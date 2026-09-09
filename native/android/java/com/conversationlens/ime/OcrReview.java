package com.conversationlens.ime;

import java.util.ArrayList;
import java.util.List;

/** Review never silently fixes characters or treats geometry as speaker identity. */
final class OcrReview {
    static final class Line {
        final String raw;
        String text;
        int speaker; // 0 unconfirmed, 1 me, 2 other, 3 exclude
        Line(String raw,String text){this.raw=raw;this.text=text;}
    }
    static List<Line> parse(String transcript){
        List<Line> lines=new ArrayList<>();
        for(String raw:transcript.split("\\r?\\n")){
            if(raw.trim().isEmpty())continue;
            String text=raw.replaceFirst("^(?:我（待核对）|对方（待核对）|待核对)：","");
            lines.add(new Line(raw,text));
            if(lines.size()>80)throw new IllegalArgumentException("识别内容超过80条，请裁剪截图后再试");
        }
        return lines;
    }
    static String assemble(List<Line> lines){
        StringBuilder out=new StringBuilder();
        for(int i=0;i<lines.size();i++){
            Line line=lines.get(i);
            if(line.speaker==3)continue;
            if(line.speaker!=1&&line.speaker!=2)throw new IllegalArgumentException("请确认第"+(i+1)+"条的发言人，或选择不纳入");
            String text=line.text.trim();
            if(text.isEmpty())throw new IllegalArgumentException("第"+(i+1)+"条为空，请填写或选择不纳入");
            // Keep embedded line breaks attributed to the same confirmed speaker.
            for(String part:text.split("\\r?\\n")){if(part.trim().isEmpty())continue;if(out.length()>0)out.append('\n');out.append(line.speaker==1?"我：":"对方：").append(part.trim());}
            if(out.length()>4000)throw new IllegalArgumentException("校对后的片段超过4000字，请缩小范围");
        }
        if(out.length()==0)throw new IllegalArgumentException("请至少保留一条已确认的聊天内容");
        return out.toString();
    }
}
