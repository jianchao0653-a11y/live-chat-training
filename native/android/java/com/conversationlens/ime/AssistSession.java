package com.conversationlens.ime;

import android.view.inputmethod.EditorInfo;
import android.os.SystemClock;
import org.json.JSONObject;
import java.util.UUID;

/** Main-thread-only, transient authority. Never persist chat, image, ticket or draft. */
final class AssistSession {
    static AssistSession current;
    static boolean helperShowing;
    String context=UUID.randomUUID().toString();
    final String host;
    final int fieldId, inputType;
    final long started=SystemClock.elapsedRealtime();
    NativeClient client;
    JSONObject result;
    String draft="";
    long deadline;
    int revision;
    boolean consuming;
    android.graphics.Bitmap image;
    String captureMessage="";
    static String feedbackId, feedbackName, feedbackDraft;
    static NativeClient feedbackClient;
    static void clearFeedback(){feedbackId=null;feedbackName=null;feedbackDraft=null;feedbackClient=null;}
    AssistSession(EditorInfo editor){host=editor.packageName;fieldId=editor.fieldId;inputType=editor.inputType;}
    boolean matches(EditorInfo editor){return editor!=null && host.equals(editor.packageName) && fieldId==editor.fieldId && inputType==editor.inputType && EditorPolicy.chinese(editor.inputType,editor.imeOptions);}
    boolean alive(){return current==this && SystemClock.elapsedRealtime()-started<15*60000;}
    boolean insertable(EditorInfo editor){return alive() && matches(editor) && result!=null && !draft.trim().isEmpty() && SystemClock.elapsedRealtime()<deadline && !consuming;}
    void invalidate(){
        final String oldContext=context;context=UUID.randomUUID().toString();
        revision++;result=null;draft="";deadline=0;
        NativeClient c=client;
        if(c!=null)NativeClient.IO.execute(()->{try{c.call("cancel",new JSONObject().put("context",oldContext));}catch(Exception ignored){}});
    }
    void clearImage(){if(image!=null){image.recycle();image=null;}}
    static void clear(){AssistSession s=current;current=null;if(s!=null){s.invalidate();s.clearImage();}}
}
