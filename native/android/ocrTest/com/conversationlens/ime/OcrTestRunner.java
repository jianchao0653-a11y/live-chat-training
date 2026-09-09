package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import android.graphics.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Generated Chinese text only. Never reads the user's screenshots or records. */
public final class OcrTestRunner extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();int passed=0,exact=0;StringBuilder mismatches=new StringBuilder();
        try{
            String[] phrases={"你好","今天工作辛苦了","早点休息","谢谢你的关心","明天再聊"};
            for(int i=0;i<30;i++){
                final String expected=phrases[i%phrases.length];
                final Bitmap bitmap=Bitmap.createBitmap(720,1280,Bitmap.Config.ARGB_8888);
                Canvas canvas=new Canvas(bitmap);canvas.drawColor(i%2==0?Color.rgb(245,245,245):Color.WHITE);
                Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setColor(Color.BLACK);paint.setTextSize(32+(i%3)*6);
                float x=i%2==0?75:640-paint.measureText(expected);
                canvas.drawText(expected,x,250+(i%6)*115,paint);
                CountDownLatch latch=new CountDownLatch(1);String[] observed={null};
                runOnMainSync(()->LocalChatOcr.recognize(bitmap,new LocalChatOcr.Done(){
                    public void success(String text){observed[0]=text;latch.countDown();}
                    public void failure(){latch.countDown();}
                }));
                if(!latch.await(25,TimeUnit.SECONDS))throw new Exception("OCR timeout case "+i);
                bitmap.recycle();
                if(observed[0]==null||observed[0].trim().isEmpty()||!observed[0].contains("待核对"))throw new Exception("OCR unavailable or missing review marker case "+i);
                if(observed[0].replace(" ","").contains(expected))exact++;
                else mismatches.append(i).append(':').append(expected).append(" -> ").append(observed[0]).append(';');
                passed++;
            }
            result.putString("offline_capability","PASS");result.putString("exact_text",exact==30?"PASS":"FAIL");result.putInt("exact_matches",exact);result.putString("synthetic_mismatches",mismatches.toString());result.putInt("synthetic_cases",passed);finish(Activity.RESULT_OK,result);
        }catch(Exception error){result.putString("ocr","FAIL");result.putInt("synthetic_cases",passed);result.putString("reason",error.toString());finish(Activity.RESULT_CANCELED,result);}
    }
}
