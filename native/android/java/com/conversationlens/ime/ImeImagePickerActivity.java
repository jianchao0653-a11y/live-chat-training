package com.conversationlens.ime;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.view.WindowManager;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.RejectedExecutionException;

/** Permission-only bridge to the system picker; all product review remains in the IME. */
public final class ImeImagePickerActivity extends Activity {
    private static final int PICK=71;
    // An unresponsive document provider must not occupy the network request pool.
    // No queued reads: a cancelled provider that does not return cannot accumulate jobs.
    private static final ThreadPoolExecutor images=new ThreadPoolExecutor(0,1,30,TimeUnit.SECONDS,
        new SynchronousQueue<Runnable>(),r->{Thread worker=new Thread(r,"lens-picked-image");worker.setDaemon(true);return worker;});
    private String request;
    private boolean delivered;
    private Runnable completion;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        request=getIntent().getStringExtra("request");
        if(!KeyboardImageRequest.accepts(request)){finish();return;}
        completion=()->{delivered=true;if(!isDestroyed())finishPicker();};
        KeyboardImageRequest.observe(request,completion);
        if(state==null){
            try{startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE),PICK);}
            catch(RuntimeException failure){finishResult(null,"系统选图未打开，草稿已保留，可重新选择或粘贴文字");}
        }
    }
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);
        if(code!=PICK)return;
        if(!KeyboardImageRequest.accepts(request)){finish();return;}
        if(result!=RESULT_OK||data==null||data.getData()==null){finishResult(null,"已取消选图，未读取图片；请重新核对客户");return;}
        final android.net.Uri uri=data.getData();final String id=request;
        try{images.execute(()->{
            Bitmap bitmap=null;String message;
            try{
                ByteArrayOutputStream output=new ByteArrayOutputStream();
                try(InputStream input=getContentResolver().openInputStream(uri)){
                    if(input==null)throw new java.io.IOException("No selected image");
                    byte[] chunk=new byte[8192];int n;
                    while((n=input.read(chunk))!=-1){if(output.size()+n>15000000)throw new java.io.IOException("Image limit");output.write(chunk,0,n);}
                }
                byte[] bytes=output.toByteArray();BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
                BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
                options.inSampleSize=ImageDecodePolicy.stableSampleSize(options.outWidth,options.outHeight);
                options.inJustDecodeBounds=false;bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
                if(bitmap==null)throw new java.io.IOException("Image decode");
                message="已读取所选图片，请在键盘预览、识别并校对；尚未上传";
            }catch(Exception|OutOfMemoryError failure){
                if(bitmap!=null&&!bitmap.isRecycled())bitmap.recycle();bitmap=null;
                message="图片未读取，请使用 15 MB 以内的截图或粘贴文字；原草稿已保留";
            }
            final Bitmap image=bitmap;final String note=message;
            runOnUiThread(()->{
                // Completion is bound to the old request, even if Android recreated this activity.
                KeyboardImageRequest.complete(id,image,note);delivered=true;
                if(!isDestroyed())finishPicker();
            });
        });}catch(RejectedExecutionException busy){finishResult(null,"上一张图片仍在读取，请稍后选择或直接粘贴文字");}
    }
    private void finishResult(Bitmap image,String message){KeyboardImageRequest.complete(request,image,message);delivered=true;finishPicker();}
    private void finishPicker(){if(isTaskRoot())finishAndRemoveTask();else finish();}
    @Override protected void onDestroy(){
        KeyboardImageRequest.unobserve(request,completion);
        if(isFinishing()&&!delivered&&KeyboardImageRequest.accepts(request))KeyboardImageRequest.complete(request,null,"选图已结束，请在键盘重新核对客户");
        super.onDestroy();
    }
}
