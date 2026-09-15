package com.conversationlens.ime;

import android.inputmethodservice.InputMethodService;
import android.os.Handler;
import android.os.Looper;
import android.os.Build;
import android.os.SystemClock;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.InsetDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.util.TypedValue;
import android.view.WindowInsets;
import android.view.View;
import android.view.Gravity;
import android.view.WindowManager;
import android.view.KeyEvent;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.ArrayList;
import android.content.Intent;
import org.json.JSONObject;
import com.conversationlens.ime.KeyboardAssistantPolicy.Mode;
import com.conversationlens.ime.KeyboardAssistantPolicy.Target;

public final class LensImeService extends InputMethodService {
    // Rime is process-global. Service recreation must not create concurrent workers.
    private static final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile int generation;
    private long session; // Engine worker only.
    private boolean ready, chinese, numeric, upper, symbols, digits, sensitive;
    private boolean composing;
    private boolean nine;
    private LinearLayout root, candidates, keyboard, toolbar, headerActions, candidateRow;
    private ScrollView keyboardViewport;
    private TextView status;
    private Button previousPage, nextPage;
    private Button assist;
    private Button layoutSwitch, resetKey;
    private String statusMessage = "";
    private String[] latest;
    private int pending;
    private final ArrayList<Button> modeButtons = new ArrayList<>();
    private final KeyboardAssistantPolicy assistantRoute=new KeyboardAssistantPolicy();
    private LinearLayout assistantTabs;
    private final ArrayList<Button> assistantModeButtons=new ArrayList<>();
    private KeyboardAssistantPanel assistantPanel;
    private KeyboardAssistantPanel.Listener internalEditorListener;
    private ImeAssistantPanel suggestionPanel;
    private ImeCustomerDetailsPanel customerDetailsPanel;
    private ImeAssistantPanel.Snapshot detailsReturnDraft;
    private NativeClient detailsClient;
    private KeyboardAssistantPanel.LocalEditor localEditor;
    private KeyboardAssistantPanel.CustomerSelection selectedCustomer;
    private boolean changingTarget;
    private boolean imeAlive;
    private final Runnable imageCompleted=()->main.post(()->{
        if(!imeAlive||!getCurrentInputStarted()||getCurrentInputConnection()==null||!KeyboardImageRequest.isCapture())return;
        EditorInfo info=getCurrentInputEditorInfo();
        if(!KeyboardImageRequest.readyFor(info))return;
        if(isInputViewShown()&&suggestionPanel!=null)restoreImageRequest(info);
        else if(Build.VERSION.SDK_INT>=28)requestShowSelf(0);
    });

    @Override public void onCreate() { setTheme(R.style.LensKeyboardTheme); super.onCreate();imeAlive=true; nine=getSharedPreferences("keyboard-layout",MODE_PRIVATE).getBoolean("nine",false);KeyboardImageRequest.addCompletionListener(imageCompleted); }

