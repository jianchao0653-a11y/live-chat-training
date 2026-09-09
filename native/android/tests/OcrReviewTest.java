package com.conversationlens.ime;
import java.util.List;
public final class OcrReviewTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    static void rejected(List<OcrReview.Line> lines){try{OcrReview.assemble(lines);throw new AssertionError();}catch(IllegalArgumentException expected){}}
    public static void main(String[] args){
        List<OcrReview.Line> lines=OcrReview.parse("待核对：12:00\n对方（待核对）：明夭再聊\n我（待核对）：好的\n");
        check(lines.size()==3);check(lines.get(1).speaker==0);check(lines.get(1).text.equals("明夭再聊"));rejected(lines);
        lines.get(0).speaker=3;lines.get(1).speaker=2;lines.get(1).text="明天再聊";lines.get(2).speaker=1;
        check(OcrReview.assemble(lines).equals("对方：明天再聊\n我：好的"));check(lines.get(1).raw.contains("明夭"));
        lines.get(2).text="第一行\n第二行";check(OcrReview.assemble(lines).endsWith("我：第一行\n我：第二行"));
        lines.get(1).text="";rejected(lines);lines.get(1).speaker=3;lines.get(2).speaker=3;rejected(lines);
        lines.get(1).speaker=1;lines.get(1).text=new String(new char[4001]).replace('\0','字');rejected(lines);
        System.out.println("OCR_REVIEW_PASS (unconfirmed, correction, exclusion, attribution, empty and bounds)");
    }
}
