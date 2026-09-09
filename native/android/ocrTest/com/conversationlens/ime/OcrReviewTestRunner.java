package com.conversationlens.ime;
import android.app.*;
import android.content.Intent;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import java.util.ArrayList;

/** Isolated app UI with synthetic text. No server, real account, image or model. */
public class OcrReviewTestRunner extends Instrumentation {
    static void check(boolean value){if(!value)throw new AssertionError("OCR review UI contract");}
    static <T> void collect(View v,Class<T> type,ArrayList<T> list){if(type.isInstance(v))list.add(type.cast(v));if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)collect(((ViewGroup)v).getChildAt(i),type,list);}
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle result=new Bundle();AssistantActivity activity=null;try{
        runOnMainSync(()->{EditorInfo editor=new EditorInfo();editor.packageName="com.synthetic.review";editor.inputType=1;AssistSession.current=new AssistSession(editor);});
        activity=(AssistantActivity)startActivitySync(new Intent(getTargetContext(),AssistantActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));final AssistantActivity target=activity;final AlertDialog[] shown={null};
        runOnMainSync(()->{
            EditText transcript=target.findViewById(2103);transcript.setText("待核对：合成原文");
            AlertDialog dialog=target.reviewOcr("待核对：12:00\n对方（待核对）：明夭再聊\n我（待核对）：好的");shown[0]=dialog;
        });
        waitForIdleSync();
        runOnMainSync(()->{
            AlertDialog dialog=shown[0];EditText transcript=target.findViewById(2103);
            check((dialog.getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0);
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();check(dialog.isShowing());check(transcript.getText().toString().contains("待核对"));
            ArrayList<EditText> edits=new ArrayList<>();ArrayList<Spinner> speakers=new ArrayList<>();
            collect(dialog.getWindow().getDecorView(),EditText.class,edits);collect(dialog.getWindow().getDecorView(),Spinner.class,speakers);check(edits.size()==3&&speakers.size()==3);
            edits.get(1).setText("明天再聊");speakers.get(0).setSelection(3);speakers.get(1).setSelection(2);speakers.get(2).setSelection(1);
        });
        waitForIdleSync();
        runOnMainSync(()->{
            shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick();check(!shown[0].isShowing());
            EditText transcript=target.findViewById(2103);check(transcript.getText().toString().equals("对方：明天再聊\n我：好的"));
            ArrayList<CheckBox> checks=new ArrayList<>();collect(target.getWindow().getDecorView(),CheckBox.class,checks);check(checks.stream().noneMatch(CheckBox::isChecked));
            AlertDialog cancel=target.reviewOcr("待核对：另一片段");cancel.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();check(transcript.getText().toString().equals("对方：明天再聊\n我：好的"));
            shown[0]=target.reviewOcr("待核对：过期片段");AssistSession.current.invalidate();
        });
        waitForIdleSync();
        runOnMainSync(()->{shown[0].getButton(AlertDialog.BUTTON_POSITIVE).performClick();check(shown[0].isShowing());shown[0].dismiss();});
        result.putString("review_ui","PASS");result.putString("coverage","unconfirmed-block,correction,speaker,exclude,manual-approval,cancel,stale-context,secure-window");finish(Activity.RESULT_OK,result);
    }catch(Throwable e){result.putString("review_ui","FAIL");result.putString("reason",e.getClass().getSimpleName());finish(Activity.RESULT_CANCELED,result);}finally{if(activity!=null){final AssistantActivity a=activity;runOnMainSync(()->a.finish());}runOnMainSync(AssistSession::clear);}}
}
