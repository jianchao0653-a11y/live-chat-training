package com.conversationlens.ime;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Locale;
import com.conversationlens.ime.KeyboardAssistantPolicy.Mode;
import com.conversationlens.ime.KeyboardAssistantPolicy.Segment;

/** Transient customer tools hosted inside the IME. No model calls or chat capture. */
final class KeyboardAssistantPanel extends ScrollView {
    static final class CustomerSelection {
        final Mode mode;
        final String id, name, platform, pairId, notes;
        final Segment segment;
        CustomerSelection(Mode mode, JSONObject person) {
            this.mode=mode; id=person.optString("id"); name=person.optString("name");
            platform=person.optString("platform");JSONObject relationship=person.optJSONObject("relationship");
            pairId=person.optString("pair_id",relationship==null?"":relationship.optString("id"));
            segment=Segment.parse(person.optString("segment"));
            notes=person.optString("notes",relationship==null?"":relationship.optString("notes"));
        }
    }
    interface Listener {
        void onEditorFocused(LocalEditor editor);
        void onEditorBlurred(LocalEditor editor);
        void onEditorSelectionChanged(LocalEditor editor);
        boolean canSubmitEditor();
        void onCustomerSelected(CustomerSelection selection);
        void onSelectionCleared();
        void onLoginRequested();
    }
    /** A private Editable, with no connection to the host app's InputConnection. */
    static final class LocalEditor extends EditText {
        private Listener listener;
        private int applying;
        final InputConnection connection;
        LocalEditor(Context context, Listener listener, int id, String hint) {
            super(context); this.listener=listener; setId(id);
            setSaveEnabled(false);setFreezesText(false);
            setInputType(InputType.TYPE_CLASS_TEXT); setSingleLine(true);
            setImeOptions(EditorInfo.IME_ACTION_DONE|EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING);
            setShowSoftInputOnFocus(false); setHint(hint); setContentDescription(hint);
            LensStyle.field(this); setMinHeight(LensStyle.dp(context,LensTokens.LOCAL_FIELD_MIN_HEIGHT_DP));
            setPadding(LensStyle.dp(context,LensTokens.LOCAL_FIELD_PADDING_X_DP),LensStyle.dp(context,LensTokens.LOCAL_FIELD_PADDING_Y_DP),LensStyle.dp(context,LensTokens.LOCAL_FIELD_PADDING_X_DP),LensStyle.dp(context,LensTokens.LOCAL_FIELD_PADDING_Y_DP));
            connection=new BaseInputConnection(this,true) {
                @Override public Editable getEditable() { return LocalEditor.this.getText(); }
            };
            setOnFocusChangeListener((v,focused)->{if(focused)listener.onEditorFocused(this);else listener.onEditorBlurred(this);});
            setOnTouchListener((v,event)->{if(event.getAction()==android.view.MotionEvent.ACTION_DOWN)listener.onEditorFocused(this);return false;});
        }
        void beginLocalEdit() { applying++; }
        void endLocalEdit() { applying--; }
        @Override protected void onSelectionChanged(int start,int end) {
            super.onSelectionChanged(start,end);
            if(listener!=null && applying==0 && hasFocus())listener.onEditorSelectionChanged(this);
        }
    }
    private final Listener listener;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final LinearLayout body, rows;
    private final TextView message, budget;
    private final ArrayList<JSONObject> people=new ArrayList<>();
    private final ArrayList<Button> actions=new ArrayList<>();
    private Mode mode=Mode.NORMAL;
    private boolean active,busy,creating;
    private int epoch;
    private NativeClient client;
    private LocalEditor search,name;
    private Spinner platform;
    private Button save;
    private String selectedId="";
    private String createOperation;

