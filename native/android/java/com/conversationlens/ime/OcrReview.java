package com.conversationlens.ime;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** The recognizer assigns fixed screenshot sides; review edits text, not roles. */
final class OcrReview {
    private static final Pattern ROLE=Pattern.compile("^(我|对方)(?:（待核对）)?\\s*[：:]\\s*(.*)$");
    private static final Pattern UNRESOLVED=Pattern.compile("(?m)^\\s*(?:我（待核对）|对方（待核对）|待核对|非聊天)\\s*[：:]");
    static final class Line {
        final String raw;
        String text;
        final int speaker; // 0 outside/unknown, 1 right/me, 2 left/other
        boolean included;
        Line(String raw,String text,int speaker){this.raw=raw;this.text=text;this.speaker=speaker;this.included=speaker==1||speaker==2;}
    }
    static List<Line> parse(String transcript){
        List<Line> lines=new ArrayList<>();
        for(String raw:transcript.split("\\r?\\n")){
            if(raw.trim().isEmpty())continue;
            String text=raw.trim();Matcher match=ROLE.matcher(text);int speaker=0;
            if(match.matches()){speaker="我".equals(match.group(1))?1:2;text=match.group(2);}
            else text=text.replaceFirst("^(?:非聊天|待核对)\\s*[：:]\\s*","");
            lines.add(new Line(raw,text,speaker));
            if(lines.size()>80)throw new IllegalArgumentException("识别内容超过80条，请裁剪截图后再试");
        }
        return lines;
    }
    static boolean hasUnresolvedMarkers(String transcript){return UNRESOLVED.matcher(transcript).find();}
    static String assemble(List<Line> lines){
        StringBuilder out=new StringBuilder();
        for(int i=0;i<lines.size();i++){
            Line line=lines.get(i);
            if(!line.included)continue;
            if(line.speaker!=1&&line.speaker!=2)throw new IllegalArgumentException("第"+(i+1)+"条未定位到聊天气泡，请不纳入或改用手工粘贴");
            String text=line.text.trim();
            if(text.isEmpty())throw new IllegalArgumentException("第"+(i+1)+"条为空，请填写或选择不纳入");
            // Edited multiline text keeps its fixed side; inclusion cannot reassign it.
            for(String part:text.split("\\r?\\n")){if(part.trim().isEmpty())continue;if(out.length()>0)out.append('\n');out.append(line.speaker==1?"我：":"对方：").append(part.trim());}
            if(out.length()>4000)throw new IllegalArgumentException("校对后的片段超过4000字，请缩小范围");
        }
        if(out.length()==0)throw new IllegalArgumentException("请至少纳入一条已定位的聊天内容；无法定位时请手工粘贴");
        return out.toString();
    }
}
