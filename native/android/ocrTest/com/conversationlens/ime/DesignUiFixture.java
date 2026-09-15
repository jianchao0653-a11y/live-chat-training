package com.conversationlens.ime;

import android.app.*;
import android.content.Intent;
import android.os.*;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;

/** Test-APK-only synthetic scene. External ADB performs all dialog interactions. */
final class DesignUiFixture {
    static void run(Instrumentation runner,String action) {
        Bundle result=new Bundle();
        final AssistantActivity[] activity={null};final AlertDialog[] dialog={null};
        boolean passed=false;
        try {
            if(!"ranchu".equals(Build.HARDWARE)&&!"goldfish".equals(Build.HARDWARE))throw new IllegalStateException("Synthetic emulator only");
            if(!"cancel".equals(action)&&!"approve".equals(action))throw new IllegalArgumentException("Unknown synthetic action");
            runner.runOnMainSync(()->{
                EditorInfo editor=new EditorInfo();editor.packageName="com.synthetic.design";editor.inputType=1;
                AssistSession.current=new AssistSession(editor);
            });
            activity[0]=(AssistantActivity)runner.startActivitySync(new Intent(runner.getTargetContext(),AssistantActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            runner.runOnMainSync(()->{
                ((EditText)activity[0].findViewById(2103)).setText("合成原文保留");
                dialog[0]=activity[0].reviewOcr("对方：明天再聊\n我：好的");
            });
            runner.waitForIdleSync();
            long deadline=SystemClock.elapsedRealtime()+180000;
            boolean[] showing={true};
            while(SystemClock.elapsedRealtime()<deadline){
                runner.runOnMainSync(()->showing[0]=dialog[0].isShowing());
                if(!showing[0])break;
                SystemClock.sleep(100);
            }
            if(showing[0])throw new IllegalStateException("External touch sequence timed out");
            final String[] observed={null};final boolean[] secure={false};
            runner.runOnMainSync(()->{
                observed[0]=((EditText)activity[0].findViewById(2103)).getText().toString();
                secure[0]=(activity[0].getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0
                    &&(dialog[0].getWindow().getAttributes().flags&WindowManager.LayoutParams.FLAG_SECURE)!=0;
            });
            String expected="cancel".equals(action)?"合成原文保留":"对方：明天再";
            if(!expected.equals(observed[0])||!secure[0])throw new AssertionError("Synthetic result or secure policy mismatch");
            result.putString("design_touch","PASS");result.putString("action",action);
            result.putString("observed",observed[0]);result.putBoolean("secure",secure[0]);passed=true;
        }catch(Throwable e){result.putString("design_touch","FAIL");result.putString("reason",e.getClass().getSimpleName()+": "+e.getMessage());}
        finally {
            try{runner.runOnMainSync(()->{
                if(dialog[0]!=null&&dialog[0].isShowing())dialog[0].dismiss();
                if(activity[0]!=null)activity[0].finish();AssistSession.clear();
            });}catch(Throwable e){passed=false;result.putString("cleanup_error",e.getClass().getSimpleName());}
        }
        runner.finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
}
