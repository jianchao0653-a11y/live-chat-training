package com.conversationlens.ime;

import android.inputmethodservice.InputMethodService;
import android.os.Handler;
import android.os.Looper;
import android.os.Build;
import android.view.WindowInsets;
import android.view.View;
import android.view.Gravity;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.ArrayList;
import android.content.Intent;
import org.json.JSONObject;

public final class LensImeService extends InputMethodService {
    // Rime is process-global. Service recreation must not create concurrent workers.
    private static final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile int generation;
    private long session; // Engine worker only.
    private boolean ready, chinese, numeric, upper, symbols, sensitive;
    private boolean composing;
    private boolean nine;
    private LinearLayout root, candidates, keyboard, toolbar, candidateRow;
    private TextView status;
    private Button previousPage, nextPage;
    private Button assist;
    private String[] latest;
    private int pending;
    private final ArrayList<Button> modeButtons = new ArrayList<>();

    @Override public void onCreate() { setTheme(R.style.LensKeyboardTheme); super.onCreate(); nine=getSharedPreferences("keyboard-layout",MODE_PRIVATE).getBoolean("nine",false); }

    @Override public View onCreateInputView() {
        getWindow().getWindow().setNavigationBarColor(LensStyle.NAVIGATION);
        getWindow().getWindow().getDecorView().setSystemUiVisibility(0);
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(4), dp(4), dp(4), dp(4)); root.setBackgroundColor(LensStyle.KEYBOARD);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int bottom = Build.VERSION.SDK_INT >= 30 ? insets.getInsets(WindowInsets.Type.navigationBars()).bottom : insets.getSystemWindowInsetBottom();
            view.setPadding(dp(4), dp(4), dp(4), dp(4) + bottom);
            // Request light icons on an explicit dark band, for both framework
            // IME navigation and system navigation in edge-to-edge windows.
            android.graphics.drawable.LayerDrawable background=new android.graphics.drawable.LayerDrawable(new android.graphics.drawable.Drawable[]{
                new android.graphics.drawable.ColorDrawable(LensStyle.KEYBOARD),new android.graphics.drawable.ColorDrawable(LensStyle.NAVIGATION)});
            background.setLayerGravity(1,Gravity.BOTTOM);background.setLayerHeight(1,bottom);
            view.setBackground(background);
            return insets;
        });
        toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);root.addView(toolbar);
        status = new TextView(this); LensStyle.text(status,12,false); status.setPadding(dp(8), dp(4), dp(8), dp(4));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        toolbar.addView(status,new LinearLayout.LayoutParams(0,-2,1));
        assist = new Button(this); LensStyle.button(assist,false);toolbar.addView(assist,new LinearLayout.LayoutParams(-2,-2));
        assist.setOnClickListener(v -> assistAction());
        HorizontalScrollView scroller = new HorizontalScrollView(this);scroller.setHorizontalScrollBarEnabled(false);
        candidates = new LinearLayout(this); scroller.addView(candidates);
        candidateRow = new LinearLayout(this);
        candidateRow.addView(scroller, new LinearLayout.LayoutParams(0, -1, 1));
        previousPage = new Button(this); previousPage.setText("‹");
        nextPage = new Button(this); nextPage.setText("›");
        for (Button button : new Button[]{previousPage, nextPage}) {
            LensStyle.key(button,true);button.setTextSize(22);
            candidateRow.addView(button, new LinearLayout.LayoutParams(dp(48), -1));
        }
        previousPage.setContentDescription("上一页候选");nextPage.setContentDescription("下一页候选");
        previousPage.setOnClickListener(view -> engine(3, -1, null));
        nextPage.setOnClickListener(view -> engine(3, 1, null));
        root.addView(candidateRow, new LinearLayout.LayoutParams(-1, dp(48)));
        keyboard = new LinearLayout(this); keyboard.setOrientation(LinearLayout.VERTICAL); root.addView(keyboard);
        render(); return root;
    }
    @Override public boolean onEvaluateFullscreenMode() { return false; }
    @Override public void onStartInput(EditorInfo info, boolean restarting) {
        super.onStartInput(info, restarting);
        AssistSession draftSession=AssistSession.current;
        boolean helper=getPackageName().equals(info.packageName) && AssistSession.helperShowing;
        if(draftSession!=null && (!draftSession.alive() || (info.inputType!=0 && !helper && !draftSession.matches(info)))) AssistSession.clear();
        generation++; pending = 0; ready = false; composing = false; latest = null;
        upper = false; symbols = false;
        sensitive = EditorPolicy.privateField(info.inputType, info.imeOptions);
        numeric = EditorPolicy.numeric(info.inputType);
        chinese = EditorPolicy.chinese(info.inputType, info.imeOptions);
        startSession(generation);
        render();
    }
    private void startSession(int token) {
        final boolean useNine=nine;
        worker.execute(() -> {
            if (session != 0) { RimeEngine.close(session); session = 0; }
            if (token != generation) return;
            // Password, no-learning, number, URL and email editors never enter Rime.
            if (!chinese) { main.post(() -> { if (token == generation) { ready = true; render(); } }); return; }
            try {
                session = RimeEngine.prepare(this);
                RimeEngine.step(session,5,useNine?1:0);
                main.post(() -> { if (token == generation) { ready = true; render(); } });
            } catch (Exception | LinkageError error) {
                main.post(() -> { if (token == generation) {
                    ready = true; chinese = false; render(); status.setText("中文引擎未就绪 · 可使用英文或切换输入法");
                } });
            }
        });
    }
    @Override public void onFinishInput() {
        generation++; pending = 0; ready = false; latest = null; composing = false;
        worker.execute(() -> { if (session != 0) { RimeEngine.close(session); session = 0; } });
        render(); super.onFinishInput();
    }
    @Override public void onFinishInputView(boolean finishingInput) {
        // Invalidate pending work even when Android keeps the editor session alive.
        generation++; pending = 0; ready = false; latest = null; composing = false;
        InputConnection connection = getCurrentInputConnection();
        if (connection != null) connection.finishComposingText();
        worker.execute(() -> { if (session != 0) { RimeEngine.close(session); session = 0; } });
        super.onFinishInputView(finishingInput);
    }
    @Override public void onStartInputView(EditorInfo info, boolean restarting) {
        super.onStartInputView(info, restarting);
        if(Build.VERSION.SDK_INT>=30){
            android.view.WindowInsetsController bars=getWindow().getWindow().getInsetsController();
            if(bars!=null)bars.setSystemBarsAppearance(0,android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        }
        if (!ready) { generation++; startSession(generation); }
        render();
    }
    @Override public void onDestroy() {
        AssistSession.clear();
        generation++;
        worker.execute(() -> { if (session != 0) RimeEngine.close(session); session = 0; });
        super.onDestroy();
    }
    @Override public void onUpdateSelection(int oldStart, int oldEnd, int start, int end, int candidateStart, int candidateEnd) {
        super.onUpdateSelection(oldStart, oldEnd, start, end, candidateStart, candidateEnd);
        if (composing && (start != end || candidateEnd < 0 || end != candidateEnd)) {
            InputConnection connection = getCurrentInputConnection();
            if (connection != null) connection.finishComposingText();
            generation++; pending = 0; composing = false; latest = null; ready = false;
            startSession(generation); render();
        }
    }
    private void engine(int action, int value, String fallback) {
        if (!ready) return;
        invalidateDraftOnTyping();
        int token = generation;
        pending++; busyState();
        worker.execute(() -> {
            if (token != generation || session == 0) return;
            try {
                String[] result = RimeEngine.step(session, action, value);
                main.post(() -> {
                    if (token != generation) return;
                    pending--; busyState();
                    InputConnection connection = getCurrentInputConnection();
                    if (connection == null) return;
                    connection.beginBatchEdit();
                    try {
                        if (!result[1].isEmpty()) connection.commitText(result[1], 1);
                        if (!result[2].isEmpty()) connection.setComposingText(result[2], 1);
                        else if (composing && result[1].isEmpty()) { connection.setComposingText("", 1); connection.finishComposingText(); }
                        else connection.finishComposingText();
                        composing = !result[2].isEmpty(); latest = result;
                        if ("0".equals(result[0]) && fallback != null) direct(fallback);
                    } finally { connection.endBatchEdit(); }
                    renderCandidates();
                });
            } catch (Exception | LinkageError error) {
                main.post(() -> { if (token == generation) {
                    generation++; pending = 0; chinese = false; latest = null; composing = false;
                    InputConnection connection = getCurrentInputConnection();
                    if (connection != null) connection.finishComposingText();
                    render(); status.setText("中文引擎异常 · 请切换输入法");
                } });
            }
        });
    }
    private void queuedDirect(String text) {
        if (!ready) return;
        invalidateDraftOnTyping();
        int token = generation;
        pending++; busyState();
        worker.execute(() -> main.post(() -> {
            if (token != generation) return;
            pending--; direct(text); busyState();
        }));
    }
    private void busyState() {
        for (Button button : modeButtons) button.setEnabled(ready && pending == 0);
        renderCandidates();
    }
    private void direct(String text) {
        InputConnection connection = getCurrentInputConnection();
        if (connection == null) return;
        if ("\b".equals(text)) {
            CharSequence selected = connection.getSelectedText(0);
            if (selected != null && selected.length() > 0) connection.commitText("", 1);
            else connection.deleteSurroundingTextInCodePoints(1, 0);
        } else connection.commitText(text, 1);
    }
    private void key(String text) {
        if (!ready) return;
        if (chinese && !symbols) engine(0, text.charAt(0), text);
        else queuedDirect(upper ? text.toUpperCase(java.util.Locale.ROOT) : text);
    }
    private void toggleMode() {
        if (pending != 0 || sensitive || numeric || !EditorPolicy.chinese(getCurrentInputEditorInfo().inputType, getCurrentInputEditorInfo().imeOptions)) return;
        InputConnection connection = getCurrentInputConnection();
        if (connection != null) connection.finishComposingText();
        generation++; pending = 0; chinese = !chinese; composing = false; latest = null; ready = false; symbols = false;
        startSession(generation); render();
    }
    private void render() {
        if (root == null) return;
        status.setText(!ready ? "正在准备本机词库… · 可切换输入法" : sensitive ? "私密输入 · 英文 · 不记录" : chinese ? "简体拼音 · 离线 · 不记录学习" : "英文 / 符号 · 离线");
        renderAssist();
        keyboard.removeAllViews(); modeButtons.clear();
        String[] rows = numeric ? new String[]{"123", "456", "789", "+0."}
            : symbols ? new String[]{"1234567890", "@#￥%&*-+=", "，。？！、：；（）"}
            : chinese && nine ? new String[]{"123","456","789"} : new String[]{"qwertyuiop", "asdfghjkl", "zxcvbnm"};
        for (String row : rows) {
            LinearLayout line = row();
            if(!numeric && !symbols && !(chinese&&nine) && row.equals(rows[1]))line.setPadding(dp(14),0,dp(14),0);
            for (int i = 0; i < row.length(); i++) {
                String key = row.substring(i, i + 1);
                boolean nineKey=chinese&&nine&&!symbols&&!numeric;
                String[] labels={"分词 ' ","2 ABC","3 DEF","4 GHI","5 JKL","6 MNO","7 PQRS","8 TUV","9 WXYZ"};
                String caption=nineKey?labels[Integer.parseInt(key)-1]:upper&&!chinese?key.toUpperCase(java.util.Locale.ROOT):key;
                Button letter=addKey(line,caption,()->key(nineKey&&key.equals("1")?"'":key),1);
                if(nineKey)LensStyle.key(letter,false);
            }
            if (row.equals(rows[rows.length - 1]) && !(chinese&&nine&&!symbols&&!numeric)) addKey(line, "⌫", () -> {
                if (chinese) engine(0, 0xff08, "\b"); else queuedDirect("\b");
            }, 1.4f);
        }
        LinearLayout controls = row();
        if(chinese&&nine&&!symbols&&!numeric)addKey(controls,"⌫",()->engine(0,0xff08,"\b"),1);
        addKey(controls, "切换", () -> ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).showInputMethodPicker(), 1.2f).setEnabled(true);
        if (!numeric) {
            modeButtons.add(addKey(controls, chinese ? "中" : "英", this::toggleMode, .8f));
            if(chinese)modeButtons.add(addKey(controls,nine?"全键":"九宫",()->{
                if(pending!=0)return;
                // Resolve the old composition before switching schemas on the same worker.
                if(composing)engine(4,0,null);
                nine=!nine;getSharedPreferences("keyboard-layout",MODE_PRIVATE).edit().putBoolean("nine",nine).apply();
                engine(5,nine?1:0,null);render();
            },1));
            modeButtons.add(addKey(controls, symbols ? "ABC" : "123", () -> {
                // Flush composition before changing layouts so punctuation cannot reorder it.
                if (composing) engine(4, 0, null);
                symbols = !symbols; render();
            }, 1));
            if (!chinese) modeButtons.add(addKey(controls, "⇧", () -> { upper = !upper; render(); }, .8f));
            addKey(controls, "空格", () -> { if (chinese) engine(0, 32, " "); else queuedDirect(" "); }, 2);
        }
        modeButtons.add(addKey(controls, "换行", () -> {
            if (chinese && composing) engine(0, 32, null);
            else if (EditorPolicy.newline(getCurrentInputEditorInfo().inputType)) queuedDirect("\n");
            else requestHideSelf(0);
        }, 1.2f));
        busyState();
    }
    private void renderCandidates() {
        renderAssist();
        if (candidates == null) return;
        candidateRow.setVisibility(chinese&&(composing||pending>0)?View.VISIBLE:View.GONE);
        candidates.removeAllViews();
        previousPage.setVisibility(View.GONE); nextPage.setVisibility(View.GONE);
        if (!chinese || latest == null || pending != 0) return;
        final int token = generation;
        for (int i = 5; i < latest.length; i++) {
            final int index = i - 5;
            Button button = new Button(this); button.setText(latest[i]); LensStyle.key(button,false);button.setTextSize(18);button.setPadding(dp(12),0,dp(12),0);
            button.setOnClickListener(view -> { if (token == generation) engine(1, index, null); });
            candidates.addView(button, new LinearLayout.LayoutParams(-2, -1));
        }
        if (latest.length > 5) {
            previousPage.setVisibility(View.VISIBLE); nextPage.setVisibility(View.VISIBLE);
            previousPage.setEnabled(!"0".equals(latest[3])); nextPage.setEnabled(!"1".equals(latest[4]));
        }
    }
    private void renderAssist(){
        if(assist==null)return;
        EditorInfo info=getCurrentInputEditorInfo();
        boolean helper=info!=null && getPackageName().equals(info.packageName) && AssistSession.helperShowing;
        boolean allowed=info!=null && EditorPolicy.chinese(info.inputType,info.imeOptions) && !helper;
        assist.setVisibility(allowed?View.VISIBLE:View.GONE);
        AssistSession s=AssistSession.current;
        boolean insert=s!=null && s.insertable(info);
        toolbar.setOrientation(insert?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);
        status.setLayoutParams(new LinearLayout.LayoutParams(insert?-1:0,-2,insert?0:1));
        assist.setLayoutParams(new LinearLayout.LayoutParams(insert?-1:-2,-2));
        LensStyle.button(assist,insert);
        assist.setText(insert?"确认正在与「"+s.result.optJSONObject("person").optString("name")+"」聊天并插入":"建议");
        assist.setEnabled(ready && pending==0 && !composing && (s==null || !s.consuming));
    }
    private void invalidateDraftOnTyping(){AssistSession s=AssistSession.current;if(s!=null && s.result!=null && !AssistSession.helperShowing && s.matches(getCurrentInputEditorInfo()))AssistSession.clear();}
    private void assistAction(){
        EditorInfo info=getCurrentInputEditorInfo();
        if(info==null || !EditorPolicy.chinese(info.inputType,info.imeOptions) || pending!=0 || composing)return;
        AssistSession s=AssistSession.current;
        if(s!=null && s.insertable(info)){
            final int token=generation;final String context=s.context;final int revision=s.revision;s.consuming=true;renderAssist();
            try {
                JSONObject person=s.result.getJSONObject("person");JSONObject payload=new JSONObject().put("context",context).put("host",s.host).put("person_id",person.getString("id")).put("pair_id",person.getString("pair_id")).put("confirmed",true).put("draft",s.draft);
                String ticket=s.result.getString("ticket_id");
                NativeClient.IO.execute(()->{try{JSONObject answer=s.client.call("tickets/"+ticket+"/consume",payload);main.post(()->{
                    if(token!=generation || !s.alive() || s.revision!=revision || !s.matches(getCurrentInputEditorInfo()) || pending!=0 || composing){if(AssistSession.current==s)AssistSession.clear();renderAssist();return;}
                    InputConnection connection=getCurrentInputConnection();boolean inserted=connection!=null && connection.commitText(answer.optString("draft"),1);
                    if(inserted){AssistSession.feedbackId=answer.optString("analysis_id");AssistSession.feedbackName=s.result.optJSONObject("person").optString("name");AssistSession.feedbackClient=s.client;}
                    AssistSession.clear();renderAssist();status.setText(inserted?"已插入草稿 · 请自行检查并发送":"输入框已关闭，请重新生成建议");
                });}catch(Exception e){main.post(()->{if(AssistSession.current==s){AssistSession.clear();renderAssist();status.setText(e.getMessage()==null?"插入失败，请重新分析":e.getMessage());}});}});
            }catch(Exception e){AssistSession.clear();renderAssist();}
        }else{
            AssistSession.clear();AssistSession.current=new AssistSession(info);
            final AssistSession fresh=AssistSession.current;
            main.postDelayed(()->{if(AssistSession.current==fresh){AssistSession.clear();renderAssist();}},15*60000);
            AssistSession.helperShowing=true;
            startActivity(new Intent(this,AssistantActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }
    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER);
        int height=getResources().getConfiguration().orientation==2?48:52;
        keyboard.addView(row, new LinearLayout.LayoutParams(-1, dp(height))); return row;
    }
    private Button addKey(LinearLayout row, String label, Runnable action, float weight) {
        Button button = new Button(this); button.setText(label);LensStyle.key(button,label.length()>1 || "⌫⇧中英".contains(label));button.setTextSize(label.length() > 1 ? 13 : 18);
        button.setPadding(0, 0, 0, 0); button.setMinWidth(0); button.setMinimumWidth(0); button.setAllCaps(false);
        button.setContentDescription(label.equals("⌫")?"退格":label.equals("⇧")?"切换大写":label);
        button.setEnabled(ready); button.setOnClickListener(view -> action.run());
        row.addView(button, new LinearLayout.LayoutParams(0, -1, weight)); return button;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
