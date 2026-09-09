package com.conversationlens.ime;
public final class ImageDecodePolicyTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    public static void main(String[] args){
        check(ImageDecodePolicy.stableSampleSize(1080,2400)==2);
        check(ImageDecodePolicy.stableSampleSize(720,1600)==1);
        check(ImageDecodePolicy.stableSampleSize(1440,3200)==2);
        check(ImageDecodePolicy.sampleSize(1080,2400)==1);
        check(ImageDecodePolicy.sampleSize(720,1280)==1);
        check(ImageDecodePolicy.sampleSize(1440,3200)==2);
        for(int[] size:new int[][]{{100000,100000},{100,90000},{4000,4000},{4097,1},{1,4097}}){int s=ImageDecodePolicy.sampleSize(size[0],size[1]);long w=((long)size[0]+s-1)/s,h=((long)size[1]+s-1)/s;check(w*h<=4000000&&Math.max(w,h)<=4096);}
        for(int[] invalid:new int[][]{{0,5},{-1,10},{Integer.MAX_VALUE,1}}){try{ImageDecodePolicy.sampleSize(invalid[0],invalid[1]);throw new AssertionError();}catch(IllegalArgumentException expected){}}
        System.out.println("IMAGE_DECODE_POLICY_PASS (normal screenshots preserved, decoded pixels and dimensions bounded)");
    }
}
