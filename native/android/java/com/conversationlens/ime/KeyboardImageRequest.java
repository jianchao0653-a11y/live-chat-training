package com.conversationlens.ime;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.inputmethod.EditorInfo;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.UUID;

/** User-started system handoffs. Pixels and form drafts never enter a Bundle or file. */
final class KeyboardImageRequest {
    private static final long LIFETIME=120000;
    private static final Handler main=new Handler(Looper.getMainLooper());
    private static final LinkedHashSet<Runnable> listeners=new LinkedHashSet<>();
    private static Pending current;
    private static final class Pending {
        final String id=UUID.randomUUID().toString(),host;
        final int fieldId,inputType;
        final boolean capture;
        long expires=SystemClock.elapsedRealtime()+LIFETIME;
        final Object snapshot;
        boolean complete,bridgeHidden;
        Bitmap image;
        String message="";
        Runnable completion,expiry,stopCapture;
        Pending(String host,int fieldId,int inputType,Object snapshot,boolean capture){this.host=host;this.fieldId=fieldId;this.inputType=inputType;this.snapshot=snapshot;this.capture=capture;}
    }
    static final class Result {
        final Object snapshot;
        final Bitmap image;
        final String message;
        final boolean capture;
        Result(Pending p){snapshot=p.snapshot;image=p.image;message=p.message;capture=p.capture;p.image=null;}
    }
    static void begin(Context context,String host,int fieldId,int inputType,Object snapshot){
        start(context,host,fieldId,inputType,snapshot,false);
    }
    static void beginCapture(Context context,String host,int fieldId,int inputType,Object snapshot){
        KeyboardCaptureService.prepareNotificationPermission(context);
        start(context,host,fieldId,inputType,snapshot,true);
    }
    private static void start(Context context,String host,int fieldId,int inputType,Object snapshot,boolean capture){
        cancel();
        if(host==null||snapshot==null)throw new IllegalArgumentException("请先选择客户并准备资料");
        Pending p=new Pending(host,fieldId,inputType,snapshot,capture);current=p;schedule(p,LIFETIME);
        try{
            context.startActivity(new Intent(context,capture?ImeCapturePermissionActivity.class:ImeImagePickerActivity.class)
                .putExtra("request",p.id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS));
        }catch(RuntimeException e){cancel();throw e;}
    }
    static boolean pending(){
        if(current!=null&&SystemClock.elapsedRealtime()>=current.expires){if(current.complete)cancel();else timedOut(current);}
        return current!=null;
    }
    static boolean isCapture(){return pending()&&current.capture;}
    static boolean matchesOrigin(EditorInfo editor){return pending()&&matches(current,editor);}
    static boolean readyFor(EditorInfo editor){return pending()&&current.complete&&matches(current,editor);}
    static void addCompletionListener(Runnable listener){if(listener!=null)listeners.add(listener);}
    static void removeCompletionListener(Runnable listener){listeners.remove(listener);}
    private static boolean matches(Pending p,EditorInfo editor){
        return editor!=null&&p.host.equals(editor.packageName)&&p.fieldId==editor.fieldId&&p.inputType==editor.inputType&&EditorPolicy.chinese(editor.inputType,editor.imeOptions);
    }
    private static void schedule(Pending p,long delay){
        if(p.expiry!=null)main.removeCallbacks(p.expiry);
        p.expires=SystemClock.elapsedRealtime()+delay;
        p.expiry=()->{if(current==p){if(p.complete)cancel();else timedOut(p);}};
        main.postDelayed(p.expiry,delay);
    }
    private static void notifyComplete(Pending p){
        run(p.completion);
        // The Activity's observer is independent from the IME's lifecycle observer.
        for(Runnable listener:new ArrayList<>(listeners))run(listener);
    }
    private static void run(Runnable callback){
        if(callback==null)return;
        if(Looper.myLooper()!=Looper.getMainLooper()){main.post(()->run(callback));return;}
        try{callback.run();}catch(RuntimeException ignored){}
    }
    private static void timedOut(Pending p){
        recycle(p.image);p.image=null;p.message=(p.capture?"截图授权":"选图")+"已超时，请重新操作或粘贴文字；返回后需核对客户";
        p.complete=true;schedule(p,30000);
        Runnable stop=p.stopCapture;p.stopCapture=null;run(stop);notifyComplete(p);
    }
    static boolean accepts(String id){return pending()&&current.id.equals(id)&&!current.complete;}
    static boolean acceptsCapture(String id){return accepts(id)&&current.capture;}
    static void captureBridgeHidden(String id){if(acceptsCapture(id))current.bridgeHidden=true;}
    static boolean captureMayProceed(String id){return acceptsCapture(id)&&current.bridgeHidden;}
    static boolean attachCaptureStop(String id,Runnable stop){
        if(!acceptsCapture(id))return false;current.stopCapture=stop;return true;
    }
    static void detachCaptureStop(String id,Runnable stop){
        if(current!=null&&current.id.equals(id)&&current.stopCapture==stop)current.stopCapture=null;
    }
    static void observe(String id,Runnable completion){
        if(!pending()||!current.id.equals(id))return;
        current.completion=completion;if(current.complete)completion.run();
    }
    static void unobserve(String id,Runnable completion){
        if(current!=null&&current.id.equals(id)&&current.completion==completion)current.completion=null;
    }
    static void complete(String id,Bitmap image,String message){
        if(Looper.myLooper()!=Looper.getMainLooper()){main.post(()->complete(id,image,message));return;}
        if(!accepts(id)){recycle(image);return;}
        Pending p=current;p.image=image;p.message=message;p.complete=true;
        Runnable stop=p.stopCapture;p.stopCapture=null;
        schedule(p,30000);run(stop);notifyComplete(p);
    }
    static Result take(EditorInfo editor){
        if(!readyFor(editor))return null;
        Pending p=current;
        current=null;if(p.expiry!=null)main.removeCallbacks(p.expiry);p.completion=null;return new Result(p);
    }
    static void cancel(){
        Pending p=current;current=null;if(p==null)return;
        if(p.expiry!=null)main.removeCallbacks(p.expiry);
        recycle(p.image);p.image=null;
        Runnable stop=p.stopCapture;p.stopCapture=null;run(stop);run(p.completion);p.completion=null;
    }
    private static void recycle(Bitmap bitmap){if(bitmap!=null&&!bitmap.isRecycled())bitmap.recycle();}
}
