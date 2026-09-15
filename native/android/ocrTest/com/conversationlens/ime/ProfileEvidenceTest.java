package com.conversationlens.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import org.json.JSONArray;
import org.json.JSONObject;

/** Synthetic snapshot ambiguity and error compatibility on the Android JSON runtime. */
final class ProfileEvidenceTest {
    static void run(Instrumentation runner){
        Bundle result=new Bundle();int checks=0;
        try{
            JSONArray materials=new JSONArray("[{id:'a',source:'合成来源甲',observed_at:'2026-09-09',text:'喜欢散步'},"
                +"{id:'b',source:'合成来源乙',observed_at:'2026-09-10',text:'喜欢散步'}]");
            JSONObject second=new JSONObject("{id:'E2',source_id:'b',quote:'喜欢散步'}");
            String shown=ProfileEvidenceText.evidence(materials,second,false);
            require(shown.contains("资料2 · 合成来源乙 · 观察于 2026-09-10")&&!shown.contains("来源甲"),"same quote source");checks++;
            JSONArray reversed=new JSONArray().put(materials.getJSONObject(1)).put(materials.getJSONObject(0));
            require(ProfileEvidenceText.evidence(reversed,second,false).contains("资料1 · 合成来源乙"),"returned snapshot order");checks++;
            JSONArray duplicate=new JSONArray(materials.toString()).put(materials.getJSONObject(1));
            require(ProfileEvidenceText.evidence(duplicate,second,false).contains("来源无法唯一核对"),"duplicate material ID");checks++;
            require(ProfileEvidenceText.evidence(null,second,false).contains("来源无法唯一核对"),"missing snapshot");checks++;
            JSONObject missing=new JSONObject("{id:'E3',quote:'喜欢散步'}");
            require(ProfileEvidenceText.evidence(materials,missing,false).contains("来源无法唯一核对"),"missing profile source");checks++;
            require(ProfileEvidenceText.evidence(null,missing,true).contains("本次提交的聊天片段"),"reply context");checks++;
            JSONArray invalid=new JSONArray("[{id:null,source:'无效来源'}]");
            JSONObject nullId=new JSONObject("{id:'E4',source_id:null,quote:'喜欢散步'}");
            require(ProfileEvidenceText.evidence(invalid,nullId,false).contains("来源无法唯一核对"),"null IDs");checks++;
            JSONArray refs=new JSONArray("['E2']"),evidence=new JSONArray().put(second);
            require(ProfileEvidenceText.references(refs,evidence,materials,false).equals(shown),"observation source");checks++;
            evidence.put(second);
            require(ProfileEvidenceText.references(refs,evidence,materials,false).contains("依据无法唯一核对"),"duplicate evidence ID");checks++;
            require(ProfileEvidenceText.references(new JSONArray("['unknown']"),evidence,materials,false).contains("依据无法唯一核对"),"missing evidence ID");checks++;
            JSONObject error=new JSONObject("{error:'旧版错误',request_id:'synthetic-only'}");
            require(new NativeClient.RequestFailure(error,429).getMessage().equals("旧版错误\n问题编号：synthetic-only"),"legacy failure");checks++;
            error.put("budget_block",new JSONObject().put("message","本月额度不足，2026-10-01 08:00（北京时间）重新检查。"));
            NativeClient.RequestFailure failure=new NativeClient.RequestFailure(error,429);
            require(failure.statusCode==429&&failure.getMessage().contains("2026-10-01 08:00")&&!failure.getMessage().contains("旧版错误"),"budget failure");checks++;
            error.getJSONObject("budget_block").put("message","");
            require(new NativeClient.RequestFailure(error).getMessage().startsWith("旧版错误"),"empty budget fallback");checks++;
            result.putString("snapshot_contract","PASS");result.putInt("checks",checks);
            result.putString("scope","Android JSON and presentation contract only; UI touches and model quality separate");
            runner.finish(Activity.RESULT_OK,result);
        }catch(Exception error){result.putString("snapshot_contract","FAIL");result.putInt("checks",checks);result.putString("reason",error.toString());runner.finish(Activity.RESULT_CANCELED,result);}
    }
    private static void require(boolean condition,String name){if(!condition)throw new IllegalStateException(name);}
}
