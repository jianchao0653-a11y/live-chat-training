package com.conversationlens.ime;

import android.app.Activity;
import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjectionManager;
import android.os.Bundle;
import android.view.WindowManager;

/** System consent only. The original keyboard owns every draft and captured pixel. */
public final class ImeCapturePermissionActivity extends Activity {
    private static final int CAPTURE=72,NOTIFICATIONS=73;
    private String request;
    private boolean delivered,handedToService;
    private int phase;
    private Runnable completion;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        request=getIntent().getStringExtra("request");
        if(!KeyboardImageRequest.acceptsCapture(request)){finishBridge();return;}
        completion=()->{delivered=true;if(!isDestroyed())finishBridge();};
        KeyboardImageRequest.observe(request,completion);
        phase=state==null?0:state.getInt("phase",0);
        if(phase==3){handedToService=true;delivered=true;finishBridge();return;}
        if(state==null){
            try{
                KeyboardCaptureService.prepareNotificationPermission(this);
                if(KeyboardCaptureService.needsNotificationPermission(this)){
                    phase=1;requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},NOTIFICATIONS);
                }else launchCaptureConsent();
            }catch(RuntimeException failure){finishResult("系统截图授权未打开；请允许停止通知，或选择图片、输入文字");}
        }
    }
    private void launchCaptureConsent(){
        if(phase>=2||!KeyboardImageRequest.acceptsCapture(request))return;
        KeyboardCaptureService.requireVisibleNotification(this);
        phase=2;
        MediaProjectionManager manager=(MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
        startActivityForResult(manager.createScreenCaptureIntent(),CAPTURE);
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results){
        super.onRequestPermissionsResult(code,permissions,results);
        if(code!=NOTIFICATIONS||isDestroyed())return;
        if(!KeyboardImageRequest.acceptsCapture(request)){delivered=true;finishBridge();return;}
        if(results.length==0||results[0]!=PackageManager.PERMISSION_GRANTED){
            finishResult("未允许截图停止通知，未捕获画面；可选择图片或输入文字");return;
        }
        try{launchCaptureConsent();}
        catch(RuntimeException failure){finishResult("停止通知或截图授权不可用；请检查通知设置，或选择图片、输入文字");}
    }
    @Override protected void onSaveInstanceState(Bundle state){
        state.putInt("phase",phase);super.onSaveInstanceState(state);
    }
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);if(code!=CAPTURE)return;
        if(!KeyboardImageRequest.acceptsCapture(request)){delivered=true;finishBridge();return;}
        if(result!=RESULT_OK||data==null){finishResult("已取消截图授权，未捕获画面；请重新核对客户");return;}
        try{
            KeyboardCaptureService.requireVisibleNotification(this);
            KeyboardCaptureService.begin(this,request,result,data);
            phase=3;handedToService=true;delivered=true;
            // The helper must leave the screen before the service may retain a frame.
            KeyboardImageRequest.unobserve(request,completion);finishBridge();
        }catch(RuntimeException failure){finishResult("截图服务未启动；请检查停止通知，或选择图片、输入文字");}
    }
    private void finishResult(String message){KeyboardImageRequest.complete(request,null,message);delivered=true;finishBridge();}
    private void finishBridge(){if(isTaskRoot())finishAndRemoveTask();else finish();}
    @Override protected void onStop(){
        super.onStop();if(handedToService)KeyboardImageRequest.captureBridgeHidden(request);
    }
    @Override protected void onDestroy(){
        KeyboardImageRequest.unobserve(request,completion);
        if(isFinishing()&&handedToService)KeyboardImageRequest.captureBridgeHidden(request);
        if(isFinishing()&&!delivered&&KeyboardImageRequest.acceptsCapture(request))KeyboardImageRequest.complete(request,null,"截图授权已结束，请在原聊天输入框重新核对客户");
        super.onDestroy();
    }
}
