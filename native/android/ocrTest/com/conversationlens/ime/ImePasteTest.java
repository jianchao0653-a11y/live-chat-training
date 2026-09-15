package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.text.Editable;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextWatcher;
import android.text.style.StyleSpan;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

/** Real Android TextView paste API in an owned synthetic activity, not a long-press UI test. */
final class ImePasteTest {
    private static final int LIMIT=4000;
    private final Instrumentation runner;
    private final Bundle result=new Bundle();
    private final JSONArray cases=new JSONArray();
    private final String clipboardLabel="lens-synthetic-paste-"+UUID.randomUUID();
    private SetupActivity activity;
    private ImeAssistantPanel panel;
    private KeyboardAssistantPanel.LocalEditor editor;
    private AssistSession session;
    private ClipboardManager clipboard;
    private boolean clipboardWritten;
    private int checks,limitMessages;
    private String step="start";

    private ImePasteTest(Instrumentation runner){this.runner=runner;}
    static void run(Instrumentation runner){new ImePasteTest(runner).run();}

    private void require(boolean condition,String name){checks++;if(!condition)throw new AssertionError(name);}
    private void mainStep(String name,Runnable action){
        step=name;final Throwable[] failure={null};
        runner.runOnMainSync(()->{try{action.run();}catch(Throwable error){failure[0]=error;}});
        if(failure[0]!=null)throw new IllegalStateException(name,failure[0]);
        runner.waitForIdleSync();
    }
    private static void texts(View view,ArrayList<TextView> found){
        if(view instanceof TextView)found.add((TextView)view);
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)texts(((ViewGroup)view).getChildAt(i),found);
    }
    private static String repeated(int count){StringBuilder text=new StringBuilder(count);for(int i=0;i<count;i++)text.append('甲');return text.toString();}
    private static String negativeTail(int length){return repeated(length-4)+"不要发送";}
    private static boolean wellFormedUtf16(CharSequence value){
        for(int i=0;i<value.length();i++){
            char c=value.charAt(i);
            if(Character.isHighSurrogate(c)){if(++i>=value.length()||!Character.isLowSurrogate(value.charAt(i)))return false;}
            else if(Character.isLowSurrogate(c))return false;
        }
        return true;
    }

    private void setup(){
        // Do not load an account, reuse an existing assistant session, or instantiate a client.
        mainStep("require_no_existing_assistant",()->require(AssistSession.current==null,"Existing assistant session must be closed before synthetic paste QA"));
        step="start_synthetic_host";
        activity=(SetupActivity)runner.startActivitySync(new Intent(runner.getTargetContext(),SetupActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        mainStep("attach_actual_product_panel",()->{
            try{
                activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
                EditorInfo origin=new EditorInfo();origin.packageName="com.synthetic.paste";origin.fieldId=1001;origin.inputType=1;
                session=new AssistSession(origin);AssistSession.current=session;
                JSONObject person=new JSONObject().put("id","synthetic-paste-customer").put("pair_id","synthetic-paste-pair")
                    .put("name","合成粘贴客户").put("platform","微信").put("segment","MAINTAIN");
                KeyboardAssistantPanel.Listener editors=new KeyboardAssistantPanel.Listener(){
                    public void onEditorFocused(KeyboardAssistantPanel.LocalEditor value){}
                    public void onEditorBlurred(KeyboardAssistantPanel.LocalEditor value){}
                    public void onEditorSelectionChanged(KeyboardAssistantPanel.LocalEditor value){}
                    public boolean canSubmitEditor(){return true;}
                    public void onCustomerSelected(KeyboardAssistantPanel.CustomerSelection value){throw new AssertionError("Unexpected customer action");}
                    public void onSelectionCleared(){throw new AssertionError("Unexpected customer action");}
                    public void onLoginRequested(){throw new AssertionError("No login in paste QA");}
                };
                ImeAssistantPanel.Listener actions=new ImeAssistantPanel.Listener(){
                    public void onBackToCustomers(){throw new AssertionError("Unexpected navigation");}
                    public void onInsertRequested(AssistSession value,String draft){throw new AssertionError("No host insertion in paste QA");}
                    public void onImageRequested(ImeAssistantPanel.Snapshot value){throw new AssertionError("No image picker in paste QA");}
                    public void onCaptureRequested(ImeAssistantPanel.Snapshot value){throw new AssertionError("No capture in paste QA");}
                    public void onCustomerDetailsRequested(ImeAssistantPanel.Snapshot value){throw new AssertionError("No customer requests in paste QA");}
                };
                panel=new ImeAssistantPanel(activity,editors,actions);
                activity.setContentView(panel);
                panel.open(new KeyboardAssistantPanel.CustomerSelection(KeyboardAssistantPolicy.Mode.MAINTAIN,person),null,session);
                editor=panel.findViewById(4301);
                require(editor!=null,"Actual reply LocalEditor 4301 must exist");
                require(session.client==null,"Synthetic session must have no network client");
                ArrayList<TextView> labels=new ArrayList<>();texts(panel,labels);int watched=0;
                for(TextView label:labels)if(!(label instanceof KeyboardAssistantPanel.LocalEditor)&&label.getAccessibilityLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE){
                    watched++;
                    label.addTextChangedListener(new TextWatcher(){
                        public void beforeTextChanged(CharSequence text,int start,int count,int after){}
                        public void onTextChanged(CharSequence text,int start,int before,int count){}
                        public void afterTextChanged(Editable text){if(text.toString().contains("本次输入会超过 4000 个字符，未加入")&&text.toString().contains("原文字与所选内容已保留"))limitMessages++;}
                    });
                }
                require(watched==1,"One actual product status label must be observed");
                clipboard=(ClipboardManager)activity.getSystemService(Context.CLIPBOARD_SERVICE);
                require(clipboard!=null,"Clipboard service must be available");
            }catch(Exception error){throw new IllegalStateException(error);}
        });
        mainStep("focus_actual_product_editor",()->require(editor.requestFocus(),"Actual LocalEditor must accept focus"));
        mainStep("verify_foreground_clipboard_reader",()->{
            require(activity.hasWindowFocus()&&editor.isFocused()&&editor.isAttachedToWindow()&&editor.isShown(),"Paste target must be attached and focused in a foreground window");
            require((activity.getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0,"Synthetic window must remain protected");
        });
    }

    private void original(CharSequence value,int start,int end){
        require(value.length()<100,"setText may prepare only a short synthetic original");
        editor.setText(value,TextView.BufferType.SPANNABLE);
        require(editor.requestFocus(),"Preparation must preserve editor focus");
        editor.setSelection(start,end);
        require(editor.getText().toString().equals(value.toString()),"Short original must be installed without truncation");
    }
    private void paste(String name,CharSequence text,String expected,boolean rejected){
        require(editor.isFocused()&&activity.hasWindowFocus(),"Paste must run on the focused foreground editor");
        int before=editor.length(),messagesBefore=limitMessages;
        // Write only our new synthetic clip. Never inspect or retain the previous clipboard.
        clipboard.setPrimaryClip(ClipData.newPlainText(clipboardLabel,text));clipboardWritten=true;
        boolean handled=editor.onTextContextMenuItem(android.R.id.paste);
        require(handled,"TextView must dispatch its real paste action");
        require(editor.getText().toString().equals(expected),"Entire Editable must match the expected paste result: "+name);
        require(wellFormedUtf16(editor.getText()),"Paste must not leave a lone surrogate: "+name);
        if(rejected)require(limitMessages>messagesBefore,"A fresh product overflow status must be emitted: "+name);
        require(session.client==null&&session.result==null,"Paste must not configure network or generated content");
        try{cases.put(new JSONObject().put("case",name).put("sourceUtf16",text.length()).put("beforeUtf16",before)
            .put("afterUtf16",editor.length()).put("rejectedWhole",rejected).put("actionHandled",handled).put("status","PASS"));}
        catch(Exception error){throw new IllegalStateException(error);}
    }
    private void scenarios(){
        mainStep("empty_plain_negative_tail_overflow",()->{
            original("",0,0);paste("empty_4001_negative_tail",negativeTail(4001),"",true);
        });
        mainStep("plain_selection_overflow",()->{
            String text="前缀：不要发送。后缀";int start=text.indexOf("不要发送"),end=start+4;
            original(text,start,end);
            paste("plain_selection_preserved",negativeTail(LIMIT+1-(text.length()-(end-start))),text,true);
            require(editor.getText().toString().contains("不要发送。后缀"),"Original negative instruction and suffix must survive rejection");
        });
        mainStep("styled_selection_overflow",()->{
            String text="前缀：不要发送。后缀";int start=text.indexOf("不要发送"),end=start+4;
            SpannableString original=new SpannableString(text);
            original.setSpan(new StyleSpan(Typeface.BOLD),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            original(original,start,end);
            SpannableString source=new SpannableString(negativeTail(LIMIT+1-(text.length()-(end-start))));
            source.setSpan(new StyleSpan(Typeface.ITALIC),source.length()-4,source.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            paste("spanned_selection_preserved",source,text,true);
            Spanned after=editor.getText();StyleSpan[] spans=after.getSpans(0,after.length(),StyleSpan.class);
            int bold=0;
            for(StyleSpan span:spans){
                require(span.getStyle()!=Typeface.ITALIC,"Rejected clipboard styling must not enter the original");
                if(span.getStyle()==Typeface.BOLD){bold++;require(after.getSpanStart(span)==start&&after.getSpanEnd(span)==end,"Original selected negative span bounds must survive");}
            }
            require(bold==1,"Original selected negative style must remain exactly once");
            // TextView may move the selection after rejection; selecting again is explicit.
            editor.setSelection(start,end);
            paste("valid_paste_after_rejection","稍后再聊",text.substring(0,start)+"稍后再聊"+text.substring(end),false);
        });
        mainStep("exact_plain_limit",()->{
            String before="原始短稿";original(before,0,before.length());paste("exact_4000_plain",negativeTail(4000),negativeTail(4000),false);
            require(editor.getText().toString().endsWith("不要发送"),"Accepted boundary paste must retain its negative tail");
        });
        mainStep("utf16_exact_then_overflow",()->{
            original("",0,0);String exact=repeated(3998)+"\uD83D\uDE00";
            paste("exact_4000_with_emoji",exact,exact,false);
            editor.setSelection(editor.length());
            paste("emoji_append_rejected_without_damage","\uD83D\uDE00",exact,true);
            editor.setSelection(editor.length()-2,editor.length());
            paste("valid_emoji_replacement_after_rejection","\uD83D\uDE42",repeated(3998)+"\uD83D\uDE42",false);
        });
        mainStep("utf16_one_unit_over_limit",()->{
            original("",0,0);paste("4001_emoji_not_split",repeated(3999)+"\uD83D\uDE00","",true);
        });
    }
    private void run(){
        boolean passed=false;
        result.putString("method","TextView.onTextContextMenuItem(android.R.id.paste), actual synthetic ClipData");
        result.putString("scope","Actual Android TextView paste and product InputFilter/status; no long-press UI, IME-window touches, Toast pixels, OCR or model quality");
        result.putBoolean("realTouches",false);result.putBoolean("oldClipboardRead",false);result.putBoolean("networkClientConfigured",false);
        try{setup();scenarios();passed=true;}
        catch(Throwable error){
            result.putString("failed_step",step);Throwable cause=error.getCause()==null?error:error.getCause();
            result.putString("reason",cause.getClass().getSimpleName()+": "+cause.getMessage());
        }finally{
            try{
                mainStep("cleanup_owned_paste_state",()->{
                    try{
                        if(clipboardWritten){
                            if(Build.VERSION.SDK_INT>=28){clipboard.clearPrimaryClip();result.putString("clipboard_cleanup","cleared");}
                            else{clipboard.setPrimaryClip(ClipData.newPlainText(clipboardLabel,""));result.putString("clipboard_cleanup","synthetic_empty_clip_api26_27");}
                        }else result.putString("clipboard_cleanup","not_written");
                    }finally{
                        try{if(panel!=null)panel.close();}
                        finally{if(session!=null&&AssistSession.current==session)AssistSession.current=null;if(activity!=null)activity.finish();}
                    }
                });
                result.putBoolean("cleanupPassed",true);
            }catch(Throwable error){passed=false;result.putBoolean("cleanupPassed",false);result.putString("cleanup_error",error.getClass().getSimpleName());}
            result.putString("paste_contract",passed?"PASS":"FAIL");result.putInt("checks",checks);result.putInt("cases",cases.length());
            result.putString("cases_json",cases.toString());runner.finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }
    }
}
