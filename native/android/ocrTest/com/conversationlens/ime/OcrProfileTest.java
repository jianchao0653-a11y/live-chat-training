package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.FileOutputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Pattern;

/** Real profile OCR on four generated images. Never reads external images or contacts. */
final class OcrProfileTest {
    private static final long CASE_TIMEOUT_NANOS=TimeUnit.SECONDS.toNanos(25);
    private static final Pattern CHAT_PREFIX=Pattern.compile("^(?:(?:我|对方)(?:（待核对）)?|待核对|非聊天)[：:]");
    private static final Spec[] SPECS={
        new Spec("signature-light-left",false,0xfff6f7f8,0xff202426,new String[]{"A1 签名：慢慢来","A2 爱好：散步","A3 近况：今天晴天"}),
        new Spec("hobbies-light-right",true,0xffffffff,0xff202426,new String[]{"B1 爱好：阅读","B2 周末：去公园","B3 计划：早点休息"}),
        new Spec("moments-dark-left",false,0xff202426,0xfff5f5f5,new String[]{"C1 朋友圈","C2 今天去散步","C3 天气很好","C4 晚上早点休息"}),
        new Spec("profile-dark-right",true,0xff35383b,0xffffffff,new String[]{"D1 资料备注","D2 喜欢安静","D3 最近在读书","D4 明天再聊"})
    };
    private static final class Spec {
        final String name;
        final boolean right;
        final int background,foreground;
        final String[] lines;
        Spec(String name,boolean right,int background,int foreground,String[] lines){this.name=name;this.right=right;this.background=background;this.foreground=foreground;this.lines=lines;}
        String expected(){return String.join("\n",lines);}
    }

