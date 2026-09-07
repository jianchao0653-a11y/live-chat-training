package com.conversationlens.ime;
import java.nio.ByteBuffer;
import java.util.Arrays;
public final class FramePixelsTest {
    public static void main(String[] args){
        byte[] input={1,2,3,4,5,6,7,8,99,99,99,99,9,10,11,12,13,14,15,16};
        byte[] output=new byte[16];ByteBuffer source=ByteBuffer.wrap(input);FramePixels.pack(source,2,2,12,4).get(output);
        if(!Arrays.equals(output,new byte[]{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16})||source.position()!=0)throw new AssertionError("Padded last row or source position");
        int rejected=0;
        for(int[] values:new int[][]{{2,2,12,4},{1601,1,6404,4},{2,1,4,4},{2,1,8,8},{0,1,8,4}}){try{FramePixels.pack(ByteBuffer.allocate(8),values[0],values[1],values[2],values[3]);}catch(IllegalArgumentException e){rejected++;}}
        if(rejected!=5)throw new AssertionError("Malformed frame accepted");
        System.out.println("FRAME_PIXELS_PASS (padding, truncated frame, dimensions, strides, source position)");
    }
}
