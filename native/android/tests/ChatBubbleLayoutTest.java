package com.conversationlens.ime;

import java.util.Arrays;

public final class ChatBubbleLayoutTest {
    static final class Image implements ChatBubbleLayout.Pixels {
        final int width,height;final int[] pixels;
        Image(int width,int height,int color){this.width=width;this.height=height;pixels=new int[width*height];Arrays.fill(pixels,color);}
        public int width(){return width;}public int height(){return height;}public int colorAt(int x,int y){return pixels[y*width+x];}
        Image rectangle(int left,int top,int right,int bottom,int color){for(int y=top;y<bottom;y++)Arrays.fill(pixels,y*width+left,y*width+right,color);return this;}
        Image glyphs(int left,int top,int right,int bottom,int color){for(int x=left;x<right;x+=16)rectangle(x,top,Math.min(x+5,right),bottom,color);return this;}
    }
    static int checks;
    static ChatBubbleLayout.Placement check(Image image,int left,int top,int right,int bottom,int expected){
        ChatBubbleLayout.Placement found=ChatBubbleLayout.classify(image,left,top,right,bottom);
        if(found.speaker!=expected)throw new AssertionError("expected "+expected+" at "+left+","+top+" but got "+found.speaker);
        checks++;return found;
    }
    public static void main(String[] args){
        Image light=new Image(720,1280,0xffededed);
        light.rectangle(65,190,405,260,0xffffffff).glyphs(85,210,385,240,0xff202020);
        check(light,85,210,385,240,2);
        // A right bubble's short last line sits left of the screen center.
        light.rectangle(140,360,655,510,0xffa8e37d).glyphs(160,380,635,410,0xff202020).glyphs(160,445,295,475,0xff202020);
        check(light,160,380,635,410,1);
        ChatBubbleLayout.Placement last=check(light,160,445,295,475,1);
        if(last.left!=140||last.right!=654)throw new AssertionError("last line did not use full bubble edges");
        // Color is never an identity rule: green on the left, white on the right.
        light.rectangle(65,560,380,630,0xffa8e37d).glyphs(85,580,350,610,0xff202020);
        check(light,85,580,350,610,2);
        light.rectangle(380,680,655,750,0xffffffff).glyphs(400,700,635,730,0xff202020);
        check(light,400,700,635,730,1);
        Image dark=new Image(720,1280,0xff151515);
        dark.rectangle(65,210,410,285,0xff35383b).glyphs(85,230,390,260,0xffeeeeee);
        dark.rectangle(330,390,655,465,0xff225b43).glyphs(350,410,635,440,0xffeeeeee);
        check(dark,85,230,390,260,2);check(dark,350,410,635,440,1);
        // A pale, non-white theme still has visible surrounding boundaries.
        Image pale=new Image(720,1280,0xfff5f5f5).rectangle(65,230,410,300,0xffffffff).glyphs(85,250,390,280,0xff222222);
        check(pale,85,250,390,280,2);
        // Centered system badges, title/tool bands and plain text have no role.
        light.rectangle(265,810,455,865,0xffd0d0d0).glyphs(285,825,435,850,0xff222222);
        check(light,285,825,435,850,0);
        light.rectangle(65,15,405,75,0xffffffff);check(light,85,30,385,60,0);
        light.rectangle(65,1180,405,1260,0xffffffff);check(light,85,1200,385,1230,0);
        Image plain=new Image(720,1280,0xffeeeeee).glyphs(85,230,390,260,0xff202020);
        check(plain,85,230,390,260,0);
        check(light,-1,210,385,240,0);check(light,85,210,85,240,0);
        // A wide symmetrical region is not assigned using the text location.
        Image centered=new Image(720,1280,0xffededed).rectangle(65,200,655,300,0xffffffff).glyphs(85,220,230,250,0xff202020);
        check(centered,85,220,230,250,0);
        System.out.println("CHAT_BUBBLE_LAYOUT_PASS ("+checks+" checks: full edges, multiline, independent colors, synthetic dark theme, excluded regions)");
    }
}