    KeyboardAssistantPanel(Context context,Listener listener) {
        super(context); this.listener=listener; setFillViewport(false);setClipToPadding(false);
        setBackground(LensStyle.shape(context,LensStyle.BG,LensTokens.PANEL_RADIUS_DP,true));
        body=column();body.setFocusableInTouchMode(true);body.setPadding(dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.COMPACT_TOP_DP),dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.GUTTER_DP));addView(body);
        budget=new TextView(context);LensStyle.text(budget,LensTokens.TEXT_CAPTION_SP,false);
        message=new TextView(context);LensStyle.text(message,LensTokens.TEXT_SUPPORT_SP,false);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        rows=column();setVisibility(GONE);
    }
    @Override protected void onMeasure(int width,int height) {
        int screen=getResources().getConfiguration().screenHeightDp;
        int cap=dp(Math.min(ImePanelLayout.ROSTER_MAX_DP,Math.max(ImePanelLayout.ROSTER_MIN_DP,Math.round(screen*ImePanelLayout.ROSTER_SCREEN_FRACTION))));
        int size=MeasureSpec.getSize(height),kind=MeasureSpec.getMode(height);
        super.onMeasure(width,MeasureSpec.makeMeasureSpec(kind==MeasureSpec.UNSPECIFIED?cap:Math.min(size,cap),MeasureSpec.AT_MOST));
    }
    void open(Mode next) {
        close(); mode=next;active=true;setVisibility(VISIBLE);showRoster();load();
    }
    void close() {
        active=false;epoch++;busy=false;client=null;mode=Mode.NORMAL;selectedId="";
        // Clear focus before detaching fields so the service revokes their route.
        if(search!=null)search.clearFocus();if(name!=null)name.clearFocus();
        search=null;name=null;people.clear();body.removeAllViews();rows.removeAllViews();actions.clear();message.setText("");budget.setText("");
        setVisibility(GONE);
    }
    void updateInputState() { if(save!=null)save.setEnabled(active&&!busy&&listener.canSubmitEditor()&&name!=null&&!name.getText().toString().trim().isEmpty()); }
    NativeClient connection() {return client;}
    private void clearEditors() {
        body.requestFocus();
        if(search!=null)search.clearFocus();if(name!=null)name.clearFocus();
        search=null;name=null;save=null;
    }
    private void page() {
        clearEditors();body.removeAllViews();actions.clear();
        body.addView(budget);body.addView(message);
    }
    private void showRoster() {
        creating=false;page();
        LinearLayout controls=new LinearLayout(getContext());body.addView(controls);
        addAction(controls,"新增客户",this::showCreate);addAction(controls,"刷新",this::load);
        search=new LocalEditor(getContext(),listener,4201,"搜索客户昵称");
        search.setFilters(new InputFilter[]{new InputFilter.LengthFilter(60)});
        body.addView(search,new LinearLayout.LayoutParams(-1,-2));
        search.addTextChangedListener(watcher(this::renderRows));
        if(rows.getParent()!=null)((LinearLayout)rows.getParent()).removeView(rows);body.addView(rows);
        renderRows();setBusy(busy);
    }
    private void renderRows() {
        if(!active||creating)return;
        rows.removeAllViews();
        String query=search==null?"":search.getText().toString().trim().toLowerCase(Locale.ROOT);
        int count=0;
        for(JSONObject person:people) {
            Segment segment=Segment.parse(person.optString("segment"));
            if(!KeyboardAssistantPolicy.visible(mode,segment)||!person.optString("name").toLowerCase(Locale.ROOT).contains(query))continue;
            count++;
            LinearLayout item=column();rows.addView(item,LensStyle.space(getContext()));
            String title=person.optString("name")+" · "+person.optString("platform");
            String notes=person.optString("notes").trim();
            boolean duplicate=false;
            for(JSONObject other:people)if(!person.optString("id").equals(other.optString("id"))&&person.optString("name").equals(other.optString("name"))&&person.optString("platform").equals(other.optString("platform"))){duplicate=true;break;}
            if(duplicate)label(item,"同名客户：请核对背景；仍无法区分时，先在客户资料中设置不同昵称。",LensTokens.TEXT_SUPPORT_SP);
            if(!notes.isEmpty())label(item,"背景："+(notes.codePointCount(0,notes.length())>120?notes.substring(0,notes.offsetByCodePoints(0,120))+"…（完整背景见客户资料）":notes),LensTokens.TEXT_SUPPORT_SP);
            else if(duplicate)label(item,"背景未填写，选择后请先核对或补充客户资料。",LensTokens.TEXT_SUPPORT_SP);
            if(segment==Segment.UNCLASSIFIED) {
                label(item,title+" · 待手动分类",LensTokens.TEXT_BODY_SP);
                LinearLayout classify=new LinearLayout(getContext());item.addView(classify);
                rowAction(classify,"归为新用户",()->classify(person,Segment.NEW));
                rowAction(classify,"归为老用户",()->classify(person,Segment.MAINTAIN));
            } else {
                boolean chosen=selectedId.equals(person.optString("id"));
                Button select=rowAction(item,(chosen?"已选择：":"选择：")+title,()->select(person));
                select.setSelected(chosen);
                if(segment==Segment.NEW)rowAction(item,"将「"+person.optString("name")+"」转入老用户维护",()->classify(person,Segment.MAINTAIN));
            }
        }
        if(count==0&&!busy)label(rows,people.isEmpty()?"还没有客户，可先新增。":"没有匹配的客户。",LensTokens.TEXT_BODY_SP);
    }
    private void select(JSONObject person) {
        if(busy)return;
        Segment segment=Segment.parse(person.optString("segment"));
        if(!KeyboardAssistantPolicy.selectable(mode,segment))return;
        selectedId=person.optString("id");
        body.requestFocus();if(search!=null)search.clearFocus();
        listener.onCustomerSelected(new CustomerSelection(mode,person));
        message.setText("已选择「"+person.optString("name")+"」。切回普通输入可继续聊天。");
        renderRows();
    }
    private void showCreate() {
        if(busy||client==null)return;
        createOperation=java.util.UUID.randomUUID().toString();
        listener.onSelectionCleared();selectedId="";creating=true;page();
        message.setText(mode==Mode.NEW?"新增客户将归入新用户破冰。":"新增客户将归入老用户维护。");
        name=new LocalEditor(getContext(),listener,4202,"客户昵称");
        name.setFilters(new InputFilter[]{new InputFilter.LengthFilter(60)});body.addView(name);
        name.addTextChangedListener(watcher(this::updateInputState));
        platform=new ImeDropdownSpinner(getContext());
        platform.setAdapter(new ArrayAdapter<String>(getContext(),android.R.layout.simple_spinner_dropdown_item,new String[]{"微信","抖音","快手","视频号"}));
        platform.setContentDescription("聊天平台");body.addView(platform,new LinearLayout.LayoutParams(-1,dp(LensTokens.SELECTOR_MIN_HEIGHT_DP)));
        LinearLayout buttons=new LinearLayout(getContext());body.addView(buttons);
        save=addAction(buttons,"保存客户",this::create);addAction(buttons,"返回列表",this::showRoster);
        updateInputState();name.requestFocus();smoothScrollTo(0,0);
    }
    private void load() {
        if(!active||busy)return;
        final int ticket=++epoch;setBusy(true);message.setText("正在读取客户…");
        NativeClient.IO.execute(()->{
            try {
                NativeClient loaded=NativeClient.load(getContext());
                if(loaded==null){main.post(()->{if(valid(ticket)){setBusy(false);showLogin("首次使用，请先登录。");}});return;}
                JSONObject me=loaded.call("auth/me",null);
                JSONObject roster=loaded.call("library/people",null);
                main.post(()->{if(!valid(ticket))return;client=loaded;setBusy(false);
                    JSONObject b=me.optJSONObject("budget");budget.setText(b==null?"":budgetText(b));
                    people.clear();JSONArray array=roster.optJSONArray("people");
                    if(array!=null)for(int i=0;i<array.length();i++){JSONObject p=array.optJSONObject(i);if(p!=null)people.add(p);}
                    message.setText("选择客户；未分类客户需先手动归类。");showRoster();
                });
            } catch(Exception failure) { main.post(()->{if(valid(ticket)){setBusy(false);showLogin("读取失败，请检查网络或重新登录。");}}); }
        });
    }
    static String budgetText(JSONObject b) {
        if(b==null)return "";
        if(!b.has("portrait_daily_limit")||!b.has("portrait_used_today"))return "";
        String timezone=b.optString("day_timezone",b.optString("timezone",""));
        String reset="UTC".equals(timezone)?" · 北京时间 08:00 重置":timezone.isEmpty()?"":" · 按 "+timezone+" 日期重置";
        String total=b.has("daily_limit")&&b.has("project_used_today")?"\n项目共享分析额度已占用 "+b.optInt("project_used_today")+" / "+b.optInt("daily_limit")+" 次；仍受共享金额预算限制。":"\n全部分析仍受项目共享次数和金额预算限制。";
        String replies=b.has("reply_used_today")&&b.has("opening_used_today")?"\n本账号今日回复请求 "+b.optInt("reply_used_today")+" 次，破冰请求 "+b.optInt("opening_used_today")+" 次。":"";
        return "新客画像今日已用 "+b.optInt("portrait_used_today")+" / "+b.optInt("portrait_daily_limit")+" 次"+reset+total+replies;
    }
    private void showLogin(String text) {
        client=null;selectedId="";people.clear();listener.onSelectionCleared();page();message.setText(text);budget.setText("");
        addAction(body,"首次登录／重新登录",listener::onLoginRequested);addAction(body,"重试读取",this::load);
    }
    private void create() {
        if(busy||client==null||name==null)return;
        if(!listener.canSubmitEditor()){message.setText("请先选定候选字，再保存客户。");return;}
        String value=name.getText().toString().trim();if(value.isEmpty()){message.setText("请填写客户昵称。");return;}
        try {
            JSONObject body=new JSONObject().put("operation_id",createOperation).put("name",value).put("platform",platform.getSelectedItem()).put("segment",mode==Mode.NEW?"NEW":"MAINTAIN");
            mutate("library/people",body,()->{showRoster();load();},"客户已保存。");
        } catch(Exception error){message.setText("请检查客户昵称。");}
    }
    private void classify(JSONObject person,Segment segment) {
        if(busy||client==null)return;
        listener.onSelectionCleared();selectedId="";
        try {mutate("library/people/"+person.optString("id")+"/segment",new JSONObject().put("segment",segment.name()),this::load,"分类已保存。");}
        catch(Exception error){message.setText("分类失败，请重试。");}
    }
    private interface Done { void run(); }
    private void mutate(String path,JSONObject payload,Done done,String success) {
        final int ticket=++epoch;final NativeClient current=client;
        setBusy(true);message.setText("正在保存…");
        NativeClient.IO.execute(()->{
            try {current.call(path,payload);main.post(()->{if(valid(ticket)){setBusy(false);message.setText(success);done.run();}});}
            catch(Exception error){main.post(()->{if(valid(ticket)){setBusy(false);message.setText("未确认保存结果。请刷新列表核对，避免重复新增。");}});}
        });
    }
    private boolean valid(int ticket) { return active&&ticket==epoch; }
    private void setBusy(boolean value) { busy=value;for(Button action:actions)action.setEnabled(!value);renderRows();updateInputState(); }
    private Button addAction(LinearLayout parent,String title,Runnable action) { Button button=rowAction(parent,title,action);actions.add(button);return button; }
    private Button rowAction(LinearLayout parent,String title,Runnable action) {
        Button button=new Button(getContext());button.setText(title);button.setContentDescription(title);LensStyle.button(button,false);
        button.setPadding(dp(LensTokens.COMPACT_ACTION_PADDING_X_DP),dp(LensTokens.ROSTER_ACTION_PADDING_Y_DP),dp(LensTokens.COMPACT_ACTION_PADDING_X_DP),dp(LensTokens.ROSTER_ACTION_PADDING_Y_DP));button.setTextSize(LensTokens.COMPACT_ACTION_TEXT_SP);button.setFocusable(false);button.setEnabled(!busy);
        button.setOnClickListener(v->{if(active&&!busy)action.run();});
        parent.addView(button,parent.getOrientation()==LinearLayout.HORIZONTAL?new LinearLayout.LayoutParams(0,-2,1):new LinearLayout.LayoutParams(-1,-2));return button;
    }
    private TextWatcher watcher(Runnable changed) { return new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable text){changed.run();}}; }
    private LinearLayout column() { LinearLayout layout=new LinearLayout(getContext());layout.setOrientation(LinearLayout.VERTICAL);return layout; }
    private void label(LinearLayout parent,String text,int size) { TextView label=new TextView(getContext());LensStyle.text(label,size,false);label.setText(text);parent.addView(label); }
    private int dp(int n) { return LensStyle.dp(getContext(),n); }
}
