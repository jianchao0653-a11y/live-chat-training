package com.conversationlens.ime;

import android.graphics.Bitmap;
import android.graphics.Rect;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;
import java.util.ArrayList;
import java.util.Collections;

/** One explicit image operation. No image is sent to the project server. */
final class LocalChatOcr {
    private static final java.util.concurrent.atomic.AtomicBoolean busy=new java.util.concurrent.atomic.AtomicBoolean();
    interface Done { void success(String text); void failure(); }
    static void recognize(Bitmap source, Done done) {
        recognize(source,done,false);
    }
    /** Profile/Moments text has no left/right speaker semantics; it always needs review. */
    static void recognizeProfile(Bitmap source, Done done) {
        recognize(source,done,true);
    }
    private static void recognize(Bitmap source, Done done, boolean profile) {
        if(!busy.compareAndSet(false,true)){done.failure();return;}
        // Own the pixels until the asynchronous recognizer completes; discarding the preview is safe.
        Bitmap owned=null;TextRecognizer opened=null;
        try{
            owned=source.copy(Bitmap.Config.ARGB_8888,false);
            opened=TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());
            final Bitmap copy=owned;final TextRecognizer recognizer=opened;
            recognizer.process(InputImage.fromBitmap(copy,0)).addOnCompleteListener(task->{
                String value=null;
                try{if(task.isSuccessful())value=profile?profileText(task.getResult()):transcript(task.getResult(),copy);}
                catch(RuntimeException|LinkageError|OutOfMemoryError failure){value=null;}
                finally{release(copy,recognizer);}
                if(value==null)done.failure();else done.success(value);
            });
        }catch(RuntimeException|LinkageError|OutOfMemoryError failure){release(owned,opened);done.failure();}
    }
    private static String profileText(Text text){
        ArrayList<Text.Line> lines=new ArrayList<>();
        for(Text.TextBlock block:text.getTextBlocks())lines.addAll(block.getLines());
        Collections.sort(lines,(a,b)->{
            Rect x=a.getBoundingBox(),y=b.getBoundingBox();
            if(x==null||y==null)return x==y?0:x==null?1:-1;
            int row=Integer.compare(x.top,y.top);return row!=0?row:Integer.compare(x.left,y.left);
        });
        StringBuilder out=new StringBuilder();
        for(Text.Line line:lines){String value=line.getText().trim();if(value.isEmpty())continue;out.append(value).append('\n');if(out.length()>12000)break;}
        return out.toString();
    }
    private static void release(Bitmap bitmap,TextRecognizer recognizer){
        try{if(recognizer!=null)recognizer.close();}catch(RuntimeException ignored){}
        finally{try{if(bitmap!=null&&!bitmap.isRecycled())bitmap.recycle();}catch(RuntimeException ignored){}finally{busy.set(false);}}
    }
    private static String transcript(Text text,Bitmap image) {
        final int width=image.getWidth(),height=image.getHeight();
        final int[] pixels=new int[Math.multiplyExact(width,height)];
        image.getPixels(pixels,0,width,0,0,width,height);
        ChatBubbleLayout.Pixels screen=new ChatBubbleLayout.Pixels(){
            public int width(){return width;}public int height(){return height;}public int colorAt(int x,int y){return pixels[y*width+x];}
        };
        ArrayList<Text.Line> lines=new ArrayList<>();
        for(Text.TextBlock block:text.getTextBlocks())lines.addAll(block.getLines());
        Collections.sort(lines,(a,b)->Integer.compare(a.getBoundingBox()==null?0:a.getBoundingBox().top,b.getBoundingBox()==null?0:b.getBoundingBox().top));
        StringBuilder out=new StringBuilder();
        for(Text.Line line:lines){
            Rect box=line.getBoundingBox();String value=line.getText().trim();if(value.isEmpty())continue;
            int side=box==null?0:ChatBubbleLayout.classify(screen,box.left,box.top,box.right,box.bottom).speaker;
            String speaker=side==1?"我":side==2?"对方":"非聊天";
            out.append(speaker).append('：').append(value).append('\n');
            if(out.length()>12000)break;
        }
        return out.toString();
    }
}
