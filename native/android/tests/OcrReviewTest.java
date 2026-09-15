package com.conversationlens.ime;
import java.util.List;
public final class OcrReviewTest {
    static int assertions;
    static void check(boolean value){assertions++;if(!value)throw new AssertionError("OCR review assertion "+assertions);}
    static void rejected(List<OcrReview.Line> lines){try{OcrReview.assemble(lines);throw new AssertionError("Expected rejected review");}catch(IllegalArgumentException expected){assertions++;}}
    public static void main(String[] args){
        List<OcrReview.Line> lines=OcrReview.parse("非聊天：12:00\n对方：明夭再聊\n我：好的\n");
        check(lines.size()==3);
        check(lines.get(0).speaker==0&&!lines.get(0).included);
        check(lines.get(1).speaker==2&&lines.get(1).included&&lines.get(1).text.equals("明夭再聊"));
        check(lines.get(2).speaker==1&&lines.get(2).included);
        // Known screenshot sides work immediately; no per-line role selection.
        check(OcrReview.assemble(lines).equals("对方：明夭再聊\n我：好的"));
        lines.get(1).text="明天再聊";
        check(OcrReview.assemble(lines).equals("对方：明天再聊\n我：好的"));
        check(lines.get(1).raw.contains("明夭"));
        lines.get(2).included=false;
        check(OcrReview.assemble(lines).equals("对方：明天再聊"));
        lines.get(2).included=true;lines.get(2).text="第一行\n第二行";
        check(OcrReview.assemble(lines).endsWith("我：第一行\n我：第二行"));
        lines.get(0).included=true;rejected(lines);lines.get(0).included=false;
        lines.get(1).text="";rejected(lines);
        lines.get(1).included=false;lines.get(2).included=false;rejected(lines);
        lines.get(1).included=true;lines.get(1).text=new String(new char[4001]).replace('\0','字');rejected(lines);
        List<OcrReview.Line> legacy=OcrReview.parse("待核对：12:00\n对方（待核对）：明天\n我（待核对）：好的");
        check(!legacy.get(0).included&&legacy.get(1).speaker==2&&legacy.get(2).speaker==1);
        check(OcrReview.assemble(legacy).equals("对方：明天\n我：好的"));
        List<OcrReview.Line> unknown=OcrReview.parse("页面标题\n非聊天：系统消息\n待核对：未定位文字");
        check(unknown.stream().noneMatch(line->line.included));rejected(unknown);
        unknown.get(0).included=true;rejected(unknown);
        check(!OcrReview.hasUnresolvedMarkers("对方：内容待核对\n我：好的"));
        check(OcrReview.hasUnresolvedMarkers("对方（待核对）：旧格式"));
        check(OcrReview.hasUnresolvedMarkers("我：正文\n非聊天：12:00"));
        check(!OcrReview.hasUnresolvedMarkers("我：非聊天：是这条消息的原话"));
        try{OcrReview.parse(new String(new char[81]).replace("\0","我：字\n"));throw new AssertionError("Expected line limit");}
        catch(IllegalArgumentException expected){assertions++;}
        System.out.println("OCR_REVIEW_PASS ("+assertions+" assertions: fixed sides, automatic inclusion, correction, exclusion, legacy, unknown, markers and bounds)");
    }
}