    private static Bitmap create(Spec spec){
        Bitmap bitmap=Bitmap.createBitmap(1080,1000,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(bitmap);canvas.drawColor(spec.background);
        Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setColor(spec.foreground);paint.setTextSize(44);paint.setTypeface(Typeface.DEFAULT);
        for(int row=0;row<spec.lines.length;row++){
            String line=spec.lines[row];float x=spec.right?1010-paint.measureText(line):70;
            canvas.drawText(line,x,155+row*185,paint);
        }
        return bitmap;
    }
    private static boolean prefixFree(String actual){
        for(String line:actual.split("\r?\n"))if(CHAT_PREFIX.matcher(line.trim()).find())return false;
        return true;
    }
    private static JSONObject order(Spec spec,String actual) throws Exception {
        // Visible A1/A2/... markers isolate reading order from Chinese character
        // accuracy. Whitespace is ignored only here, never for exact_text.
        String compact=actual.replaceAll("\\s+","");
        JSONArray positions=new JSONArray();boolean verifiable=true,ordered=true;int previous=-1;
        for(String line:spec.lines){
            String marker=line.substring(0,2);int position=compact.indexOf(marker);
            boolean unique=position>=0&&compact.indexOf(marker,position+marker.length())<0;
            if(!unique)verifiable=false;
            if(position<=previous)ordered=false;
            positions.put(new JSONObject().put("marker",marker).put("position",position).put("unique",unique));
            previous=position;
        }
        return new JSONObject().put("status",verifiable?(ordered?"PASS":"FAIL"):"UNVERIFIED")
            .put("verifiable",verifiable).put("positions",positions);
    }

    static void run(Instrumentation runner){
        Bundle output=new Bundle();JSONArray cases=new JSONArray();
        int processed=0,nonempty=0,noPrefix=0,ordered=0,exact=0;
        boolean engineAvailable=true,timeout=false;
        output.putInt("api",android.os.Build.VERSION.SDK_INT);output.putBoolean("synthetic",true);
        output.putBoolean("qualityAccepted",false);output.putBoolean("productionReady",false);
        output.putString("interaction_mode","generated-bitmap-through-LocalChatOcr.recognizeProfile");
        output.putString("scope","synthetic-profile-text-only;not-real-WeChat-or-OEM-quality");
        output.putString("network_isolation","caller-must-verify");
        output.putString("source_image_package",runner.getTargetContext().getPackageName());
        output.putString("exact_matching","line-endings-normalized-and-outer-trim-only;no-role-or-space-removal");
        output.putString("order_matching","visible-unique-line-markers;whitespace-ignored-only-for-marker-order");
        try{
            for(int index=0;index<SPECS.length;index++){
                Spec spec=SPECS[index];String filename="profile-synthetic-"+index+".png";
                JSONObject record=new JSONObject().put("case",spec.name).put("expected",spec.expected())
                    .put("actual",JSONObject.NULL).put("source_image",filename).put("alignment",spec.right?"right":"left")
                    .put("background",String.format("#%08x",spec.background)).put("foreground",String.format("#%08x",spec.foreground))
                    .put("nonempty",false).put("no_chat_prefix",false).put("exact_text",false);
                if(timeout){cases.put(record.put("engine","NOT_RUN_AFTER_TIMEOUT").put("reading_order","UNVERIFIED"));continue;}
                final Bitmap bitmap=create(spec);final Object pixels=new Object();
                final AtomicBoolean expired=new AtomicBoolean();
                final AtomicReference<String> observed=new AtomicReference<>(),callbackError=new AtomicReference<>();
                final CountDownLatch latch=new CountDownLatch(1);
                final long start=System.nanoTime();boolean completed=false;
                try{
                    // Write only this test's generated evidence; never enumerate/read files.
                    try(FileOutputStream file=runner.getTargetContext().openFileOutput(filename,Context.MODE_PRIVATE)){
                        if(!bitmap.compress(Bitmap.CompressFormat.PNG,100,file))throw new IllegalStateException("Synthetic PNG encoding failed");
                    }
                    new Handler(Looper.getMainLooper()).post(()->{
                        synchronized(pixels){
                            if(expired.get())return;
                            try{
                                LocalChatOcr.recognizeProfile(bitmap,new LocalChatOcr.Done(){
                                    public void success(String text){if(!expired.get())observed.set(text);latch.countDown();}
                                    public void failure(){callbackError.set("RECOGNIZER_FAILURE");latch.countDown();}
                                });
                            }catch(Throwable error){callbackError.set(error.getClass().getSimpleName());latch.countDown();}
                        }
                    });
                    long remaining=CASE_TIMEOUT_NANOS-(System.nanoTime()-start);
                    completed=remaining>0&&latch.await(remaining,TimeUnit.NANOSECONDS);
                }finally{
                    // LocalChatOcr owns a private copy once recognizeProfile returns.
                    // The lock prevents recycling the original during that synchronous copy.
                    synchronized(pixels){expired.set(true);if(!bitmap.isRecycled())bitmap.recycle();}
                }
                processed++;record.put("milliseconds",(System.nanoTime()-start)/1000000);
                String actual=observed.get();record.put("actual",actual==null?JSONObject.NULL:actual);
                if(!completed||actual==null){
                    engineAvailable=false;timeout=!completed;
                    cases.put(record.put("engine",completed?"FAIL":"TIMEOUT").put("reading_order","UNVERIFIED")
                        .put("reason",completed?String.valueOf(callbackError.get()):"25_SECOND_DEADLINE"));
                    continue;
                }
                String normalized=actual.replace("\r\n","\n").replace('\r','\n').trim();
                boolean hasText=!normalized.isEmpty();boolean clean=hasText&&prefixFree(normalized);
                JSONObject ordering=order(spec,normalized);boolean inOrder="PASS".equals(ordering.getString("status"));
                boolean matches=spec.expected().equals(normalized);
                if(hasText)nonempty++;if(clean)noPrefix++;if(inOrder)ordered++;if(matches)exact++;
                if(!hasText)engineAvailable=false;
                cases.put(record.put("engine",hasText?"PASS":"EMPTY").put("normalized_actual",normalized)
                    .put("nonempty",hasText).put("no_chat_prefix",clean).put("reading_order",ordering.getString("status"))
                    .put("order_evidence",ordering).put("exact_text",matches));
            }
            boolean contract=processed==SPECS.length&&engineAvailable&&nonempty==SPECS.length&&noPrefix==SPECS.length&&ordered==SPECS.length;
            output.putString("profile_contract",contract?"PASS":"FAIL");output.putString("ocr_engine",engineAvailable?"PASS":"FAIL");
            output.putString("nonempty",nonempty==SPECS.length?"PASS":"FAIL");
            output.putString("no_chat_prefix",noPrefix==SPECS.length?"PASS":"FAIL");
            output.putString("reading_order",ordered==SPECS.length?"PASS":"FAIL");
            output.putString("exact_text",exact==SPECS.length?"PASS":"FAIL");
            output.putInt("planned_cases",SPECS.length);output.putInt("synthetic_cases",processed);
            output.putInt("nonempty_matches",nonempty);output.putInt("prefix_free_matches",noPrefix);
            output.putInt("order_matches",ordered);output.putInt("exact_matches",exact);output.putString("cases",cases.toString());
            runner.finish(contract?Activity.RESULT_OK:Activity.RESULT_CANCELED,output);
        }catch(Throwable error){
            output.putString("profile_contract","FAIL");output.putString("exact_text","FAIL");
            output.putInt("planned_cases",SPECS.length);output.putInt("synthetic_cases",processed);
            output.putInt("exact_matches",exact);output.putString("reason",error.getClass().getSimpleName());
            output.putString("cases",cases.toString());runner.finish(Activity.RESULT_CANCELED,output);
        }
    }
}
