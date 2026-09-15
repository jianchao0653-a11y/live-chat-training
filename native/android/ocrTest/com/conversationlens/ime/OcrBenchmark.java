package com.conversationlens.ime;
import android.app.*;
import android.graphics.*;
import android.os.Bundle;
import org.json.*;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.*;
/** Fixed synthetic transcription corpus. Both variants see identical PNG bytes. */
final class OcrBenchmark {
    static String stripRoles(String transcript){
        StringBuilder out=new StringBuilder();
        for(String raw:transcript.split("\\r?\\n")){
            String line=raw.trim().replaceFirst("^(?:(?:我|对方)(?:（待核对）)?|待核对|非聊天)\\s*[：:]\\s*","");
            if(line.isEmpty())continue;
            if(out.length()>0)out.append('\n');out.append(line);
        }
        return out.toString();
    }
    static int distance(String a,String b){int[] prev=new int[b.length()+1];for(int j=0;j<prev.length;j++)prev[j]=j;for(int i=1;i<=a.length();i++){int[] next=new int[b.length()+1];next[0]=i;for(int j=1;j<=b.length();j++)next[j]=Math.min(Math.min(prev[j]+1,next[j-1]+1),prev[j-1]+(a.charAt(i-1)==b.charAt(j-1)?0:1));prev=next;}return prev[b.length()];}
    static void run(Instrumentation runner){Bundle output=new Bundle();JSONArray cases=new JSONArray();try{
        String[] phrases={"今天工作辛苦了","早点休息","谢谢你的关心","明天再聊","今晚八点见面","这次不用送礼物","我不方便接电话","还有三天就放假","我想先安静一下","你周末有什么安排","明天下午三点再确认","这件事我还没答应","谢谢理解我的决定","今天已经完成工作","周日一起去公园走走","不用着急回复消息","我会认真考虑一下","最近工作比较繁忙","我们下次再聊这个","不是不想理你"};
        int[][] sizes={{720,1600},{1080,2400},{1440,3200},{2400,1080}};
        for(int profile=0;profile<sizes.length;profile++)for(int i=0;i<20;i++){
            String expected=phrases[i%20];int width=sizes[profile][0],height=sizes[profile][1];
            Bitmap source=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(source);boolean dark=i%4==0;canvas.drawColor(dark?Color.rgb(35,35,35):Color.rgb(245,245,245));
            Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setColor(dark?Color.WHITE:Color.BLACK);int textPixels=28+(i%4)*4;paint.setTextSize(textPixels);
            float x=i%2==0?85:width-85-paint.measureText(expected);canvas.drawText(expected,x,height*(0.12f+(i%8)*0.10f),paint);
            ByteArrayOutputStream png=new ByteArrayOutputStream();source.compress(Bitmap.CompressFormat.PNG,100,png);source.recycle();byte[] bytes=png.toByteArray();
            for(int variant=0;variant<2;variant++){
                int legacy=ImageDecodePolicy.stableSampleSize(width,height);
                BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=variant==0?legacy:ImageDecodePolicy.sampleSize(width,height);
                Bitmap input=BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);CountDownLatch latch=new CountDownLatch(1);String[] observed={null};long start=System.nanoTime();
                runner.runOnMainSync(()->LocalChatOcr.recognize(input,new LocalChatOcr.Done(){public void success(String value){observed[0]=value;latch.countDown();}public void failure(){latch.countDown();}}));
                if(!latch.await(25,TimeUnit.SECONDS))throw new Exception("Synthetic OCR timeout");input.recycle();
                String actual=observed[0]==null?"":stripRoles(observed[0]);
                cases.put(new JSONObject().put("id",profile*20+i).put("width",width).put("height",height).put("textPixels",textPixels).put("dark",dark).put("sampleSize",options.inSampleSize).put("api",android.os.Build.VERSION.SDK_INT).put("split",i%20<10?"development":"validation").put("variant",variant==0?"legacy1600":"preserve4mp").put("expected",expected).put("actual",actual).put("exact",expected.equals(actual)).put("distance",distance(expected,actual)).put("characters",expected.length()).put("milliseconds",(System.nanoTime()-start)/1000000));
            }
        }
        output.putString("benchmark","PASS");output.putString("cases",cases.toString());output.putString("scope","synthetic-single-message-transcription-only");runner.finish(Activity.RESULT_OK,output);
    }catch(Exception e){output.putString("benchmark","FAIL");output.putString("reason",e.getClass().getSimpleName());runner.finish(Activity.RESULT_CANCELED,output);}}
}
