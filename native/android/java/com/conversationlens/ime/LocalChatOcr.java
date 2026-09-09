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
        if(!busy.compareAndSet(false,true)){done.failure();return;}
        // Own the pixels until the asynchronous recognizer completes; discarding the preview is safe.
        Bitmap owned=null;TextRecognizer opened=null;
        try{
            owned=source.copy(Bitmap.Config.ARGB_8888,false);
            opened=TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());
            final Bitmap copy=owned;final TextRecognizer recognizer=opened;
            recognizer.process(InputImage.fromBitmap(copy,0)).addOnCompleteListener(task->{
                String value=task.isSuccessful()?transcript(task.getResult(),copy.getWidth(),copy.getHeight()):null;
                recognizer.close();copy.recycle();busy.set(false);
                if(value==null)done.failure();else done.success(value);
            });
        }catch(RuntimeException e){if(opened!=null)opened.close();if(owned!=null)owned.recycle();busy.set(false);throw e;}
    }
    private static String transcript(Text text,int width,int height) {
        ArrayList<Text.Line> lines=new ArrayList<>();
        for(Text.TextBlock block:text.getTextBlocks())lines.addAll(block.getLines());
        Collections.sort(lines,(a,b)->Integer.compare(a.getBoundingBox()==null?0:a.getBoundingBox().top,b.getBoundingBox()==null?0:b.getBoundingBox().top));
        StringBuilder out=new StringBuilder();
        for(Text.Line line:lines){
            Rect box=line.getBoundingBox();String value=line.getText().trim();if(value.isEmpty())continue;
            // Geometry is only a proposed attribution: narrow text on either side is not proof.
            String speaker="待核对";
            if(box!=null&&box.top>height*.12&&box.bottom<height*.86){
                if(box.right<width*.70&&box.left<width*.25)speaker="对方（待核对）";
                else if(box.left>width*.30&&box.right>width*.75)speaker="我（待核对）";
            }
            out.append(speaker).append('：').append(value).append('\n');
            if(out.length()>12000)break;
        }
        return out.toString();
    }
}
