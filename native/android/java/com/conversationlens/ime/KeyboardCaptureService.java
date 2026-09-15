package com.conversationlens.ime;

import android.Manifest;
import android.app.Activity;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.DisplayMetrics;
import android.view.WindowManager;

/** One fresh consent token, one virtual display, one retained frame; no network or files. */
public final class KeyboardCaptureService extends Service {
    private static final String CHANNEL="lens-keyboard-capture",STOP="lens.stop.keyboard.capture";
    private static final int NOTICE=304;
    private static final long TIMEOUT=10000;
    private final Handler main=new Handler(Looper.getMainLooper());
    private MediaProjection projection;
    private MediaProjection.Callback callback;
    private VirtualDisplay display;
    private ImageReader reader;
    private String request;
    private Runnable coordinatorStop;
    private long started;
    private boolean done,receiverRegistered,receiverFailed,contentSized;
    private int rawWidth,rawHeight,density,frameRevision;
    private final BroadcastReceiver screenOff=new BroadcastReceiver(){
        @Override public void onReceive(Context context,Intent intent){finishCapture("锁屏或息屏已停止截图",null);}
    };
    static boolean needsNotificationPermission(Context context){
        return Build.VERSION.SDK_INT>=33&&context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED;
    }
    static void prepareNotificationPermission(Context context){
        NotificationManager manager=(NotificationManager)context.getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL,"键盘单次截图",NotificationManager.IMPORTANCE_LOW));
        NotificationChannel channel=manager.getNotificationChannel(CHANNEL);
        // On API 33 a fresh install reports notifications disabled until runtime
        // permission is granted. That is not proof of a user-disabled channel.
        if(channel==null||channel.getImportance()==NotificationManager.IMPORTANCE_NONE
                ||(!needsNotificationPermission(context)&&!manager.areNotificationsEnabled())){
            throw new IllegalStateException("截图需要可见的停止通知；请在系统设置允许通知，或选择图片、输入文字");
        }
    }
    static void requireVisibleNotification(Context context){
        prepareNotificationPermission(context);
        if(needsNotificationPermission(context)||!((NotificationManager)context.getSystemService(NOTIFICATION_SERVICE)).areNotificationsEnabled()){
            throw new IllegalStateException("截图需要可见的停止通知；请在系统设置允许通知，或选择图片、输入文字");
        }
    }
    static void begin(Context context,String request,int result,Intent permission){
        if(result!=Activity.RESULT_OK||permission==null||!KeyboardImageRequest.acceptsCapture(request))throw new IllegalStateException("截图授权已失效");
        context.startForegroundService(new Intent(context,KeyboardCaptureService.class).putExtra("request",request).putExtra("result",result).putExtra("permission",permission));
    }
    @Override public void onCreate(){
        super.onCreate();IntentFilter filter=new IntentFilter(Intent.ACTION_SCREEN_OFF);
        try{
            if(Build.VERSION.SDK_INT>=33)registerReceiver(screenOff,filter,Context.RECEIVER_NOT_EXPORTED);else registerReceiver(screenOff,filter);
            receiverRegistered=true;
        }catch(RuntimeException failure){receiverFailed=true;}
    }
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null){finishCapture("截图请求未恢复，请重新授权",null);return START_NOT_STICKY;}
        String incoming=intent.getStringExtra("request");
        if(STOP.equals(intent.getAction())){
            if(request==null||request.equals(incoming))finishCapture("已主动停止截图",null);
            return START_NOT_STICKY;
        }
        if(done){
            KeyboardImageRequest.complete(incoming,null,"截图服务已结束，请重新授权或选择图片");stopSelf(startId);return START_NOT_STICKY;
        }
        if(request!=null){
            // A duplicate start may not reuse a token or create another display.
            if(!request.equals(incoming))KeyboardImageRequest.complete(incoming,null,"上一截图仍在停止，请重新授权或选择图片");
            return START_NOT_STICKY;
        }
        if(!KeyboardImageRequest.acceptsCapture(incoming)){stopSelf(startId);return START_NOT_STICKY;}
        request=incoming;started=SystemClock.elapsedRealtime();
        coordinatorStop=()->finishCapture("截图上下文已结束，未保留新画面",null);
        if(!KeyboardImageRequest.attachCaptureStop(request,coordinatorStop)){stopSelf(startId);return START_NOT_STICKY;}
        try{
            if(receiverFailed)throw new IllegalStateException("Screen-off listener unavailable");
            requireVisibleNotification(this);
            PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,KeyboardCaptureService.class).setAction(STOP)
                .setData(Uri.parse("lens-capture-stop:"+request)).putExtra("request",request),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_CANCEL_CURRENT);
            Notification notice=new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.ic_menu_camera)
                .setContentTitle("3 秒后截取一帧画面").setContentText("截取后立即停止；请返回原聊天，图片不会自动上传")
                .setOngoing(true).setOnlyAlertOnce(true).addAction(new Notification.Action.Builder(null,"停止截图",stop).build()).build();
            if(Build.VERSION.SDK_INT>=29)startForeground(NOTICE,notice,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);else startForeground(NOTICE,notice);
            main.postDelayed(()->finishCapture("截图已超时，请重新授权或选择图片",null),TIMEOUT);
            Intent permission=intent.getParcelableExtra("permission");
            if(intent.getIntExtra("result",Activity.RESULT_CANCELED)!=Activity.RESULT_OK||permission==null)throw new IllegalStateException("No fresh consent");
            projection=((MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE)).getMediaProjection(Activity.RESULT_OK,permission);
            if(projection==null)throw new IllegalStateException("No projection");
            callback=new MediaProjection.Callback(){
                @Override public void onStop(){finishCapture("系统已停止截图，请重新授权或选择图片",null);}
                @Override public void onCapturedContentResize(int width,int height){capturedSize(width,height);}
                @Override public void onCapturedContentVisibilityChanged(boolean visible){
                    if(!visible)finishCapture("共享画面已不可见，截图已停止；请返回原聊天重新授权",null);
                }
            };
            projection.registerCallback(callback,main);
            main.postDelayed(this::capture,3000);
        }catch(RuntimeException failure){finishCapture("截图未开始；请检查授权与停止通知，或选择图片、输入文字",null);}
        return START_NOT_STICKY;
    }
    private boolean valid(){
        if(done)return false;
        if(!KeyboardImageRequest.acceptsCapture(request)){finishCapture("截图上下文已失效",null);return false;}
        if(SystemClock.elapsedRealtime()-started>=TIMEOUT){finishCapture("截图已超时，请重新授权或选择图片",null);return false;}
        if(!((PowerManager)getSystemService(POWER_SERVICE)).isInteractive()||((KeyguardManager)getSystemService(KEYGUARD_SERVICE)).isKeyguardLocked()){
            finishCapture("锁屏或息屏已停止截图",null);return false;
        }
        return true;
    }
    private void capture(){
        if(!valid())return;
        if(!KeyboardImageRequest.captureMayProceed(request)){main.postDelayed(this::capture,100);return;}
        try{
            requireVisibleNotification(this);
            WindowManager windows=(WindowManager)getSystemService(WINDOW_SERVICE);
            DisplayMetrics metrics=getResources().getDisplayMetrics();density=metrics.densityDpi;
            if(Build.VERSION.SDK_INT>=30){Rect bounds=windows.getMaximumWindowMetrics().getBounds();rawWidth=bounds.width();rawHeight=bounds.height();}
            else{metrics=new DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(metrics);rawWidth=metrics.widthPixels;rawHeight=metrics.heightPixels;density=metrics.densityDpi;}
            int[] size=scaled(rawWidth,rawHeight);contentSized=Build.VERSION.SDK_INT<34;
            installReader(size[0],size[1]);
            display=projection.createVirtualDisplay("LensKeyboardSingleFrame",size[0],size[1],density,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader.getSurface(),null,main);
        }catch(RuntimeException|OutOfMemoryError failure){finishCapture("本次画面无法截取，请重新授权或选择图片",null);}
    }
    private static int[] scaled(int width,int height){
        if(width<=0||height<=0)throw new IllegalArgumentException("Invalid capture size");
        double scale=Math.min(1d,1600d/Math.max(width,height));
        return new int[]{Math.max(1,(int)Math.round(width*scale)),Math.max(1,(int)Math.round(height*scale))};
    }
    private void capturedSize(int width,int height){
        if(!valid())return;
        if(contentSized){
            if(width!=rawWidth||height!=rawHeight)finishCapture("共享画面尺寸发生变化，截图已取消；请重新授权或选择图片",null);
            return;
        }
        try{
            if(display==null)throw new IllegalStateException("Display not ready");
            // Android 14 reports the initial chosen app region after creation.
            // Resize the existing display once; never reuse consent for another VD.
            if(width!=rawWidth||height!=rawHeight){
                int[] size=scaled(width,height);installReader(size[0],size[1]);
                display.resize(size[0],size[1],density);display.setSurface(reader.getSurface());
                rawWidth=width;rawHeight=height;
            }
            contentSized=true;
        }catch(RuntimeException|OutOfMemoryError failure){finishCapture("无法确认共享区域尺寸，截图已取消；请重新授权或选择图片",null);}
    }
    private void installReader(int width,int height){
        frameRevision++;if(reader!=null){reader.setOnImageAvailableListener(null,null);reader.close();}
        final int revision=frameRevision;reader=ImageReader.newInstance(width,height,PixelFormat.RGBA_8888,2);
        reader.setOnImageAvailableListener(source->{
            Bitmap bitmap=null;
            try(Image frame=source.acquireLatestImage()){
                if(frame==null||done||revision!=frameRevision||!contentSized)return;
                if(!valid())return;requireVisibleNotification(this);
                Image.Plane plane=frame.getPlanes()[0];
                java.nio.ByteBuffer pixels=FramePixels.pack(plane.getBuffer(),width,height,plane.getRowStride(),plane.getPixelStride());
                bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);bitmap.copyPixelsFromBuffer(pixels);
            }catch(RuntimeException|OutOfMemoryError failure){
                if(bitmap!=null&&!bitmap.isRecycled())bitmap.recycle();
                if(!done&&revision==frameRevision)finishCapture("本次截图未完成，请重新授权或选择图片",null);return;
            }
            if(bitmap!=null)finishCapture("已截取一帧，请核对应用、聊天对象和文字；受保护或空白画面可改用文字。尚未上传",bitmap);
        },main);
    }
    private void finishCapture(String message,Bitmap bitmap){
        if(done){if(bitmap!=null&&!bitmap.isRecycled())bitmap.recycle();return;}done=true;
        main.removeCallbacksAndMessages(null);frameRevision++;
        if(reader!=null){try{reader.setOnImageAvailableListener(null,null);reader.close();}catch(RuntimeException ignored){}reader=null;}
        if(display!=null){try{display.release();}catch(RuntimeException ignored){}display=null;}
        if(projection!=null){
            try{if(callback!=null)projection.unregisterCallback(callback);}catch(RuntimeException ignored){}
            try{projection.stop();}catch(RuntimeException ignored){}projection=null;
        }
        stopForeground(STOP_FOREGROUND_REMOVE);
        KeyboardImageRequest.detachCaptureStop(request,coordinatorStop);
        KeyboardImageRequest.complete(request,bitmap,message);stopSelf();
    }
    @Override public void onDestroy(){
        if(receiverRegistered){try{unregisterReceiver(screenOff);}catch(IllegalArgumentException ignored){}receiverRegistered=false;}
        finishCapture("截图服务已停止，请重新核对客户",null);super.onDestroy();
    }
}