    @Override public View onCreateInputView() {
        final boolean recreated=root!=null;
        if(recreated){dismissAssistant();generation++;pending=0;ready=false;composing=false;latest=null;}
        getWindow().getWindow().setNavigationBarColor(LensStyle.NAVIGATION);
        getWindow().getWindow().getDecorView().setSystemUiVisibility(0);
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP)); root.setBackgroundColor(LensStyle.KEYBOARD);
        assistantTabs=new LinearLayout(this);root.addView(assistantTabs);
        assistantModeButtons.clear();
        String[] titles={"普通输入","新用户破冰","老用户维护"};
        Mode[] modes={Mode.NORMAL,Mode.NEW,Mode.MAINTAIN};
        for(int i=0;i<modes.length;i++){
            final Mode mode=modes[i];Button button=new Button(this);button.setText(titles[i]);button.setContentDescription(titles[i]);
            styleKey(button,true,false,LensTokens.KEY_TAB_TEXT_SP);button.setFocusable(false);button.setOnClickListener(v->changeAssistantMode(mode));
            assistantModeButtons.add(button);assistantTabs.addView(button,new LinearLayout.LayoutParams(0,dp(KeyboardLayout.BAR_HEIGHT_DP),1));
        }
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int bottom = Build.VERSION.SDK_INT >= 30 ? insets.getInsets(WindowInsets.Type.navigationBars()).bottom : insets.getSystemWindowInsetBottom();
            view.setPadding(dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP), dp(KeyboardLayout.GUTTER_DP) + bottom);
            // Request light icons on an explicit dark band, for both framework
            // IME navigation and system navigation in edge-to-edge windows.
            android.graphics.drawable.LayerDrawable background=new android.graphics.drawable.LayerDrawable(new android.graphics.drawable.Drawable[]{
                new android.graphics.drawable.ColorDrawable(LensStyle.KEYBOARD),new android.graphics.drawable.ColorDrawable(LensStyle.NAVIGATION)});
            background.setLayerGravity(1,Gravity.BOTTOM);background.setLayerHeight(1,bottom);
            view.setBackground(background);
            return insets;
        });
        toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);root.addView(toolbar);
        assist = new Button(this); styleKey(assist,false,true,LensTokens.KEY_ACTION_TEXT_SP);assist.setMinHeight(dp(KeyboardLayout.BAR_HEIGHT_DP));
        toolbar.addView(assist,new LinearLayout.LayoutParams(0,-2,1));
        assist.setOnClickListener(v -> assistAction());
        headerActions=new LinearLayout(this);headerActions.setGravity(Gravity.END|Gravity.CENTER_VERTICAL);
        toolbar.addView(headerActions,new LinearLayout.LayoutParams(-2,-2));
        layoutSwitch=new Button(this);styleKey(layoutSwitch,true,false,LensTokens.KEY_TAB_TEXT_SP);layoutSwitch.setOnClickListener(v->switchLayout());
        headerActions.addView(layoutSwitch,new LinearLayout.LayoutParams(dp(KeyboardLayout.HEADER_SWITCH_WIDTH_DP),dp(KeyboardLayout.BAR_HEIGHT_DP)));
        Button systemSwitch=new Button(this);systemSwitch.setText("切换");systemSwitch.setContentDescription("切换输入法");styleKey(systemSwitch,true,false,LensTokens.KEY_TAB_TEXT_SP);
        systemSwitch.setOnClickListener(v->((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).showInputMethodPicker());
        headerActions.addView(systemSwitch,new LinearLayout.LayoutParams(dp(KeyboardLayout.HEADER_SWITCH_WIDTH_DP),dp(KeyboardLayout.BAR_HEIGHT_DP)));
        status = new TextView(this); LensStyle.text(status,LensTokens.TEXT_CAPTION_SP,false); status.setPadding(dp(LensTokens.KEYBOARD_STATUS_PADDING_X_DP), dp(LensTokens.KEYBOARD_STATUS_PADDING_Y_DP), dp(LensTokens.KEYBOARD_STATUS_PADDING_X_DP), dp(LensTokens.KEYBOARD_STATUS_PADDING_Y_DP));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(status,new LinearLayout.LayoutParams(-1,-2));
        internalEditorListener=new KeyboardAssistantPanel.Listener(){
            @Override public void onEditorFocused(KeyboardAssistantPanel.LocalEditor editor){focusLocalEditor(editor);}
            @Override public void onEditorBlurred(KeyboardAssistantPanel.LocalEditor editor){blurLocalEditor(editor);}
            @Override public void onEditorSelectionChanged(KeyboardAssistantPanel.LocalEditor editor){
                if(!changingTarget&&localEditor==editor){finishTargetComposition();assistantRoute.invalidate();restartTarget();}
            }
            @Override public boolean canSubmitEditor(){return ready&&pending==0&&!composing;}
            @Override public void onCustomerSelected(KeyboardAssistantPanel.CustomerSelection selection){
                if(selectedCustomer==null||!selectedCustomer.id.equals(selection.id)||selectedCustomer.mode!=selection.mode)AssistSession.clear();
                selectedCustomer=selection;
                openSuggestionPanel(selection,assistantPanel.connection(),null,null,"");
            }
            @Override public void onSelectionCleared(){selectedCustomer=null;AssistSession.clear();}
            @Override public void onLoginRequested(){
                changeAssistantMode(Mode.NORMAL);
                startActivity(new Intent(LensImeService.this,LibraryActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            }
        };
        assistantPanel=new KeyboardAssistantPanel(this,internalEditorListener);
        root.addView(assistantPanel,new LinearLayout.LayoutParams(-1,-2));
        suggestionPanel=new ImeAssistantPanel(this,internalEditorListener,new ImeAssistantPanel.Listener(){
            @Override public void onBackToCustomers(){showCustomerList();}
            @Override public void onInsertRequested(AssistSession session,String draft){insertFromPanel(session,draft);}
            @Override public void onImageRequested(ImeAssistantPanel.Snapshot snapshot){
                EditorInfo info=getCurrentInputEditorInfo();
                if(info==null||!EditorPolicy.chinese(info.inputType,info.imeOptions)||pending!=0||composing)return;
                finishTargetComposition();
                suggestionPanel.revokeForImage();
                try{KeyboardImageRequest.begin(LensImeService.this,info.packageName,info.fieldId,info.inputType,snapshot);}
                catch(RuntimeException failure){showStatus("系统选图无法打开，请手动输入资料。");}
            }
            @Override public void onCaptureRequested(ImeAssistantPanel.Snapshot snapshot){
                EditorInfo info=getCurrentInputEditorInfo();
                if(info==null||!EditorPolicy.chinese(info.inputType,info.imeOptions)||pending!=0||composing)return;
                finishTargetComposition();suggestionPanel.revokeForImage();
                try{
                    KeyboardImageRequest.beginCapture(LensImeService.this,info.packageName,info.fieldId,info.inputType,snapshot);
                    requestHideSelf(0);
                }catch(RuntimeException failure){showStatus(failure.getMessage()==null?"系统截图未开始，可选择图片或输入文字。":failure.getMessage());}
            }
            @Override public void onCustomerDetailsRequested(ImeAssistantPanel.Snapshot snapshot){openCustomerDetails(snapshot);}
        });
        root.addView(suggestionPanel,new LinearLayout.LayoutParams(-1,-2));
        customerDetailsPanel=new ImeCustomerDetailsPanel(this,internalEditorListener,this::returnFromCustomerDetails,AssistSession::clear);
        root.addView(customerDetailsPanel,new LinearLayout.LayoutParams(-1,-2));
        HorizontalScrollView scroller = new HorizontalScrollView(this);scroller.setHorizontalScrollBarEnabled(false);
        candidates = new LinearLayout(this); scroller.addView(candidates);
        candidateRow = new LinearLayout(this);
        candidateRow.addView(scroller, new LinearLayout.LayoutParams(0, -1, 1));
        previousPage = new Button(this); previousPage.setText("‹");
        nextPage = new Button(this); nextPage.setText("›");
        for (Button button : new Button[]{previousPage, nextPage}) {
            styleKey(button,true,false,LensTokens.CANDIDATE_PAGE_TEXT_SP);
            candidateRow.addView(button, new LinearLayout.LayoutParams(dp(KeyboardLayout.BAR_HEIGHT_DP), -1));
        }
        previousPage.setContentDescription("上一页候选");nextPage.setContentDescription("下一页候选");
        previousPage.setOnClickListener(view -> engine(3, -1, null));
        nextPage.setOnClickListener(view -> engine(3, 1, null));
        root.addView(candidateRow, new LinearLayout.LayoutParams(-1, dp(KeyboardLayout.BAR_HEIGHT_DP)));
        keyboardViewport=new ScrollView(this){
            @Override protected void onMeasure(int widthSpec,int heightSpec){
                // Keep the header reachable in short windows and at large font scales.
                int fixed=toolbar.getMeasuredHeight()+root.getPaddingTop()+root.getPaddingBottom();
                if(assistantTabs.getVisibility()==View.VISIBLE)fixed+=assistantTabs.getMeasuredHeight();
                if(assistantPanel.getVisibility()==View.VISIBLE)fixed+=assistantPanel.getMeasuredHeight();
                if(suggestionPanel.getVisibility()==View.VISIBLE)fixed+=suggestionPanel.getMeasuredHeight();
                if(customerDetailsPanel.getVisibility()==View.VISIBLE)fixed+=customerDetailsPanel.getMeasuredHeight();
                if(status.getVisibility()==View.VISIBLE)fixed+=status.getMeasuredHeight();
                if(candidateRow.getVisibility()==View.VISIBLE)fixed+=candidateRow.getMeasuredHeight();
                float fraction=getResources().getConfiguration().orientation==2?KeyboardLayout.LANDSCAPE_SCREEN_FRACTION:KeyboardLayout.PORTRAIT_SCREEN_FRACTION;
                int cap=Math.max(dp(KeyboardLayout.VIEWPORT_MIN_DP),Math.round(dp(getResources().getConfiguration().screenHeightDp)*fraction)-fixed);
                int mode=View.MeasureSpec.getMode(heightSpec),size=View.MeasureSpec.getSize(heightSpec);
                super.onMeasure(widthSpec,View.MeasureSpec.makeMeasureSpec(mode==View.MeasureSpec.UNSPECIFIED?cap:Math.min(size,cap),View.MeasureSpec.AT_MOST));
            }
        };
        keyboardViewport.setFillViewport(false);keyboardViewport.setHorizontalScrollBarEnabled(false);
        keyboardViewport.setVerticalScrollBarEnabled(true);keyboardViewport.setClipToPadding(false);
        keyboard = new LinearLayout(this); keyboard.setOrientation(LinearLayout.VERTICAL);keyboardViewport.addView(keyboard);
        root.addView(keyboardViewport,new LinearLayout.LayoutParams(-1,-2));
        if(recreated)restartTarget();else render();return root;
    }
    @Override public boolean onEvaluateFullscreenMode() { return false; }
    @Override public boolean onKeyDown(int keyCode,KeyEvent event){
        if(assistantRoute.mode()==Mode.NORMAL||event.isSystem())return super.onKeyDown(keyCode,event);
        // Physical keyboard text obeys the same local-only boundary as touch keys.
        if(targetConnection()!=null&&localEditor!=null)localEditor.onKeyDown(keyCode,event);
        return true;
    }
    @Override public boolean onKeyUp(int keyCode,KeyEvent event){
        if(assistantRoute.mode()==Mode.NORMAL||event.isSystem())return super.onKeyUp(keyCode,event);
        if(targetConnection()!=null&&localEditor!=null)localEditor.onKeyUp(keyCode,event);
        return true;
    }
    @Override public boolean onKeyMultiple(int keyCode,int count,KeyEvent event){
        if(assistantRoute.mode()==Mode.NORMAL)return super.onKeyMultiple(keyCode,count,event);
        if(targetConnection()!=null&&localEditor!=null)localEditor.onKeyMultiple(keyCode,count,event);
        return true;
    }
    @Override public void onStartInput(EditorInfo info, boolean restarting) {
        super.onStartInput(info, restarting);
        if(KeyboardImageRequest.isCapture()&&info.inputType!=0&&!KeyboardImageRequest.matchesOrigin(info))KeyboardImageRequest.cancel();
        dismissAssistant();
        AssistSession draftSession=AssistSession.current;
        boolean helper=getPackageName().equals(info.packageName) && AssistSession.helperShowing;
        if(draftSession!=null && (!draftSession.alive() || (info.inputType!=0 && !helper && !draftSession.matches(info)))) AssistSession.clear();
        generation++; pending = 0; ready = false; composing = false; latest = null;
        upper = false; symbols = false; digits = false; statusMessage = "";
        sensitive = EditorPolicy.privateField(info.inputType, info.imeOptions);
        numeric = EditorPolicy.numeric(info.inputType);
        chinese = EditorPolicy.chinese(info.inputType, info.imeOptions);
        startSession(generation);
        render();
    }
    private void startSession(int token) {
        final boolean useNine=nine;
        final boolean useChinese=chinese;
        worker.execute(() -> {
            if (session != 0) { RimeEngine.close(session); session = 0; }
            if (token != generation) return;
            // Password, no-learning, number, URL and email editors never enter Rime.
            if (!useChinese) { main.post(() -> { if (token == generation) { ready = true; render(); } }); return; }
            try {
                session = RimeEngine.prepare(this);
                RimeEngine.step(session,5,useNine?1:0);
                main.post(() -> { if (token == generation) { ready = true; render(); } });
            } catch (Exception | LinkageError error) {
                main.post(() -> { if (token == generation) {
                    ready = true; chinese = false; render(); showStatus("中文引擎未就绪 · 可使用英文或切换输入法");
                } });
            }
        });
    }
    @Override public void onFinishInput() {
        dismissAssistant();
        generation++; pending = 0; ready = false; latest = null; composing = false;
        worker.execute(() -> { if (session != 0) { RimeEngine.close(session); session = 0; } });
        render(); super.onFinishInput();
    }
    @Override public void onFinishInputView(boolean finishingInput) {
        // Invalidate pending work even when Android keeps the editor session alive.
        finishTargetComposition();dismissAssistant();
        generation++; pending = 0; ready = false; latest = null; composing = false;
        InputConnection connection = getCurrentInputConnection();
        if (connection != null) connection.finishComposingText();
        worker.execute(() -> { if (session != 0) { RimeEngine.close(session); session = 0; } });
        super.onFinishInputView(finishingInput);
    }
    @Override public void onStartInputView(EditorInfo info, boolean restarting) {
        super.onStartInputView(info, restarting);
        // The system can reshow the keyboard when its consent window closes.
        // Keep our own keyboard out of the one explicitly requested frame.
        if(KeyboardImageRequest.isCapture()&&!KeyboardImageRequest.readyFor(info)){
            requestHideSelf(0);return;
        }
        if(Build.VERSION.SDK_INT>=30){
            android.view.WindowInsetsController bars=getWindow().getWindow().getInsetsController();
            if(bars!=null)bars.setSystemBarsAppearance(0,android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        }
        if (!ready) { generation++; startSession(generation); }
        render();
        restoreImageRequest(info);
    }
    @Override public void onDestroy() {
        imeAlive=false;
        KeyboardImageRequest.removeCompletionListener(imageCompleted);
        if(KeyboardImageRequest.isCapture())KeyboardImageRequest.cancel();
        dismissAssistant();
        AssistSession.clear();
        generation++;
        worker.execute(() -> { if (session != 0) RimeEngine.close(session); session = 0; });
        super.onDestroy();
    }
    @Override public void onUpdateSelection(int oldStart, int oldEnd, int start, int end, int candidateStart, int candidateEnd) {
        super.onUpdateSelection(oldStart, oldEnd, start, end, candidateStart, candidateEnd);
        if (assistantRoute.target()==Target.HOST && composing && (start != end || candidateEnd < 0 || end != candidateEnd)) {
            InputConnection connection = getCurrentInputConnection();
            if (connection != null) connection.finishComposingText();
            generation++; pending = 0; composing = false; latest = null; ready = false;
            startSession(generation); render();
        }
    }
    private void engine(int action, int value, String fallback) {
        if (!ready || targetConnection()==null) return;
        invalidateDraftOnTyping();
        int token = generation;
        final KeyboardAssistantPolicy.Route route=assistantRoute.snapshot();
        pending++; busyState();
        worker.execute(() -> {
            if (token != generation || session == 0) return;
            try {
                String[] result = RimeEngine.step(session, action, value);
                main.post(() -> {
                    if (token != generation || !assistantRoute.accepts(route)) return;
                    pending--; busyState();
                    InputConnection connection = targetConnection();
                    if (connection == null) return;
                    KeyboardAssistantPanel.LocalEditor editing=localEditor;
                    if(editing!=null)editing.beginLocalEdit();
                    connection.beginBatchEdit();
                    try {
                        if (!result[1].isEmpty()) connection.commitText(result[1], 1);
                        if (!result[2].isEmpty()) connection.setComposingText(result[2], 1);
                        else if (composing && result[1].isEmpty()) { connection.setComposingText("", 1); connection.finishComposingText(); }
                        else connection.finishComposingText();
                        composing = !result[2].isEmpty(); latest = result;
                        if ("0".equals(result[0]) && fallback != null) direct(fallback);
                    } finally { connection.endBatchEdit();if(editing!=null)editing.endLocalEdit(); }
                    if(assistantPanel!=null)assistantPanel.updateInputState();
                    if(suggestionPanel!=null)suggestionPanel.updateInputState();
                    if(customerDetailsPanel!=null)customerDetailsPanel.updateInputState();
                    renderCandidates();
                });
            } catch (Exception | LinkageError error) {
                main.post(() -> { if (token == generation && assistantRoute.accepts(route)) {
                    generation++; pending = 0; chinese = false; latest = null; composing = false;
                    finishTargetComposition();
                    render(); showStatus("中文引擎异常 · 请切换输入法");
                } });
            }
        });
    }
    private void queuedDirect(String text) {
        if (!ready || targetConnection()==null) return;
        invalidateDraftOnTyping();
        int token = generation;
        final KeyboardAssistantPolicy.Route route=assistantRoute.snapshot();
        pending++; busyState();
        worker.execute(() -> main.post(() -> {
            if (token != generation || !assistantRoute.accepts(route)) return;
            pending--; direct(text); busyState();
        }));
    }
    private void busyState() {
        for (Button button : modeButtons) button.setEnabled(ready && pending == 0 && assistantRoute.target()!=Target.BLOCKED);
        if(assistantPanel!=null)assistantPanel.updateInputState();
        if(suggestionPanel!=null)suggestionPanel.updateInputState();
        if(customerDetailsPanel!=null)customerDetailsPanel.updateInputState();
        renderCandidates();
    }
    private void direct(String text) {
        InputConnection connection = targetConnection();
        if (connection == null) return;
        KeyboardAssistantPanel.LocalEditor editing=localEditor;
        if(editing!=null)editing.beginLocalEdit();
        try {
        if ("\b".equals(text)) {
            CharSequence selected = connection.getSelectedText(0);
            if (selected != null && selected.length() > 0) connection.commitText("", 1);
            else connection.deleteSurroundingTextInCodePoints(1, 0);
        } else connection.commitText(text, 1);
        } finally {if(editing!=null)editing.endLocalEdit();}
    }
    private void key(String text) {
        if (!ready) return;
        if (chinese && !symbols && !digits) engine(0, text.charAt(0), text);
        else queuedDirect(upper ? text.toUpperCase(java.util.Locale.ROOT) : text);
    }
    private void toggleMode() {
        EditorInfo info=targetEditorInfo();
        if (pending != 0 || sensitive || numeric || info==null || !EditorPolicy.chinese(info.inputType,info.imeOptions)) return;
        finishTargetComposition();
        generation++; pending = 0; chinese = !chinese; composing = false; latest = null; ready = false; symbols = false; digits = false;
        startSession(generation); render();
    }
    private void switchLayout() {
        if (!ready || pending != 0 || !chinese) return;
        // All composition and schema operations keep their order on the engine worker.
        if (composing) engine(4,0,null);
        nine=!nine;symbols=false;digits=false;
        getSharedPreferences("keyboard-layout",MODE_PRIVATE).edit().putBoolean("nine",nine).apply();
        engine(5,nine?1:0,null);render();
    }
    private void switchPanel(boolean numberPanel) {
        if (!ready || pending != 0) return;
        if (chinese) engine(4,0,null);
        digits=numberPanel;symbols=!numberPanel;render();keyboardViewport.scrollTo(0,0);
    }
    private void returnToLetters() {
        if (!ready || pending != 0) return;
        symbols=false;digits=false;render();keyboardViewport.scrollTo(0,0);
    }
    private void literal(String text) {
        if (!ready) return;
        // Flush even if a prior key has not reached the main-thread composing flag.
        // The queued literal follows that commit; it never replaces host text.
        if (chinese) engine(4,0,null);
        queuedDirect(text);
    }
    private void backspace() {
        if(chinese&&!symbols&&!digits)engine(0,0xff08,"\b");else queuedDirect("\b");
    }
    private void resetComposition() {
        if(ready&&pending==0&&chinese&&composing)engine(2,0,null);
    }
    private void enter() {
        EditorInfo info=targetEditorInfo();
        if(info==null)return;
        if(chinese&&composing)engine(0,32,null);
        else if(EditorPolicy.newline(info.inputType))queuedDirect("\n");
        else if(localEditor!=null)localEditor.clearFocus();
        else requestHideSelf(0);
    }
    private void showStatus(String message) {
        statusMessage=message==null?"":message;renderStatus();
    }
    private void renderStatus() {
        if(status==null)return;
        String message=!statusMessage.isEmpty()?statusMessage:!ready?"正在准备词库…":sensitive?"私密输入":"";
        status.setText(message);status.setVisibility(message.isEmpty()?View.GONE:View.VISIBLE);
    }
    private void render() {
        if (root == null) return;
        renderStatus();renderAssist();
        keyboard.removeAllViews();modeButtons.clear();resetKey=null;
        modeButtons.add(layoutSwitch);
        if(chinese&&nine&&!symbols&&!digits&&!numeric)renderNineKeys();
        else renderRegularKeys();
        renderBottomRow();busyState();
    }
    private void renderNineKeys() {
        boolean landscape=getResources().getConfiguration().orientation==2;
        int height=landscape?3*keyRowHeight(true):Math.max(dp(KeyboardLayout.NINE_BOARD_MIN_DP),3*keyRowHeight(true));
        LinearLayout board=new LinearLayout(this);board.setGravity(Gravity.CENTER);
        keyboard.addView(board,new LinearLayout.LayoutParams(-1,height));
        int width=getResources().getConfiguration().screenWidthDp;
        int side=dp(Math.max(KeyboardLayout.SIDE_MIN_DP,Math.min(KeyboardLayout.SIDE_MAX_DP,Math.round(width*KeyboardLayout.SIDE_SCREEN_FRACTION))));
        LinearLayout punctuation=new LinearLayout(this);punctuation.setOrientation(LinearLayout.VERTICAL);
        punctuation.setBackground(new InsetDrawable(LensStyle.shape(this,LensStyle.TINT,LensTokens.KEY_PUNCTUATION_RADIUS_DP,true),dp(LensTokens.KEY_INSET_X_DP),dp(LensTokens.KEY_INSET_Y_DP),dp(LensTokens.KEY_INSET_X_DP),dp(LensTokens.KEY_INSET_Y_DP)));
        board.addView(punctuation,new LinearLayout.LayoutParams(landscape?dp(KeyboardLayout.LANDSCAPE_PUNCTUATION_WIDTH_DP):side,-1));
        String[] marks={"，","。","？","！"};
        LinearLayout punctuationRow=punctuation;
        for(int index=0;index<marks.length;index++){
            final String mark=marks[index];
            if(landscape&&index%2==0){punctuationRow=new LinearLayout(this);punctuation.addView(punctuationRow,new LinearLayout.LayoutParams(-1,0,1));}
            Button button=new Button(this);button.setText(mark);styleKey(button,true,false,LensTokens.KEY_NINE_TEXT_SP);button.setContentDescription(mark);
            button.setBackground(new RippleDrawable(ColorStateList.valueOf(LensTokens.ACTION_PRESSED),null,null));
            button.setEnabled(ready);button.setOnClickListener(v->literal(mark));
            punctuationRow.addView(button,landscape?new LinearLayout.LayoutParams(0,-1,1):new LinearLayout.LayoutParams(-1,0,1));
        }
        LinearLayout letters=new LinearLayout(this);letters.setOrientation(LinearLayout.VERTICAL);
        board.addView(letters,new LinearLayout.LayoutParams(0,-1,1));
        String[] captions={"分词","ABC","DEF","GHI","JKL","MNO","PQRS","TUV","WXYZ"};
        for(int y=0;y<3;y++){
            LinearLayout line=new LinearLayout(this);
            letters.addView(line,new LinearLayout.LayoutParams(-1,0,1));
            for(int x=0;x<3;x++){
                final int digit=y*3+x+1;
                String label=digit+"\n"+captions[digit-1];
                Button button=addKey(line,label,()->key(digit==1?"'":String.valueOf(digit)),1);
                styleKey(button,false,false,LensTokens.KEY_NINE_TEXT_SP);button.setSingleLine(false);button.setMaxLines(KeyboardLayout.NINE_MAX_LINES);button.setIncludeFontPadding(false);
                SpannableString caption=new SpannableString(label);
                caption.setSpan(new RelativeSizeSpan(LensTokens.KEY_DIGIT_TEXT_FRACTION),0,1,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                caption.setSpan(new ForegroundColorSpan(LensStyle.MUTED),0,1,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                button.setText(caption);button.setContentDescription(digit==1?"分词":digit+" "+captions[digit-1]);
            }
        }
        LinearLayout actions=new LinearLayout(this);actions.setOrientation(LinearLayout.VERTICAL);
        board.addView(actions,new LinearLayout.LayoutParams(side,-1));
        addColumnKey(actions,"⌫","退格",this::backspace,LensTokens.KEY_BACKSPACE_TEXT_SP);
        resetKey=addColumnKey(actions,"重输","重输当前拼音",this::resetComposition,LensTokens.KEY_RESET_TEXT_SP);
        addColumnKey(actions,"0","0",()->literal("0"),LensTokens.KEY_ZERO_TEXT_SP);
    }
    private Button addColumnKey(LinearLayout column,String label,String description,Runnable action,int size){
        Button button=new Button(this);button.setText(label);styleKey(button,true,false,size);button.setContentDescription(description);
        button.setEnabled(ready);button.setOnClickListener(v->action.run());column.addView(button,new LinearLayout.LayoutParams(-1,0,1));return button;
    }
    private void renderRegularKeys(){
        String[] rows=numeric||digits?new String[]{"123","456","789","+0."}
            :symbols?new String[]{"1234567890","@#￥%&*-+=","，。？！、：；（）"}
            :new String[]{"qwertyuiop","asdfghjkl","zxcvbnm"};
        for(int y=0;y<rows.length;y++){
            String letters=rows[y];LinearLayout line=row();
            if(!numeric&&!digits&&!symbols&&y==1)line.setPadding(dp(KeyboardLayout.FULL_ROW_INDENT_DP),0,dp(KeyboardLayout.FULL_ROW_INDENT_DP),0);
            for(int x=0;x<letters.length();x++){
                String value=letters.substring(x,x+1),caption=upper&&!chinese?value.toUpperCase(java.util.Locale.ROOT):value;
                addKey(line,caption,()->key(value),1);
            }
            if(y==rows.length-1)addKey(line,"⌫",this::backspace,KeyboardLayout.BACKSPACE_WEIGHT);
        }
    }
    private void renderBottomRow(){
        LinearLayout controls=row();
        if(!numeric){
            if(symbols||digits){
                Button back=addKey(controls,"返回",this::returnToLetters,KeyboardLayout.RETURN_WEIGHT);back.setContentDescription("返回文字键盘");modeButtons.add(back);
            }else{
                modeButtons.add(addKey(controls,"符",()->switchPanel(false),1));
                modeButtons.add(addKey(controls,"123",()->switchPanel(true),1));
            }
            Button space=addKey(controls,"空格",()->{if(chinese&&!symbols&&!digits)engine(0,32," ");else literal(" ");},KeyboardLayout.SPACE_WEIGHT);
            styleKey(space,false,false,LensTokens.KEY_ACTION_TEXT_SP);
            if(!chinese&&!symbols&&!digits)modeButtons.add(addKey(controls,"⇧",()->{upper=!upper;render();},KeyboardLayout.SHIFT_WEIGHT));
            Button language=addKey(controls,"中/英",this::toggleMode,KeyboardLayout.LANGUAGE_WEIGHT);
            language.setContentDescription(chinese?"切换到英文":"切换到中文");modeButtons.add(language);
            EditorInfo info=targetEditorInfo();
            if(sensitive||info==null||!EditorPolicy.chinese(info.inputType,info.imeOptions))language.setVisibility(View.GONE);
        }else addKey(controls,"空格",()->queuedDirect(" "),KeyboardLayout.NUMERIC_SPACE_WEIGHT);
        Button enter=addKey(controls,"↵",this::enter,1);
        styleKey(enter,false,true,LensTokens.KEY_ENTER_TEXT_SP);enter.setContentDescription("换行");modeButtons.add(enter);
    }
    private void renderCandidates() {
        renderAssist();
        if(resetKey!=null)resetKey.setEnabled(ready&&pending==0&&composing);
        if (candidates == null) return;
        candidateRow.setVisibility(chinese&&(composing||pending>0)?View.VISIBLE:View.GONE);
        candidates.removeAllViews();
        previousPage.setVisibility(View.GONE); nextPage.setVisibility(View.GONE);
        if (!chinese || latest == null || pending != 0) return;
        final int token = generation;
        for (int i = 5; i < latest.length; i++) {
            final int index = i - 5;
            Button button = new Button(this); button.setText(latest[i]); styleKey(button,false,false,LensTokens.CANDIDATE_TEXT_SP);button.setPadding(dp(LensTokens.CANDIDATE_PADDING_X_DP),0,dp(LensTokens.CANDIDATE_PADDING_X_DP),0);button.setContentDescription(latest[i]);
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
        if(assistantTabs!=null){
            assistantTabs.setVisibility(allowed?View.VISIBLE:View.GONE);
            for(int i=0;i<assistantModeButtons.size();i++){
                Button tab=assistantModeButtons.get(i);boolean active=assistantRoute.mode().ordinal()==i;
                styleKey(tab,true,active,LensTokens.KEY_TAB_TEXT_SP);tab.setSelected(active);
                tab.setEnabled(allowed&&(i==0||pending==0&&!composing));
            }
        }
        allowed=allowed&&assistantRoute.mode()==Mode.NORMAL;
        assist.setVisibility(allowed?View.VISIBLE:View.GONE);
        AssistSession s=AssistSession.current;
        boolean insert=allowed&&s!=null && s.insertable(info);
        toolbar.setOrientation(insert?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);
        assist.setLayoutParams(new LinearLayout.LayoutParams(insert?-1:0,-2,insert?0:1));
        headerActions.setLayoutParams(new LinearLayout.LayoutParams(insert?-1:-2,-2));
        styleKey(assist,false,true,LensTokens.KEY_ACTION_TEXT_SP);assist.setMinHeight(dp(KeyboardLayout.BAR_HEIGHT_DP));assist.setMinimumHeight(dp(KeyboardLayout.BAR_HEIGHT_DP));
        if(insert){assist.setAutoSizeTextTypeWithDefaults(TextView.AUTO_SIZE_TEXT_TYPE_NONE);assist.setTextSize(LensTokens.ACTION_TEXT_SP);assist.setSingleLine(false);assist.setMaxLines(Integer.MAX_VALUE);assist.setPadding(dp(LensTokens.INSERT_PADDING_X_DP),dp(LensTokens.INSERT_PADDING_Y_DP),dp(LensTokens.INSERT_PADDING_X_DP),dp(LensTokens.INSERT_PADDING_Y_DP));}
        assist.setText(insert?"确认正在与「"+s.result.optJSONObject("person").optString("name")+"」聊天并插入":"建议");
        assist.setContentDescription(assist.getText());
        assist.setEnabled(ready && pending==0 && !composing && (s==null || !s.consuming));
        layoutSwitch.setText(nine?"全键":"九宫");layoutSwitch.setContentDescription(nine?"切换全键盘":"切换九宫格");
        layoutSwitch.setVisibility(chinese&&!numeric?View.VISIBLE:View.GONE);layoutSwitch.setEnabled(ready&&pending==0);
    }
    private void invalidateDraftOnTyping(){if(!statusMessage.isEmpty())showStatus("");if(assistantRoute.target()!=Target.HOST)return;AssistSession s=AssistSession.current;if(s!=null && s.result!=null && !AssistSession.helperShowing && s.matches(getCurrentInputEditorInfo()))AssistSession.clear();}
    private InputConnection targetConnection(){
        if(assistantRoute.target()==Target.HOST)return getCurrentInputConnection();
        if(assistantRoute.target()==Target.INTERNAL&&localEditor!=null&&localEditor.hasFocus()&&localEditor.isEnabled()&&localEditor.isAttachedToWindow()
                &&assistantRoute.snapshot().field==localEditor.getId())return localEditor.connection;
        return null;
    }
    private EditorInfo targetEditorInfo(){
        if(assistantRoute.mode()==Mode.NORMAL)return getCurrentInputEditorInfo();
        EditorInfo info=new EditorInfo();info.inputType=localEditor==null?1:localEditor.getInputType();info.imeOptions=EditorInfo.IME_ACTION_DONE;return info;
    }
    private void finishTargetComposition(){
        KeyboardAssistantPanel.LocalEditor editing=localEditor;
        InputConnection connection=editing!=null?editing.connection:assistantRoute.target()==Target.HOST?getCurrentInputConnection():null;
        if(connection==null)return;
        if(editing!=null)editing.beginLocalEdit();
        try{connection.finishComposingText();}finally{if(editing!=null)editing.endLocalEdit();}
    }
    private void restartTarget(){
        generation++;pending=0;ready=false;composing=false;latest=null;upper=false;symbols=false;digits=false;statusMessage="";
        EditorInfo info=targetEditorInfo();
        sensitive=info!=null&&EditorPolicy.privateField(info.inputType,info.imeOptions);
        numeric=info!=null&&EditorPolicy.numeric(info.inputType);
        chinese=info!=null&&EditorPolicy.chinese(info.inputType,info.imeOptions);
        startSession(generation);render();
    }
    private void focusLocalEditor(KeyboardAssistantPanel.LocalEditor editor){
        if(changingTarget||assistantRoute.mode()==Mode.NORMAL||localEditor==editor)return;
        finishTargetComposition();localEditor=editor;assistantRoute.focus(editor.getId());restartTarget();
    }
    private void blurLocalEditor(KeyboardAssistantPanel.LocalEditor editor){
        if(changingTarget||localEditor!=editor)return;
        finishTargetComposition();assistantRoute.blur(editor.getId());localEditor=null;restartTarget();
    }
    private void changeAssistantMode(Mode next){
        if(assistantPanel==null||next==assistantRoute.mode())return;
        EditorInfo info=getCurrentInputEditorInfo();
        boolean allowed=info!=null&&EditorPolicy.chinese(info.inputType,info.imeOptions)
                &&!(getPackageName().equals(info.packageName)&&AssistSession.helperShowing);
        if(next!=Mode.NORMAL&&(!allowed||pending!=0||composing))return;
        finishTargetComposition();changingTarget=true;
        try{
            if(suggestionPanel!=null&&suggestionPanel.isActive()){suggestionPanel.close();AssistSession.clear();}
            closeCustomerDetails();
            assistantPanel.close();localEditor=null;selectedCustomer=null;assistantRoute.open(next,allowed);
            if(next!=Mode.NORMAL)AssistSession.clear();
            updateAssistantPrivacy();
            if(assistantRoute.mode()!=Mode.NORMAL)assistantPanel.open(next);
        }finally{changingTarget=false;}
        restartTarget();
    }
    private void dismissAssistant(){
        changingTarget=true;
        try{
            // onStartInput may already refer to the next host; only finish the local field here.
            if(localEditor!=null)finishTargetComposition();
            if(suggestionPanel!=null&&suggestionPanel.isActive()){suggestionPanel.close();AssistSession.clear();}
            closeCustomerDetails();
            if(assistantPanel!=null)assistantPanel.close();localEditor=null;selectedCustomer=null;assistantRoute.reset();
            updateAssistantPrivacy();
        }finally{changingTarget=false;}
    }
    private void updateAssistantPrivacy(){
        if(getWindow()==null||getWindow().getWindow()==null)return;
        if(assistantRoute.mode()==Mode.NORMAL)getWindow().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
        else getWindow().getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
    }
    private void openSuggestionPanel(KeyboardAssistantPanel.CustomerSelection customer,NativeClient client,ImeAssistantPanel.Snapshot restored,android.graphics.Bitmap image,String message){
        EditorInfo info=getCurrentInputEditorInfo();
        if(client==null||customer==null||customer.pairId.isEmpty()||info==null||!EditorPolicy.chinese(info.inputType,info.imeOptions)){
            if(image!=null&&!image.isRecycled())image.recycle();showStatus("客户资料未就绪，请刷新后重新选择。");return;
        }
        finishTargetComposition();changingTarget=true;
        try{
            assistantPanel.close();suggestionPanel.close();closeCustomerDetails();localEditor=null;AssistSession.clear();
            selectedCustomer=customer;assistantRoute.open(customer.mode,true);updateAssistantPrivacy();
            AssistSession current=new AssistSession(info);current.client=client;AssistSession.current=current;
            suggestionPanel.open(customer,client,current);
            if(restored!=null)suggestionPanel.restore(restored,image,message);
            else if(image!=null)suggestionPanel.onImage(image,message);
        }finally{changingTarget=false;}
        restartTarget();
    }
    private void showCustomerList(){
        Mode mode=assistantRoute.mode();if(mode==Mode.NORMAL)return;
        finishTargetComposition();changingTarget=true;
        try{
            suggestionPanel.close();closeCustomerDetails();localEditor=null;selectedCustomer=null;AssistSession.clear();assistantRoute.open(mode,true);assistantPanel.open(mode);
        }finally{changingTarget=false;}
        restartTarget();
    }
    private void openCustomerDetails(ImeAssistantPanel.Snapshot snapshot){
        if(snapshot==null||snapshot.customer==null||snapshot.client==null||pending!=0||composing)return;
        finishTargetComposition();changingTarget=true;
        try{
            suggestionPanel.close();assistantPanel.close();localEditor=null;AssistSession.clear();
            detailsReturnDraft=snapshot;detailsClient=snapshot.client;selectedCustomer=snapshot.customer;
            assistantRoute.open(snapshot.customer.mode,true);updateAssistantPrivacy();customerDetailsPanel.open(snapshot.customer,snapshot.client);
        }finally{changingTarget=false;}
        restartTarget();
    }
    private void returnFromCustomerDetails(){
        if(customerDetailsPanel==null||detailsReturnDraft==null)return;
        KeyboardAssistantPanel.CustomerSelection selected=customerDetailsPanel.selection();
        ImeAssistantPanel.Snapshot snapshot=detailsReturnDraft;NativeClient client=detailsClient;
        if(selected==null||!KeyboardAssistantPolicy.selectable(selected.mode,selected.segment)){showCustomerList();return;}
        openSuggestionPanel(selected,client,snapshot,null,"已返回客户资料。请重新核对聊天对象和待提交内容。");
    }
    private void closeCustomerDetails(){
        if(customerDetailsPanel!=null)customerDetailsPanel.close();detailsReturnDraft=null;detailsClient=null;
    }
    private void restoreImageRequest(EditorInfo info){
        if(!imeAlive||!getCurrentInputStarted()||getCurrentInputConnection()==null)return;
        KeyboardImageRequest.Result result=KeyboardImageRequest.take(info);if(result==null)return;
        if(!(result.snapshot instanceof ImeAssistantPanel.Snapshot)){
            if(result.image!=null)result.image.recycle();return;
        }
        final ImeAssistantPanel.Snapshot snapshot=(ImeAssistantPanel.Snapshot)result.snapshot;
        final int token=generation;final String host=info.packageName;final int field=info.fieldId,type=info.inputType;
        NativeClient.IO.execute(()->{
            NativeClient restored=null;KeyboardAssistantPanel.CustomerSelection verified=null;
            try{
                restored=NativeClient.load(this);
                if(restored!=null&&snapshot.client!=null&&restored.endpoint.equals(snapshot.client.endpoint)&&restored.token.equals(snapshot.client.token)){
                    JSONObject person=restored.call("library/people/"+snapshot.customer.id,null);
                    verified=new KeyboardAssistantPanel.CustomerSelection(snapshot.customer.mode,person);
                    if(!verified.pairId.equals(snapshot.customer.pairId)||!KeyboardAssistantPolicy.selectable(verified.mode,verified.segment))verified=null;
                }
            }catch(Exception ignored){verified=null;}
            final NativeClient client=restored;final KeyboardAssistantPanel.CustomerSelection customer=verified;
            main.post(()->{
                EditorInfo current=getCurrentInputEditorInfo();
                if(!imeAlive||!getCurrentInputStarted()||getCurrentInputConnection()==null||token!=generation||current==null||!host.equals(current.packageName)||field!=current.fieldId||type!=current.inputType||pending!=0||composing){
                    if(result.image!=null&&!result.image.isRecycled())result.image.recycle();return;
                }
                if(customer==null){if(result.image!=null&&!result.image.isRecycled())result.image.recycle();showStatus("账户或客户资料已变化，请重新选择客户和图片。");return;}
                openSuggestionPanel(customer,client,snapshot,result.image,result.message);
            });
        });
    }
    private void insertFromPanel(AssistSession current,String draft){
        EditorInfo info=getCurrentInputEditorInfo();
        if(assistantRoute.mode()==Mode.NORMAL||selectedCustomer==null||current==null||current!=AssistSession.current
                ||!current.alive()||!current.matches(info)||current.result==null||current.consuming
                ||pending!=0||composing||draft.trim().isEmpty()||SystemClock.elapsedRealtime()>=current.deadline
                ||!suggestionPanel.permitsInsertion(current,draft))return;
        final JSONObject result=current.result;
        JSONObject person=result.optJSONObject("person");
        if(person==null||!selectedCustomer.id.equals(person.optString("id"))||!selectedCustomer.pairId.equals(person.optString("pair_id"))
                ||result.isNull("ticket_id")||result.optString("ticket_id").isEmpty())return;
        try{
            current.draft=draft;finishTargetComposition();current.consuming=true;suggestionPanel.setConsuming(true);
            final int token=generation,revision=current.revision;final String context=current.context;
            final Mode mode=assistantRoute.mode();final String customerId=selectedCustomer.id,pairId=selectedCustomer.pairId;
            final JSONObject payload=new JSONObject().put("context",context).put("host",current.host).put("person_id",customerId)
                    .put("pair_id",pairId).put("confirmed",true).put("draft",draft);
            NativeClient.IO.execute(()->{try{
                JSONObject answer=current.client.call("tickets/"+result.optString("ticket_id")+"/consume",payload);
                main.post(()->{
                    if(token!=generation||assistantRoute.mode()!=mode||!current.alive()||current.revision!=revision||current.result!=result
                            ||!current.matches(getCurrentInputEditorInfo())||selectedCustomer==null||!customerId.equals(selectedCustomer.id)
                            ||!pairId.equals(selectedCustomer.pairId)||!draft.equals(current.draft)||pending!=0||composing){
                        if(AssistSession.current==current){current.consuming=false;suggestionPanel.insertionFailed("输入现场已变化，请重新核对并生成建议。",false);}return;
                    }
                    InputConnection hostConnection=getCurrentInputConnection();String confirmedDraft=answer.optString("draft");
                    boolean inserted=false;
                    try{inserted=draft.equals(confirmedDraft)&&hostConnection!=null&&hostConnection.commitText(confirmedDraft,1);}
                    catch(RuntimeException failure){/* Keep the draft; never repeat an uncertain host write. */}
                    if(!inserted){current.consuming=false;suggestionPanel.insertionFailed("未能确认插入，请先检查聊天输入框。编辑稿已暂存，旧插入授权已失效。");return;}
                    if(inserted){AssistSession.feedbackId=answer.optString("analysis_id");AssistSession.feedbackName=selectedCustomer.name;AssistSession.feedbackDraft=confirmedDraft;AssistSession.feedbackClient=current.client;}
                    if(inserted&&suggestionPanel.afterContinuousInsertion()){restartTarget();return;}
                    changeAssistantMode(Mode.NORMAL);showStatus(inserted?"已插入草稿 · 请自行检查并发送":"输入框已关闭，请重新生成建议");
                });
            }catch(Exception failure){main.post(()->{if(AssistSession.current==current&&suggestionPanel.isActive()){
                current.consuming=false;suggestionPanel.insertionFailed("未能确认插入，旧候选已失效。请检查输入框后重新生成。");
            }});}});
        }catch(Exception failure){current.consuming=false;suggestionPanel.insertionFailed("插入授权不可用，请重新生成建议。");}
    }
    private void assistAction(){
        EditorInfo info=getCurrentInputEditorInfo();
        if(assistantRoute.target()!=Target.HOST || info==null || !EditorPolicy.chinese(info.inputType,info.imeOptions) || pending!=0 || composing)return;
        AssistSession s=AssistSession.current;
        if(s!=null && s.insertable(info)){
            final int token=generation;final String context=s.context;final int revision=s.revision;s.consuming=true;renderAssist();
            try {
                JSONObject person=s.result.getJSONObject("person");JSONObject payload=new JSONObject().put("context",context).put("host",s.host).put("person_id",person.getString("id")).put("pair_id",person.getString("pair_id")).put("confirmed",true).put("draft",s.draft);
                String ticket=s.result.getString("ticket_id");
                NativeClient.IO.execute(()->{try{JSONObject answer=s.client.call("tickets/"+ticket+"/consume",payload);main.post(()->{
                    if(token!=generation || assistantRoute.target()!=Target.HOST || !s.alive() || s.revision!=revision || !s.matches(getCurrentInputEditorInfo()) || pending!=0 || composing){if(AssistSession.current==s)AssistSession.clear();renderAssist();return;}
                    InputConnection connection=getCurrentInputConnection();boolean inserted=connection!=null && connection.commitText(answer.optString("draft"),1);
                    if(inserted){AssistSession.feedbackId=answer.optString("analysis_id");AssistSession.feedbackName=s.result.optJSONObject("person").optString("name");AssistSession.feedbackDraft=answer.optString("draft");AssistSession.feedbackClient=s.client;}
                    AssistSession.clear();renderAssist();showStatus(inserted?"已插入草稿 · 请自行检查并发送":"输入框已关闭，请重新生成建议");
                });}catch(Exception e){main.post(()->{if(AssistSession.current==s){AssistSession.clear();renderAssist();showStatus(e.getMessage()==null?"插入失败，请重新分析":e.getMessage());}});}});
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
        keyboard.addView(row, new LinearLayout.LayoutParams(-1,keyRowHeight(false))); return row;
    }
    private Button addKey(LinearLayout row, String label, Runnable action, float weight) {
        Button button = new Button(this); button.setText(label);styleKey(button,label.length()>1 || "⌫⇧符中英↵".contains(label),false,label.length()>1?LensTokens.KEY_ACTION_TEXT_SP:LensTokens.KEY_LETTER_TEXT_SP);
        button.setContentDescription(label.equals("⌫")?"退格":label.equals("⇧")?"切换大写":label);
        button.setEnabled(ready); button.setOnClickListener(view -> action.run());
        row.addView(button, new LinearLayout.LayoutParams(0, -1, weight)); return button;
    }
    private int keyRowHeight(boolean nineKeys){
        float scale=getResources().getConfiguration().fontScale;
        int base=getResources().getConfiguration().orientation==2?KeyboardLayout.LANDSCAPE_ROW_DP:nineKeys?KeyboardLayout.NINE_ROW_DP:KeyboardLayout.FULL_ROW_DP;
        return dp(base+Math.round(Math.min(KeyboardLayout.FONT_GROWTH_MAX_DP,Math.max(0f,scale-1f)*KeyboardLayout.FONT_GROWTH_STEP_DP)));
    }
    private void styleKey(Button button,boolean special,boolean primary,int size){
        button.setFocusable(false);
        button.setAllCaps(false);button.setGravity(Gravity.CENTER);button.setSingleLine(true);button.setHorizontallyScrolling(false);button.setMaxLines(KeyboardLayout.KEY_MAX_LINES);
        button.setPadding(dp(LensTokens.KEY_PADDING_X_DP),0,dp(LensTokens.KEY_PADDING_X_DP),0);button.setMinWidth(0);button.setMinimumWidth(0);button.setMinHeight(0);button.setMinimumHeight(0);
        button.setTypeface(Typeface.create(LensTokens.FONT_KEY,Typeface.NORMAL));button.setIncludeFontPadding(false);button.setLineSpacing(0,1);
        button.setTextSize(size);button.setAutoSizeTextTypeUniformWithConfiguration(LensTokens.KEY_AUTOSIZE_MIN_SP,size,LensTokens.KEY_AUTOSIZE_STEP_SP,TypedValue.COMPLEX_UNIT_SP);
        StateListDrawable states=new StateListDrawable();
        states.addState(new int[]{-android.R.attr.state_enabled},LensStyle.shape(this,LensStyle.DISABLED,LensTokens.KEY_SURFACE_RADIUS_DP,false));
        states.addState(new int[]{},LensStyle.shape(this,primary?LensStyle.GREEN:special?LensStyle.TINT:LensStyle.SURFACE,LensTokens.KEY_SURFACE_RADIUS_DP,!primary));
        button.setBackground(new RippleDrawable(ColorStateList.valueOf(LensTokens.KEY_PRESSED),new InsetDrawable(states,dp(LensTokens.KEY_INSET_X_DP),dp(LensTokens.KEY_INSET_Y_DP),dp(LensTokens.KEY_INSET_X_DP),dp(LensTokens.KEY_INSET_Y_DP)),null));
        button.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{LensStyle.MUTED,primary?LensStyle.SURFACE:LensStyle.INK}));
        button.setStateListAnimator(null);button.setElevation(0);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
