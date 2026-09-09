package com.conversationlens.ime;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.graphics.*;
import android.hardware.display.*;
import android.media.*;
import android.media.projection.*;
import android.os.*;
import android.util.DisplayMetrics;
import android.view.WindowManager;

/** One consent token, one virtual display, one retained frame. No network or files. */
public final class CaptureService extends Service {
    static final String CHANNEL="lens-capture";
    private final Handler handler=new Handler(Looper.getMainLooper());
    private MediaProjection projection;
    private VirtualDisplay display;
    private ImageReader reader;
    private boolean done;
    private AssistSession session;
    private String context;
    private MediaProjection.Callback callback;
    private final BroadcastReceiver screenOff=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent i){finishCapture("锁屏或息屏已停止截图",null);}};
    @Override public void onCreate(){super.onCreate();IntentFilter filter=new IntentFilter(Intent.ACTION_SCREEN_OFF);if(Build.VERSION.SDK_INT>=33)registerReceiver(screenOff,filter,Context.RECEIVER_NOT_EXPORTED);else registerReceiver(screenOff,filter);}
    static void channel(Context context){((NotificationManager)context.getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(new NotificationChannel(CHANNEL,"单次屏幕截图",NotificationManager.IMPORTANCE_DEFAULT));}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent==null || "stop".equals(intent.getAction())){finishCapture("已停止截图",null);return START_NOT_STICKY;}
        if(projection!=null)return START_NOT_STICKY;
        session=AssistSession.current;context=intent.getStringExtra("context");
        channel(this);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,CaptureService.class).setAction("stop"),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notice=new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.ic_menu_camera).setContentTitle("3 秒后截取一帧屏幕").setContentText("截取后立即停止；图片先预览，不会自动上传").setOngoing(true).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build();
        try{
            if(Build.VERSION.SDK_INT>=29)startForeground(301,notice,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);else startForeground(301,notice);
            if(session==null || !session.alive() || !session.context.equals(context))throw new Exception("输入现场已失效");
            Intent permission=intent.getParcelableExtra("permission");
            projection=((MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE)).getMediaProjection(Activity.RESULT_OK,permission);
            callback=new MediaProjection.Callback(){@Override public void onStop(){finishCapture("系统已停止截图",null);}};
            projection.registerCallback(callback,handler);
            // Give the consent/helper window time to leave the screen before creating the only display.
            handler.postDelayed(()->capture(),3000);
            handler.postDelayed(()->finishCapture("截图超时，请重试",null),10000);
        }catch(Exception e){finishCapture("截图未开始："+e.getMessage(),null);}
        return START_NOT_STICKY;
    }
    private void capture(){
        if(done)return;
        try{
            if(session==null||!session.alive()||!session.context.equals(context))throw new Exception("输入现场已变化");
            if(!((PowerManager)getSystemService(POWER_SERVICE)).isInteractive() || ((KeyguardManager)getSystemService(KEYGUARD_SERVICE)).isKeyguardLocked()){finishCapture("锁屏或息屏已停止截图",null);return;}
            DisplayMetrics metrics=new DisplayMetrics();((WindowManager)getSystemService(WINDOW_SERVICE)).getDefaultDisplay().getRealMetrics(metrics);
            float scale=Math.min(1f,1600f/Math.max(metrics.widthPixels,metrics.heightPixels));
            int width=Math.max(1,Math.round(metrics.widthPixels*scale)),height=Math.max(1,Math.round(metrics.heightPixels*scale));
            reader=ImageReader.newInstance(width,height,PixelFormat.RGBA_8888,2);
            reader.setOnImageAvailableListener(source->{
                if(done)return;
                try(Image frame=source.acquireLatestImage()){
                    if(frame==null)return;
                    if(!((PowerManager)getSystemService(POWER_SERVICE)).isInteractive() || ((KeyguardManager)getSystemService(KEYGUARD_SERVICE)).isKeyguardLocked()){finishCapture("锁屏或息屏已停止截图",null);return;}
                    Image.Plane plane=frame.getPlanes()[0];
                    java.nio.ByteBuffer pixels=FramePixels.pack(plane.getBuffer(),width,height,plane.getRowStride(),plane.getPixelStride());
                    Bitmap cropped=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);cropped.copyPixelsFromBuffer(pixels);
                    finishCapture("已截取一帧 · 点击预览，尚未上传",cropped);
                }catch(Exception e){finishCapture("截图失败，请重试",null);}
            },handler);
            display=projection.createVirtualDisplay("LensSingleFrame",width,height,metrics.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader.getSurface(),null,handler);
        }catch(Exception e){finishCapture("截图未完成："+e.getMessage(),null);}
    }
    private void finishCapture(String message,Bitmap image){
        if(done){if(image!=null)image.recycle();return;}done=true;
        handler.removeCallbacksAndMessages(null);
        if(display!=null){display.release();display=null;}
        if(reader!=null){reader.setOnImageAvailableListener(null,null);reader.close();reader=null;}
        if(projection!=null){projection.unregisterCallback(callback);projection.stop();projection=null;}
        boolean valid=session!=null && session.alive() && session.context.equals(context);
        if(valid){session.captureMessage=message;if(image!=null){session.clearImage();session.image=image;}}
        else if(image!=null)image.recycle();
        stopForeground(STOP_FOREGROUND_REMOVE);
        if(valid){
            PendingIntent open=PendingIntent.getActivity(this,2,new Intent(this,AssistantActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(302,new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.ic_menu_camera).setContentTitle(message).setContentText("打开观微核对截图").setContentIntent(open).setAutoCancel(true).build());
        }
        stopSelf();
    }
    @Override public void onDestroy(){unregisterReceiver(screenOff);finishCapture("截图服务已停止",null);super.onDestroy();}
}
