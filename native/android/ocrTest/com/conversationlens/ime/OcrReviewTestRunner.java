package com.conversationlens.ime;
import android.app.*;
import android.content.Intent;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import java.util.ArrayList;

/** Isolated synthetic UI contracts; no server, real account, image or model. */
public class OcrReviewTestRunner extends Instrumentation {
    private String step="start",lastAssertion="";
    private int assertions;
    private void check(boolean value,String name){
        lastAssertion=name;assertions++;
        if(!value)throw new AssertionError(name);
    }
    static <T> void collect(View v,Class<T> type,ArrayList<T> list){
        if(type.isInstance(v))list.add(type.cast(v));
        if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)collect(((ViewGroup)v).getChildAt(i),type,list);
    }
    private void mainStep(String name,Runnable action){
        step=name;final Throwable[] failure={null};
        // Instrumentation.SyncRunnable does not catch an assertion from its target.
        // Capture here so the instrumentation thread can finish with a receipt.
        runOnMainSync(()->{try{action.run();}catch(Throwable error){failure[0]=error;}});
        if(failure[0]!=null)throw new RuntimeException("Synthetic review step failed",failure[0]);
        // Dialog.show posts OnShowListener through its Handler. Creation, clicks
        // and assertions are separate steps with the application queue drained.
        waitForIdleSync();
    }
    private void failure(Bundle result,Throwable error){
        result.putString("review_ui","FAIL");result.putString("failed_step",step);
        result.putString("last_assertion",lastAssertion);
        result.putString("reason",(error.getCause()==null?error:error.getCause()).getClass().getSimpleName());
    }
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();AssistantActivity activity=null;
        final AlertDialog[] shown={null};boolean passed=false;
        try{
            mainStep("session",()->{
                EditorInfo editor=new EditorInfo();editor.packageName="com.synthetic.review";editor.inputType=1;
                AssistSession.current=new AssistSession(editor);
            });
            step="start_activity";
            activity=(AssistantActivity)startActivitySync(new Intent(getTargetContext(),AssistantActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            final AssistantActivity target=activity;
            mainStep("correction_show",()->{
                EditText transcript=target.findViewById(2103);transcript.setText("待核对：合成原文");
                shown[0]=target.reviewOcr("非聊天：12:00\n对方：明夭再聊\n我：好的");
            });
            mainStep("correction_edit",()->{
                AlertDialog dialog=shown[0];EditText transcript=target.findViewById(2103);
                check((dialog.getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0,"dialog_secure");
                check((target.getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0,"activity_secure");
                check(dialog.isShowing()&&transcript.getText().toString().equals("待核对：合成原文"),"original_preserved_before_approval");
                ArrayList<EditText> edits=new ArrayList<>();ArrayList<Spinner> speakers=new ArrayList<>();
                collect(dialog.getWindow().getDecorView(),EditText.class,edits);collect(dialog.getWindow().getDecorView(),Spinner.class,speakers);
                check(edits.size()==3&&speakers.isEmpty(),"editable_text_without_role_picker");
                CheckBox unknown=dialog.findViewById(23000),other=dialog.findViewById(23001),self=dialog.findViewById(23002);
                check(!unknown.isChecked()&&!unknown.isEnabled(),"unknown_excluded_and_disabled");
                check(other.isChecked()&&other.isEnabled()&&self.isChecked()&&self.isEnabled(),"known_default_inclusion");
                check(other.getContentDescription().toString().equals("第2条纳入分析"),"inclusion_accessibility");
                EditText correction=dialog.findViewById(22001);correction.setText("明天再聊");self.setChecked(false);
            });
            mainStep("correction_approve",()->shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick());
            mainStep("correction_assert",()->{
                check(!shown[0].isShowing(),"correction_dialog_closed");
                EditText transcript=target.findViewById(2103);
                check(transcript.getText().toString().equals("对方：明天再聊"),"corrected_selected_text_only");
                ArrayList<CheckBox> checks=new ArrayList<>();collect(target.getWindow().getDecorView(),CheckBox.class,checks);
                check(checks.stream().noneMatch(CheckBox::isChecked),"analysis_not_approved");
            });
            // Fixed roles are already selected: one overall approval suffices.
            mainStep("automatic_show",()->shown[0]=target.reviewOcr("对方（待核对）：明天再聊\n我：好的"));
            mainStep("automatic_approve",()->shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick());
            mainStep("automatic_assert",()->{
                check(!shown[0].isShowing(),"automatic_dialog_closed");
                check(((EditText)target.findViewById(2103)).getText().toString().equals("对方：明天再聊\n我：好的"),"default_roles_assembled");
            });
            mainStep("unknown_show",()->shown[0]=target.reviewOcr("非聊天：12:00\n未定位标题"));
            mainStep("unknown_approve",()->shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick());
            mainStep("unknown_assert",()->{
                check(shown[0].isShowing(),"unknown_only_blocked");
                check(((EditText)target.findViewById(2103)).getText().toString().equals("对方：明天再聊\n我：好的"),"unknown_preserves_transcript");
            });
            mainStep("unknown_cancel",()->shown[0].getButton(AlertDialog.BUTTON_NEGATIVE).performClick());
            mainStep("unknown_cancel_assert",()->check(!shown[0].isShowing(),"unknown_dialog_cancelled"));
            mainStep("cancel_show",()->shown[0]=target.reviewOcr("对方：取消的片段"));
            mainStep("cancel_edit",()->((EditText)shown[0].findViewById(22000)).setText("取消的修改"));
            mainStep("cancel_click",()->shown[0].getButton(AlertDialog.BUTTON_NEGATIVE).performClick());
            mainStep("cancel_assert",()->{
                check(!shown[0].isShowing(),"edited_dialog_cancelled");
                check(((EditText)target.findViewById(2103)).getText().toString().equals("对方：明天再聊\n我：好的"),"cancel_preserves_transcript");
            });
            mainStep("stale_show",()->shown[0]=target.reviewOcr("对方：过期片段"));
            mainStep("stale_invalidate",()->AssistSession.current.invalidate());
            mainStep("stale_approve",()->shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick());
            mainStep("stale_assert",()->check(shown[0].isShowing(),"stale_context_blocked"));
            result.putString("review_ui","PASS");
            result.putString("coverage","fixed-sides,no-speaker-picker,default-inclusion,non-chat-exclusion,correction,overall-approval,unknown-block,cancel,stale-context,secure-window");
            passed=true;
        }catch(Throwable error){failure(result,error);}
        finally{
            final AssistantActivity closing=activity;
            try{
                mainStep("cleanup",()->{
                    try{if(shown[0]!=null&&shown[0].isShowing())shown[0].dismiss();}
                    finally{try{if(closing!=null)closing.finish();}finally{AssistSession.clear();}}
                });
            }catch(Throwable error){
                result.putString("cleanup_error",error.getClass().getSimpleName());
                if(passed)failure(result,error);
                passed=false;
            }
        }
        result.putInt("assertions",assertions);
        result.putString("interaction_mode","instrumentation-contract");
        finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
}
