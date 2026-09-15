package com.conversationlens.ime;

import java.util.ArrayList;

/** Finds a surrounding bubble, then maps its side. No theme color means a role. */
final class ChatBubbleLayout {
    interface Pixels { int width(); int height(); int colorAt(int x,int y); }
    static final class Placement {
        final int speaker,left,right; // 0 non-chat/unknown, 1 right/me, 2 left/other
        Placement(int speaker,int left,int right){this.speaker=speaker;this.left=left;this.right=right;}
    }
    private static final class Span {
        final int left,right,y,color,speaker;
        Span(int left,int right,int y,int color,int speaker){this.left=left;this.right=right;this.y=y;this.color=color;this.speaker=speaker;}
    }
    private static Placement unknown(){return new Placement(0,-1,-1);}
    static Placement classify(Pixels image,int left,int top,int right,int bottom){
        if(image==null)return unknown();
        int width=image.width(),height=image.height();
        if(width<32||height<32||left<0||top<0||right>width||bottom>height||left>=right||top>=bottom)return unknown();
        // This classifier is for full chat screenshots, not cropped text strips.
        // Header and input-tool bands must not be mistaken for chat bubbles.
        if(top<height*.07f||bottom>height*.90f)return unknown();
        int padding=Math.max(2,Math.min((bottom-top)/3,width/90));
        int[] rows={top-padding,top-1,top+(bottom-top)/4,(top+bottom)/2,bottom-(bottom-top)/4,bottom,bottom+padding};
        int[] seeds={left+(right-left)/4,(left+right)/2,right-1-(right-left)/4};
        int gap=Math.max(2,Math.min(width/90,Math.max(2,(bottom-top)/3)));
        int minPadding=Math.max(2,width/240),tolerance=Math.max(4,width/80);
        ArrayList<Span> spans=new ArrayList<>();
        for(int y:rows){
            if(y<0||y>=height)continue;
            for(int x:seeds){
                int color=image.colorAt(x,y);
                if((color>>>24)<240)continue;
                int begin=edge(image,x,y,-1,color,gap),end=edge(image,x,y,1,color,gap);
                // Enclose the complete OCR line with actual background padding.
                if(begin>left-minPadding||end<right-1+minPadding||begin<=0||end>=width-1)continue;
                if(end-begin>width*.86f||end-begin<Math.max(12,right-left+2*minPadding))continue;
                int near=Math.min(begin,width-1-end),bias=begin-(width-1-end);
                if(near>width*.28f||Math.abs(bias)<width*.05f)continue;
                int matches=0,total=0;
                for(int probe=begin;probe<=end;probe+=2){total++;if(similar(color,image.colorAt(probe,y)))matches++;}
                if(matches<total*.68f)continue;
                spans.add(new Span(begin,end,y,color,bias>0?1:2));
            }
        }
        Span best=null;int bestSupport=0;boolean me=false,other=false;
        for(Span candidate:spans){
            ArrayList<Integer> supportedRows=new ArrayList<>();
            for(Span support:spans){
                if(support.speaker==candidate.speaker&&similar(support.color,candidate.color)
                    &&Math.abs(support.left-candidate.left)<=tolerance&&Math.abs(support.right-candidate.right)<=tolerance
                    &&!supportedRows.contains(support.y))supportedRows.add(support.y);
            }
            if(supportedRows.size()<2)continue;
            if(candidate.speaker==1)me=true;else other=true;
            if(supportedRows.size()>bestSupport){best=candidate;bestSupport=supportedRows.size();}
        }
        // Conflicting surrounding regions are not resolved by a color guess.
        return best==null||me&&other?unknown():new Placement(best.speaker,best.left,best.right);
    }
    private static int edge(Pixels image,int x,int y,int step,int color,int gap){
        int last=x,misses=0;
        for(int next=x+step;next>=0&&next<image.width();next+=step){
            if(similar(color,image.colorAt(next,y))){last=next;misses=0;}
            else if(++misses>gap)break;
        }
        return last;
    }
    private static boolean similar(int a,int b){
        if((b>>>24)<240)return false;
        int r=Math.abs((a>>16&255)-(b>>16&255)),g=Math.abs((a>>8&255)-(b>>8&255)),bl=Math.abs((a&255)-(b&255));
        return Math.max(r,Math.max(g,bl))<=12&&r+g+bl<=24;
    }
}
