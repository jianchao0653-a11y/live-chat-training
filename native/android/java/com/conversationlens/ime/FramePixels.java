package com.conversationlens.ime;
import java.nio.ByteBuffer;

/** ImageReader may omit padding after its last row. Never read past the buffer. */
final class FramePixels {
    static ByteBuffer pack(ByteBuffer source,int width,int height,int rowStride,int pixelStride){
        if(width<1||height<1||width>1600||height>1600||pixelStride!=4||rowStride<(long)width*4)throw new IllegalArgumentException("Unsupported screenshot plane");
        long needed=(long)(height-1)*rowStride+(long)width*4;
        if(source.remaining()<needed)throw new IllegalArgumentException("Incomplete screenshot frame");
        ByteBuffer result=ByteBuffer.allocate(width*height*4),row=source.duplicate();int start=source.position();
        for(int y=0;y<height;y++){row.limit(source.limit());row.position(start+y*rowStride);row.limit(row.position()+width*4);result.put(row);}
        result.flip();return result;
    }
}
