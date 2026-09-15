package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.Bundle;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Real bundled OCR over generated pixels. No real screenshot or screen capture. */
final class OcrBubbleTest {
    private static final String[] PALETTES={"light-green","light-blue","dark-green","same-bubble-color"};
    private static final int[][] COLORS={
        {0xffededed,0xffffffff,0xffa8e37d,0xff202020},
        {0xffededed,0xffffffff,0xff9ec9ff,0xff202020},
        {0xff151515,0xff35383b,0xff225b43,0xffeeeeee},
        {0xffededed,0xffffffff,0xffffffff,0xff202020}
    };
    private static final Integer[] EXPECTED_ROLES={0,0,2,2,1,1,0};
    private static final String EXPECTED_TEXT="聊天\n12:00\n你好\n明天再聊\n好的\n谢谢\n发送";

    private static Bitmap create(int profile){
        int[] colors=COLORS[profile];
        Bitmap bitmap=Bitmap.createBitmap(720,1280,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(bitmap);canvas.drawColor(colors[0]);
        Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(colors[1]);canvas.drawRoundRect(new RectF(65,280,455,480),18,18,paint);
        paint.setColor(colors[2]);canvas.drawRoundRect(new RectF(265,580,655,800),18,18,paint);
        paint.setColor(colors[3]);paint.setTextSize(44);
        canvas.drawText("聊天",(720-paint.measureText("聊天"))/2,62,paint);
        canvas.drawText("12:00",(720-paint.measureText("12:00"))/2,214,paint);
        canvas.drawText("你好",95,335,paint);
        canvas.drawText("明天再聊",95,405,paint);
        // Short right-side lines deliberately lie near/left of the screen center.
        // Correct identity requires the surrounding bubble's full boundaries.
        canvas.drawText("好的",295,645,paint);
        canvas.drawText("谢谢",295,715,paint);
        canvas.drawText("发送",(720-paint.measureText("发送"))/2,1220,paint);
        return bitmap;
    }

    private static ArrayList<Integer> roles(String transcript){
        ArrayList<Integer> result=new ArrayList<>();
        for(String raw:transcript.split("\\r?\\n")){
            String line=raw.trim();if(line.isEmpty())continue;
            result.add(line.startsWith("我：")?1:line.startsWith("对方：")?2:line.startsWith("非聊天：")?0:-1);
        }
        return result;
    }

    static void run(Instrumentation runner){
        Bundle output=new Bundle();JSONArray cases=new JSONArray();
        int attributed=0,exact=0,processed=0;boolean engineAvailable=true;
        output.putInt("api",android.os.Build.VERSION.SDK_INT);
        output.putBoolean("synthetic",true);output.putBoolean("qualityAccepted",false);
        output.putString("interaction_mode","generated-bitmap-through-LocalChatOcr");
        output.putString("network_isolation","caller-must-verify");
        output.putString("source_image_package",runner.getTargetContext().getPackageName());
        output.putString("scope","synthetic-full-chat-layout;not-real-WeChat-or-OEM-quality");
        try{
            for(int profile=0;profile<PALETTES.length;profile++){
                Bitmap bitmap=create(profile);
                String filename="bubble-synthetic-"+profile+".png";
                String[] observed={null};CountDownLatch latch=new CountDownLatch(1);
                JSONObject record=new JSONObject().put("palette",PALETTES[profile])
                    .put("expectedRoles",new JSONArray(Arrays.asList(EXPECTED_ROLES)))
                    .put("expectedText",EXPECTED_TEXT).put("sourceImage",filename);
                long start=System.nanoTime();boolean completed;
                try{
                    // Instrumentation runs in the target process. Write only our generated
                    // evidence filenames into its writable files directory, without reading it.
                    try(FileOutputStream file=runner.getTargetContext().openFileOutput(filename,Context.MODE_PRIVATE)){
                        if(!bitmap.compress(Bitmap.CompressFormat.PNG,100,file))throw new IllegalStateException("Synthetic PNG encoding failed");
                    }
                    runner.runOnMainSync(()->LocalChatOcr.recognize(bitmap,new LocalChatOcr.Done(){
                        public void success(String value){observed[0]=value;latch.countDown();}
                        public void failure(){latch.countDown();}
                    }));
                    completed=latch.await(25,TimeUnit.SECONDS);
                }finally{bitmap.recycle();}
                processed++;
                record.put("milliseconds",(System.nanoTime()-start)/1000000);
                if(!completed||observed[0]==null){
                    engineAvailable=false;
                    record.put("engine",completed?"FAIL":"TIMEOUT").put("attribution",false).put("exactText",false);
                    cases.put(record);
                    // A timed-out recognizer may still own its private pixel copy.
                    if(!completed)break;
                    continue;
                }
                ArrayList<Integer> actualRoles=roles(observed[0]);
                String actualText=OcrBenchmark.stripRoles(observed[0]);
                boolean attribution=actualRoles.equals(Arrays.asList(EXPECTED_ROLES));
                boolean exactText=EXPECTED_TEXT.equals(actualText);
                if(attribution)attributed++;if(exactText)exact++;
                cases.put(record.put("engine","PASS").put("actualRoles",new JSONArray(actualRoles))
                    .put("actualText",actualText).put("transcript",observed[0])
                    .put("attribution",attribution).put("exactText",exactText));
            }
            boolean pass=engineAvailable&&processed==PALETTES.length&&attributed==PALETTES.length;
            output.putString("bubble_attribution",pass?"PASS":"FAIL");
            output.putString("ocr_engine",engineAvailable?"PASS":"FAIL");
            output.putString("exact_text",exact==PALETTES.length?"PASS":"FAIL");
            output.putInt("synthetic_cases",processed);output.putInt("attribution_matches",attributed);output.putInt("exact_matches",exact);
            output.putString("cases",cases.toString());
            runner.finish(pass?Activity.RESULT_OK:Activity.RESULT_CANCELED,output);
        }catch(Throwable error){
            output.putString("bubble_attribution","FAIL");output.putString("reason",error.getClass().getSimpleName());
            output.putString("cases",cases.toString());output.putInt("synthetic_cases",processed);
            runner.finish(Activity.RESULT_CANCELED,output);
        }
    }
}
