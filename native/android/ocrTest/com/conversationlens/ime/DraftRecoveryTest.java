package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.view.inputmethod.EditorInfo;
import org.json.JSONObject;

/** Actual product panel and Editable, with no network/client credential access. */
final class DraftRecoveryTest {
    static void run(Instrumentation runner) {
        Bundle report=new Bundle();final Throwable[] failure={null};final int[] checks={0};
        SetupActivity activity=(SetupActivity)runner.startActivitySync(new Intent(runner.getTargetContext(),SetupActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        runner.runOnMainSync(()->{
            ImeAssistantPanel panel=null;
            try{
                if(AssistSession.current!=null)throw new AssertionError("Existing session");
                EditorInfo origin=new EditorInfo();origin.packageName="com.synthetic.recovery";origin.fieldId=1;origin.inputType=1;
                AssistSession session=new AssistSession(origin);AssistSession.current=session;
                // Panel uses client identity only; session.client remains null to disable cancel IO.
                NativeClient client=new NativeClient("http://127.0.0.1:1","synthetic");
                JSONObject person=new JSONObject().put("id","synthetic-person").put("pair_id","synthetic-pair").put("name","合成恢复客户").put("platform","微信").put("segment","MAINTAIN");
                KeyboardAssistantPanel.Listener editors=new KeyboardAssistantPanel.Listener(){
                    public void onEditorFocused(KeyboardAssistantPanel.LocalEditor e){}
                    public void onEditorBlurred(KeyboardAssistantPanel.LocalEditor e){}
                    public void onEditorSelectionChanged(KeyboardAssistantPanel.LocalEditor e){}
                    public boolean canSubmitEditor(){return true;}
                    public void onCustomerSelected(KeyboardAssistantPanel.CustomerSelection c){}
                    public void onSelectionCleared(){}
                    public void onLoginRequested(){}
                };
                ImeAssistantPanel.Listener listener=new ImeAssistantPanel.Listener(){
                    public void onBackToCustomers(){}
                    public void onInsertRequested(AssistSession s,String d){throw new AssertionError("Unexpected insertion");}
                    public void onImageRequested(ImeAssistantPanel.Snapshot s){}
                    public void onCaptureRequested(ImeAssistantPanel.Snapshot s){}
                    public void onCustomerDetailsRequested(ImeAssistantPanel.Snapshot s){}
                };
                panel=new ImeAssistantPanel(activity,editors,listener);activity.setContentView(panel);
                panel.open(new KeyboardAssistantPanel.CustomerSelection(KeyboardAssistantPolicy.Mode.MAINTAIN,person),client,session);
                JSONObject result=new JSONObject().put("ticket_id","synthetic-ticket").put("candidates",new org.json.JSONArray().put(new JSONObject().put("text","原候选").put("label","合成")));
                java.lang.reflect.Method show=ImeAssistantPanel.class.getDeclaredMethod("showResult",JSONObject.class);show.setAccessible(true);
                java.lang.reflect.Field draftField=ImeAssistantPanel.class.getDeclaredField("draft");draftField.setAccessible(true);
                java.lang.reflect.Field recovery=ImeAssistantPanel.class.getDeclaredField("recoveryDraft");recovery.setAccessible(true);
                java.lang.reflect.Field insert=ImeAssistantPanel.class.getDeclaredField("insert");insert.setAccessible(true);
                session.result=result;show.invoke(panel,result);
                KeyboardAssistantPanel.LocalEditor draft=(KeyboardAssistantPanel.LocalEditor)draftField.get(panel);
                draft.setText("本人改过的合成编辑稿");panel.setConsuming(true);panel.insertionFailed("合成丢失响应");
                require(session.result==null,"Old authority revoked",checks);
                require(insert.get(panel)==null,"No old insert button",checks);
                draft=(KeyboardAssistantPanel.LocalEditor)draftField.get(panel);
                require(draft.getText().toString().equals("本人改过的合成编辑稿"),"Edited text retained",checks);
                require(!session.insertable(origin),"Retained text is not insertion authority",checks);
                draft.setText("继续修改的暂存稿");require(recovery.get(panel).equals("继续修改的暂存稿"),"Recovery draft remains editable",checks);
                session.result=result;show.invoke(panel,result);
                android.view.View button=find(panel,"恢复上次编辑稿（请重新核对）");require(button!=null,"Explicit recovery control",checks);button.performClick();
                require(((KeyboardAssistantPanel.LocalEditor)draftField.get(panel)).getText().toString().equals("继续修改的暂存稿"),"User restores edited text",checks);
                panel.insertionFailed("合成现场变化",false);
                require(draftField.get(panel)==null&&recovery.get(panel).equals(""),"Context change clears draft",checks);
                panel.close();require(recovery.get(panel).equals(""),"Exit clears recovery",checks);
            }catch(Throwable e){failure[0]=e;}
            finally{if(panel!=null)panel.close();AssistSession.clear();activity.finish();}
        });
        report.putString("draft_recovery",failure[0]==null?"PASS":"FAIL");report.putInt("checks",checks[0]);
        report.putString("scope","Real panel/Editable/authority/recovery control; host commitText and network loss require end-to-end fixture");
        if(failure[0]!=null)report.putString("reason",failure[0].toString());
        runner.finish(failure[0]==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,report);
    }
    private static void require(boolean condition,String label,int[] checks){checks[0]++;if(!condition)throw new AssertionError(label);}
    private static android.view.View find(android.view.View view,String label){
        if(view instanceof android.widget.Button&&label.contentEquals(((android.widget.Button)view).getText()))return view;
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++){android.view.View found=find(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }
}
