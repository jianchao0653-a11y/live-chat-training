package com.conversationlens.ime;

/** Stable default plus a bounded experimental OCR policy; no device-specific branches. */
final class ImageDecodePolicy {
    static int stableSampleSize(int width,int height){
        if(width<=0||height<=0||width>100000||height>100000)throw new IllegalArgumentException("Invalid image dimensions");
        int sample=1;while(Math.max(width/sample,height/sample)>1600)sample*=2;
        return sample;
    }
    static int sampleSize(int width,int height){
        if(width<=0||height<=0||width>100000||height>100000)throw new IllegalArgumentException("截图尺寸无效或过大，请裁剪后再试");
        int sample=1;
        while(true){long w=((long)width+sample-1)/sample,h=((long)height+sample-1)/sample;
            if(w*h<=4000000L&&Math.max(w,h)<=4096)return sample;
            sample*=2;
        }
    }
}
