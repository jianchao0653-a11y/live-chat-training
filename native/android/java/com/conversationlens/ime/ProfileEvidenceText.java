package com.conversationlens.ime;

import org.json.JSONArray;
import org.json.JSONObject;

/** Human-readable source labels resolved only within the returned analysis snapshot. */
final class ProfileEvidenceText {
    private ProfileEvidenceText() {}

    static String material(JSONArray materials,int index) {
        JSONObject item=materials==null?null:materials.optJSONObject(index);
        return item==null?"资料无法核对":sourceLabel(item,index)+"\n"+item.optString("text");
    }

    static String evidence(JSONArray materials,JSONObject item,boolean chat) {
        return "依据 "+item.optString("id")+" · "+source(materials,stringId(item.opt("source_id")),chat)
            +"\n“"+item.optString("quote")+"”";
    }

    static String references(JSONArray refs,JSONArray evidence,JSONArray materials,boolean chat) {
        if(refs==null||refs.length()==0)return "没有可核对引用";
        StringBuilder text=new StringBuilder();
        for(int i=0;i<Math.min(24,refs.length());i++){
            if(i>0)text.append("\n");
            String id=stringId(refs.opt(i));int found=uniqueIndex(evidence,id);
            if(found<0)text.append(id).append(" · 依据无法唯一核对");
            else text.append(evidence(materials,evidence.optJSONObject(found),chat));
        }
        return text.toString();
    }

    private static String source(JSONArray materials,String id,boolean chat) {
        // Reply evidence has no material ID. A missing profile ID must never be guessed.
        if(chat&&id.isEmpty())return "本次提交的聊天片段";
        int index=uniqueIndex(materials,id);
        if(index<0)return "来源无法唯一核对，请重新核对这份分析";
        return sourceLabel(materials.optJSONObject(index),index);
    }

    private static String sourceLabel(JSONObject item,int index) {
        String source=item.optString("source"),date=item.optString("observed_at");
        return "资料"+(index+1)+" · "+(source.isEmpty()?"来源未提供":source)
            +" · "+(date.isEmpty()?"观察日期未提供":"观察于 "+date);
    }

    private static int uniqueIndex(JSONArray items,String id) {
        if(items==null||id.isEmpty())return -1;
        int found=-1;
        for(int i=0;i<items.length();i++){
            JSONObject item=items.optJSONObject(i);
            if(item!=null&&id.equals(stringId(item.opt("id")))){if(found>=0)return -1;found=i;}
        }
        return found;
    }

    private static String stringId(Object value){return value instanceof String?(String)value:"";}
}
