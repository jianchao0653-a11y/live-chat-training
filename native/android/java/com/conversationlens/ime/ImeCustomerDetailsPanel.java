package com.conversationlens.ime;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.function.BooleanSupplier;

/** Customer maintenance within the current IME visibility session. No model calls. */
final class ImeCustomerDetailsPanel extends ScrollView {
    private static final String[] PLATFORMS={"微信","抖音","快手","视频号"};
    private static final String[] STAGES={"初识","熟悉中","稳定联系","需要修复"};
    private static final String[] KINDS={"FACT","SELF_DECLARED","INFERRED","DISPUTED","EXPIRED"};
    private static final String[] KIND_LABELS={"已核对事实","对方自述","待核实推测","已有反证","已过期"};
    private static final String[] OUTCOMES={"UNKNOWN","POSITIVE","MIXED","NEGATIVE"};
    private static final String[] OUTCOME_LABELS={"未知／尚无回应","积极回应","混合回应","消极回应"};
    private final KeyboardAssistantPanel.Listener editorListener;
    private final Runnable onBack,onDataChanged;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final LinearLayout body;
    private final TextView message;
    private final ArrayList<KeyboardAssistantPanel.LocalEditor> editors=new ArrayList<>();
    private final ArrayList<View> inputs=new ArrayList<>();
    private final ArrayList<Action> actions=new ArrayList<>();
    private KeyboardAssistantPanel.CustomerSelection selected;
    private NativeClient client;
    private LinearLayout confirmation,writeReview;
    private PendingWrite pendingWrite;
    private boolean navigationConfirmation;
    private boolean active,attached,busy,loadOnAttach;
    private int epoch,nextEditorId=4400;

    private interface Done {void run(JSONObject value) throws Exception;}
    private static final class PendingWrite {
        final String path,draft,personId;
        final NativeClient connection;
        final Runnable reread;
        boolean submitted,acknowledged,reconciling,rejected;
        PendingWrite(String path,String draft,String personId,NativeClient connection,Runnable reread){
            this.path=path;this.draft=draft;this.personId=personId;this.connection=connection;this.reread=reread;
        }
    }
    private static final class Action {
        final Button button;
        final boolean needsEditor,allowedDuringReview;
        final BooleanSupplier allowed;
        Action(Button button,boolean needsEditor,BooleanSupplier allowed,boolean allowedDuringReview){this.button=button;this.needsEditor=needsEditor;this.allowed=allowed;this.allowedDuringReview=allowedDuringReview;}
    }

    ImeCustomerDetailsPanel(Context context,KeyboardAssistantPanel.Listener editorListener,Runnable onBack,Runnable onDataChanged){
        super(context);this.editorListener=editorListener;this.onBack=onBack;this.onDataChanged=onDataChanged;
        setSaveEnabled(false);setSaveFromParentEnabled(false);setFillViewport(false);setClipToPadding(false);
        setBackground(LensStyle.shape(context,LensStyle.BG,LensTokens.PANEL_RADIUS_DP,true));
        body=column();body.setFocusableInTouchMode(true);body.setPadding(dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.COMPACT_TOP_DP),dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.GUTTER_DP));addView(body);
        message=new TextView(context);message.setSaveEnabled(false);LensStyle.text(message,LensTokens.TEXT_SUPPORT_SP,false);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);setVisibility(GONE);
    }

    @Override protected void onMeasure(int width,int height){
        int screen=getResources().getConfiguration().screenHeightDp;
        int cap=dp(Math.min(ImePanelLayout.DETAILS_MAX_DP,Math.max(ImePanelLayout.DETAILS_MIN_DP,Math.round(screen*ImePanelLayout.DETAILS_SCREEN_FRACTION))));
        int size=MeasureSpec.getSize(height),kind=MeasureSpec.getMode(height);
        super.onMeasure(width,MeasureSpec.makeMeasureSpec(kind==MeasureSpec.UNSPECIFIED?cap:Math.min(size,cap),MeasureSpec.AT_MOST));
    }
    @Override protected void onAttachedToWindow(){
        super.onAttachedToWindow();attached=true;
        if(active&&loadOnAttach){loadOnAttach=false;loadPerson(false);}
        updateInputState();
    }
    @Override protected void onDetachedFromWindow(){
        attached=false;close();super.onDetachedFromWindow();
    }

    void open(KeyboardAssistantPanel.CustomerSelection selection,NativeClient connection){
        close();if(selection==null||connection==null)return;
        selected=selection;client=connection;active=true;setVisibility(VISIBLE);
        page("客户资料");label(body,"正在读取「"+selection.name+"」的资料。",LensTokens.TEXT_BODY_SP,false);
        if(attached)loadPerson(false);else loadOnAttach=true;
    }
    KeyboardAssistantPanel.CustomerSelection selection(){return selected;}
    void close(){
        active=false;epoch++;busy=false;loadOnAttach=false;client=null;selected=null;pendingWrite=null;
        clearEditors();removeConfirmation();removeWriteReview();body.removeAllViews();actions.clear();inputs.clear();
        message.setText("");setVisibility(GONE);
    }
    void updateInputState(){
        boolean enabled=active&&attached&&!busy&&client!=null&&selected!=null;
        for(View input:inputs)input.setEnabled(enabled&&(pendingWrite==null||(navigationConfirmation&&confirmation!=null&&inside(input,confirmation))));
        for(Action action:actions)action.button.setEnabled(enabled&&(pendingWrite==null||action.allowedDuringReview)&&(!action.needsEditor||editorListener.canSubmitEditor())&&action.allowed.getAsBoolean());
    }

    private void clearEditors(){
        body.requestFocus();
        for(KeyboardAssistantPanel.LocalEditor editor:editors){editor.clearFocus();editor.setText("");}
        editors.clear();
    }
    private void page(String title){
        epoch++;clearEditors();removeConfirmation();removeWriteReview();body.removeAllViews();inputs.clear();actions.clear();
        label(body,title+(selected==null?"":" · "+selected.name),LensTokens.TEXT_PAGE_TITLE_SP,true);
        message.setText("");body.addView(message);
        button(body,"返回辅助面板",this::back,false,()->true,true);
        scrollTo(0,0);
    }
    private void back(){
        if(pendingWrite!=null){
            confirm("返回辅助面板","保存结果尚待核对。离开会清除本页保留文字；再次进入后请先查看最新资料。",onBack,false);return;
        }
        if(editors.isEmpty()){onBack.run();return;}
        confirm("返回辅助面板","离开后本页尚未保存的文字将被丢弃。",onBack,false);
    }
    private void setBusy(boolean value){busy=value;updateInputState();}
    private boolean valid(int ticket,NativeClient connection,String personId){
        return active&&attached&&isAttachedToWindow()&&ticket==epoch&&client==connection&&selected!=null&&selected.id.equals(personId);
    }
    private void call(String path,JSONObject payload,boolean mutation,Done done){
        if(!active||!attached||busy||client==null||selected==null)return;
        if(!path.startsWith("library/")){message.setText("资料请求无效。");return;}
        // mutate() checked composition before disabling the focused LocalEditor.
        // Sending consumes only that validated, bound request; checking the now
        // disabled editor again would reject a legitimate confirmed submission.
        if(mutation&&(pendingWrite==null||pendingWrite.submitted||!path.equals(pendingWrite.path)
                ||client!=pendingWrite.connection||!selected.id.equals(pendingWrite.personId))){
            message.setText("保存请求已失效，请重新核对资料。");return;
        }
        final NativeClient current=client;final String personId=selected.id;
        if(mutation){
            onDataChanged.run();
            if(!active||!attached||client!=current||selected==null||!personId.equals(selected.id))return;
            pendingWrite.submitted=true;
        }
        final PendingWrite review=!mutation&&pendingWrite!=null&&pendingWrite.reconciling?pendingWrite:null;
        final int ticket=++epoch;setBusy(true);message.setText(mutation?"正在保存…":review!=null?"正在只读核对最新资料…":"正在读取…");
        NativeClient.IO.execute(()->{
            try{
                JSONObject result=current.call(path,payload);
                main.post(()->{
                    if(!valid(ticket,current,personId))return;
                    setBusy(false);
                    if(mutation&&pendingWrite!=null)pendingWrite.acknowledged=true;
                    try{done.run(result);if(review!=null)finishWriteReview(review);}
                    catch(Exception failure){
                        if(pendingWrite!=null){pendingWrite.reconciling=false;showWriteReview();}
                        message.setText("返回资料格式不完整，请重新读取核对；尚未再次提交。");
                    }
                });
            }catch(Exception failure){
                final String detail=errorText(failure);
                final int status=failure instanceof NativeClient.RequestFailure?((NativeClient.RequestFailure)failure).statusCode:0;
                main.post(()->{
                    if(!valid(ticket,current,personId))return;
                    setBusy(false);
                    if(review!=null&&review==pendingWrite&&status==404&&review.path.equals(personPath()+"/delete")){
                        pendingWrite=null;selected=null;onBack.run();return;
                    }
                    if(pendingWrite!=null){
                        removeConfirmation();pendingWrite.reconciling=false;
                        if(mutation)pendingWrite.rejected=status>=400&&status<500;
                        showWriteReview();
                        message.setText((mutation?(status==409?"资料状态已变化或暂不可写入，旧选择已暂停。请先读取最新资料核对。\n":"未确认保存结果，提交文字仍保留。请先读取最新资料核对，不能直接再次保存。\n"):
                            pendingWrite.acknowledged?"服务已确认写入，但最新资料尚未读取。请只读核对，不要重复保存。\n":"最新资料尚未读取，提交文字仍保留；再次保存继续暂停。\n")+detail);
                    }else message.setText("读取未完成，当前内容仍保留。\n"+detail);
                });
            }
        });
    }
    private void mutate(String path,JSONObject payload,Runnable reread){
        if(!active||!attached||busy||client==null||selected==null)return;
        if(pendingWrite!=null){message.setText("请先读取最新资料核对上次保存结果。");showWriteReview();return;}
        if(!editorListener.canSubmitEditor()){message.setText("请先选定候选字，再保存资料。");return;}
        pendingWrite=new PendingWrite(path,submissionDraft(),selected.id,client,reread);
        removeConfirmation();updateInputState();
        call(path,payload,true,value->reconcileWrite());
    }
    private String submissionDraft(){
        StringBuilder text=new StringBuilder();
        for(KeyboardAssistantPanel.LocalEditor editor:editors){
            if(text.length()>0)text.append("\n\n");text.append(editor.getHint()).append("：\n").append(editor.getText());
        }
        for(View input:inputs){
            if(confirmation!=null&&inside(input,confirmation))continue;
            if(input instanceof Spinner){
                Spinner spinner=(Spinner)input;if(text.length()>0)text.append("\n\n");
                text.append(spinner.getContentDescription()).append("：").append(spinner.getSelectedItem());
            }else if(input instanceof CheckBox&&((CheckBox)input).isChecked()){
                if(text.length()>0)text.append("\n\n");text.append("所选观察：").append(((CheckBox)input).getText());
            }
        }
        return text.toString();
    }
    private void reconcileWrite(){
        if(pendingWrite==null||busy)return;
        removeConfirmation();pendingWrite.reconciling=true;
        pendingWrite.reread.run();
    }
    private void showWriteReview(){
        if(pendingWrite==null)return;
        removeWriteReview();writeReview=column();
        label(writeReview,"本次提交的文字与选择仍保留。先读取最新资料核对，再决定下一步；不会自动重放写入。",LensTokens.TEXT_SUPPORT_SP,false);
        button(writeReview,"重新读取最新资料核对",this::reconcileWrite,false,()->true,true);
        body.addView(writeReview,Math.min(2,body.getChildCount()));updateInputState();scrollTo(0,0);
    }
    private void removeWriteReview(){
        if(writeReview==null)return;
        LinearLayout removed=writeReview;
        actions.removeIf(action->inside(action.button,removed));inputs.removeIf(input->inside(input,removed));
        body.removeView(removed);removed.removeAllViews();writeReview=null;
    }
    private void finishWriteReview(PendingWrite review){
        if(pendingWrite!=review)return;
        pendingWrite=null;removeWriteReview();
        message.setText(review.acknowledged?"已保存并读取最新资料，请核对本次结果。":review.rejected?
            "此前请求被服务拒绝；已读取最新资料，请重新核对后操作。":"已读取最新资料。请对照本次提交内容核对结果，不会自动重复保存。");
        if(!review.draft.isEmpty()){
            LinearLayout retained=card();label(retained,"本次提交内容 · 保留供核对",LensTokens.TEXT_SUBHEADING_SP,true);
            label(retained,review.draft,LensTokens.TEXT_SUPPORT_SP,false);
        }
        updateInputState();
    }
    private String personPath(){return "library/people/"+selected.id;}
    private JSONObject checkedPerson(JSONObject person) throws Exception {
        if(selected==null||!selected.id.equals(person.optString("id")))throw new Exception("Customer mismatch");
        KeyboardAssistantPanel.CustomerSelection updated=new KeyboardAssistantPanel.CustomerSelection(selected.mode,person);
        if(updated.pairId.isEmpty()||!selected.pairId.equals(updated.pairId))throw new Exception("Relationship mismatch");
        selected=updated;return person;
    }
    private void loadPerson(boolean memories){
        if(!active||busy)return;
        call(personPath(),null,false,value->{JSONObject person=checkedPerson(value);if(memories)renderMemories(person);else renderPerson(person);});
    }
    private void renderPerson(JSONObject person){
        page("客户资料");
        label(body,"平台："+person.optString("platform")+"\n关系阶段："+person.optString("stage")+"\n分类："+segmentLabel(person.optString("segment")),LensTokens.TEXT_BODY_SP,false);
        label(body,"背景："+emptyLabel(person.optString("notes"))+"\n边界："+emptyLabel(person.optString("boundary")),LensTokens.TEXT_BODY_SP,false);
        button(body,"修改客户与关系资料",()->editPerson(person),false,()->true);
        button(body,"记忆与标记",()->renderMemories(person),false,()->true);
        button(body,"查看分析历史与反馈",this::loadHistory,false,()->true);
        button(body,"刷新客户资料",()->loadPerson(false),false,()->true);
        button(body,"删除此客户及关联资料",()->confirm("删除客户",
            "将删除「"+selected.name+"」的客户、关系、记忆、分析和反馈，无法在应用中撤销。",()->{
                mutate(personPath()+"/delete",new JSONObject(),()->loadPerson(false));
            }),true,()->true);
        updateInputState();
    }
    private void editPerson(JSONObject person){
        page("修改客户资料");
        label(body,"保存更正会清除该客户旧分析与反馈，让之后的建议使用新资料。已保存记忆仍需分别核对。",LensTokens.TEXT_BODY_SP,false);
        KeyboardAssistantPanel.LocalEditor name=field("客户昵称",person.optString("name"),60,false);
        Spinner platform=options("聊天平台",PLATFORMS,person.optString("platform"));
        Spinner stage=options("关系阶段",STAGES,person.optString("stage"));
        KeyboardAssistantPanel.LocalEditor notes=field("客户背景",person.optString("notes"),3000,true);
        KeyboardAssistantPanel.LocalEditor boundary=field("关系边界",person.optString("boundary"),1000,true);
        button(body,"核对并保存客户资料",()->confirm("保存客户资料",
            "保存当前填写内容，并清除该客户旧分析与反馈。",()->{
                try{
                    JSONObject payload=new JSONObject().put("name",required(name,"客户昵称")).put("platform",platform.getSelectedItem())
                        .put("stage",stage.getSelectedItem()).put("notes",value(notes)).put("boundary",value(boundary));
                    mutate(personPath()+"/save",payload,()->loadPerson(false));
                }catch(Exception failure){message.setText("请填写客户昵称并核对资料。");}
            }),true,()->!value(name).isEmpty());
        button(body,"放弃修改并重新读取",()->confirm("放弃本页修改","尚未保存的文字将被丢弃。",()->loadPerson(false)),false,()->true);
        updateInputState();
    }

    private void renderMemories(JSONObject person){
        page("记忆与标记");
        label(body,"推测只有单独确认后才能作为推测参考，仍不等于事实。每位客户最多保存 100 条。",LensTokens.TEXT_BODY_SP,false);
        button(body,"添加记忆或标记",()->editMemory(null),false,()->true);
        button(body,"刷新记忆",()->loadPerson(true),false,()->true);
        button(body,"返回客户资料",()->loadPerson(false),false,()->true);
        JSONArray claims=person.optJSONArray("claims");
        if(claims==null||claims.length()==0)label(body,"还没有保存的记忆或标记。",LensTokens.TEXT_BODY_SP,false);
        if(claims!=null)for(int i=0;i<Math.min(100,claims.length());i++){
            JSONObject claim=claims.optJSONObject(i);if(claim==null)continue;
            LinearLayout card=card();
            label(card,(i+1)+" · "+("TAG".equals(claim.optString("category"))?"标记":"记忆")+" · "+kindLabel(claim.optString("kind"))+
                " · "+("PENDING".equals(claim.optString("review_state"))?"待确认":"已确认状态"),LensTokens.TEXT_BODY_SP,true);
            label(card,claim.optString("content")+"\n来源："+claim.optString("source")+"\n"+claim.optString("created_at"),LensTokens.TEXT_BODY_SP,false);
            button(card,"修改或删除第 "+(i+1)+" 条",()->editMemory(claim),false,()->true);
            if("INFERRED".equals(claim.optString("kind"))&&"PENDING".equals(claim.optString("review_state"))){
                button(card,"明确确认此条推测",()->confirm("确认推测",
                    "确认后这条内容可作为推测参考，仍保留推测性质与来源；该客户旧分析与反馈会清除。",()->{
                        try{mutate("library/memories/"+claim.optString("id")+"/confirm",new JSONObject().put("confirmed",true),()->loadPerson(true));}
                        catch(Exception failure){message.setText("确认请求未提交，请重新核对。");}
                    }),true,()->true);
            }
        }
        updateInputState();
    }
    private void editMemory(JSONObject claim){
        page(claim==null?"添加记忆或标记":"更正记忆或标记");
        label(body,"请填写来源。保存为推测时保持待确认，不能自动变成事实。"+
            (claim==null?"":"更正会清除该客户旧分析与反馈。"),LensTokens.TEXT_BODY_SP,false);
        Spinner kind=options("内容性质",KIND_LABELS,kindLabel(claim==null?"SELF_DECLARED":claim.optString("kind")));
        Spinner category=options("保存类别",new String[]{"聊天记忆","客户标记"},claim!=null&&"TAG".equals(claim.optString("category"))?"客户标记":"聊天记忆");
        KeyboardAssistantPanel.LocalEditor content=field("记忆内容",claim==null?"":claim.optString("content"),1000,true);
        KeyboardAssistantPanel.LocalEditor source=field("记忆来源",claim==null?"":claim.optString("source"),500,true);
        button(body,"核对并保存记忆",()->confirm("保存记忆",
            claim==null?"只保存当前填写的内容和来源；推测仍需单独确认。":"保存当前更正，并清除该客户旧分析与反馈。",()->{
                try{
                    JSONObject payload=new JSONObject().put("content",required(content,"记忆内容")).put("source",required(source,"记忆来源"))
                        .put("kind",KINDS[kind.getSelectedItemPosition()]).put("category",category.getSelectedItemPosition()==1?"TAG":"MEMORY");
                    String path=claim==null?personPath()+"/memories":"library/memories/"+claim.optString("id")+"/save";
                    mutate(path,payload,()->loadPerson(true));
                }catch(Exception failure){message.setText("请填写记忆内容和来源。");}
            }),true,()->!value(content).isEmpty()&&!value(source).isEmpty());
        if(claim!=null)button(body,"删除此条记忆",()->confirm("删除记忆",
            "删除此条记忆并清除该客户旧分析与反馈，无法在应用中撤销。",()->
                mutate("library/memories/"+claim.optString("id")+"/delete",new JSONObject(),()->loadPerson(true))),true,()->true);
        button(body,"放弃修改并返回记忆",()->confirm("放弃本页修改","尚未保存的文字将被丢弃。",()->loadPerson(true)),false,()->true);
        updateInputState();
    }

    private void loadHistory(){
        if(!active||busy)return;
        call(personPath()+"/history",null,false,this::renderHistory);
    }
    private void renderHistory(JSONObject response){
        page("分析历史与反馈");
        label(body,"最近 30 条记录。画像是一份材料快照；新截图不会自动撤销旧资料。插入文字不代表已经发送或得到积极回应。",LensTokens.TEXT_BODY_SP,false);
        button(body,"刷新历史",this::loadHistory,false,()->true);
        button(body,"返回客户资料",()->loadPerson(false),false,()->true);
        JSONArray history=response.optJSONArray("history");
        if(history==null||history.length()==0)label(body,"暂时没有分析记录。",LensTokens.TEXT_BODY_SP,false);
        if(history!=null)for(int i=0;i<Math.min(30,history.length());i++){
            JSONObject analysis=history.optJSONObject(i);if(analysis==null)continue;
            LinearLayout card=card();label(card,analysis.optString("created_at")+" · "+analysis.optString("goal"),LensTokens.TEXT_BODY_SP,true);
            label(card,analysis.optString("summary"),LensTokens.TEXT_BODY_SP,false);
            JSONObject outcome=analysis.optJSONObject("outcome");
            if(outcome!=null)label(card,"反馈："+outcomeLabel(outcome.optString("status"))+"\n"+outcome.optString("note"),LensTokens.TEXT_SUPPORT_SP,false);
            button(card,"查看第 "+(i+1)+" 条详情",()->loadAnalysis(analysis.optString("id")),false,()->true);
        }
        updateInputState();
    }
    private void loadAnalysis(String id){call("library/analyses/"+id,null,false,this::renderAnalysis);}
    private void renderAnalysis(JSONObject response) throws Exception {
        JSONObject analysis=response.getJSONObject("analysis");
        if(selected==null||!selected.id.equals(analysis.optString("person_id")))throw new Exception("Customer mismatch");
        JSONObject result=analysis.getJSONObject("result");final String id=analysis.getString("id");
        boolean stale=response.optBoolean("stale",true);
        page("分析详情");
        label(body,analysis.optString("created_at")+" · "+analysis.optString("goal"),LensTokens.TEXT_BODY_SP,true);
        label(body,stale?"客户资料已变化：此快照仅供核对，不能纳入记忆。":"这是本次资料快照，尚未自动加入客户记忆。",LensTokens.TEXT_BODY_SP,false);
        label(body,result.optString("summary")+"\n策略："+result.optString("strategy")+"\n说明："+result.optString("reason")+"\n注意："+result.optString("risk"),LensTokens.TEXT_BODY_SP,false);
        JSONObject judge=result.optJSONObject("judge");
        if(judge!=null)label(body,"审核："+judge.optString("verdict")+"\n"+judge.optString("reason"),LensTokens.TEXT_SUPPORT_SP,false);
        JSONArray materials=result.optJSONArray("materials"),evidence=result.optJSONArray("evidence");
        if(materials!=null&&materials.length()>0){
            label(body,"本次提供的资料",LensTokens.TEXT_HEADING_SP,true);
            for(int i=0;i<Math.min(8,materials.length());i++){
                JSONObject material=materials.optJSONObject(i);if(material==null)continue;
                label(body,ProfileEvidenceText.material(materials,i),LensTokens.TEXT_SUPPORT_SP,false);
            }
        }
        if(evidence!=null&&evidence.length()>0){
            label(body,"原文依据",LensTokens.TEXT_HEADING_SP,true);
            for(int i=0;i<Math.min(24,evidence.length());i++){
                JSONObject item=evidence.optJSONObject(i);if(item==null)continue;
                label(body,ProfileEvidenceText.evidence(materials,item,"REPLY".equals(result.optString("task_type"))),LensTokens.TEXT_SUPPORT_SP,false);
            }
        }
        JSONObject profile=result.optJSONObject("profile");
        JSONArray observations=profile==null?null:profile.optJSONArray("observations");
        final ArrayList<CheckBox> picks=new ArrayList<>();final ArrayList<String> observationIds=new ArrayList<>();
        final boolean maySave="PROFILE".equals(result.optString("task_type"))&&!stale&&!"SAFE_STOP".equals(result.optString("route"))&&judge!=null&&"PASS".equals(judge.optString("verdict"));
        if(observations!=null&&observations.length()>0){
            label(body,"画像观察 · 逐项核对后选择",LensTokens.TEXT_HEADING_SP,true);
            for(int i=0;i<Math.min(16,observations.length());i++){
                JSONObject observation=observations.optJSONObject(i);if(observation==null)continue;
                String heading=observationKindLabel(observation.optString("kind"))+" · "+observation.optString("content");
                if(maySave){
                    CheckBox pick=check(body,heading);pick.setContentDescription("选择画像观察 "+observation.optString("id"));picks.add(pick);observationIds.add(observation.optString("id"));
                }else label(body,heading,LensTokens.TEXT_BODY_SP,false);
                if(!observation.optString("uncertainty").isEmpty())label(body,"限定："+observation.optString("uncertainty"),LensTokens.TEXT_SUPPORT_SP,false);
                label(body,ProfileEvidenceText.references(observation.optJSONArray("evidence_refs"),evidence,materials,"REPLY".equals(result.optString("task_type"))),LensTokens.TEXT_SUPPORT_SP,false);
            }
        }
        JSONArray unknowns=profile==null?null:profile.optJSONArray("unknowns");
        if(unknowns!=null&&unknowns.length()>0){
            label(body,"仍需确认",LensTokens.TEXT_HEADING_SP,true);
            for(int i=0;i<Math.min(16,unknowns.length());i++)label(body,"• "+unknowns.optString(i),LensTokens.TEXT_SUPPORT_SP,false);
        }
        if(maySave&&!picks.isEmpty()){
            label(body,"一次最多选择 12 条。推测保存后仍为待确认；保存会更新客户版本，同一旧快照不能随后重复纳入。",LensTokens.TEXT_SUPPORT_SP,false);
            button(body,"核对并保存所选观察",()->confirm("保存画像观察",
                "将当前勾选项保存为客户记忆；推测仍保持待确认，不自动成为事实。",()->{
                    try{
                        JSONArray ids=new JSONArray();for(int i=0;i<picks.size();i++)if(picks.get(i).isChecked())ids.put(observationIds.get(i));
                        if(ids.length()<1||ids.length()>12){message.setText("请选择 1 至 12 条观察。");return;}
                        mutate("library/analyses/"+id+"/memories",new JSONObject().put("confirmed",true).put("observation_ids",ids),()->loadPerson(true));
                    }catch(Exception failure){message.setText("保存请求未提交，请重新核对所选观察。");}
                }),true,()->countChecked(picks)>0&&countChecked(picks)<=12);
        }
        JSONObject outcome=analysis.optJSONObject("outcome");
        if(outcome!=null)label(body,"实际反馈："+outcomeLabel(outcome.optString("status"))+"\n"+outcome.optString("note"),LensTokens.TEXT_BODY_SP,false);
        button(body,outcome==null?"填写实际反馈":"修改实际反馈",()->editFeedback(analysis),false,()->true);
        if(outcome!=null)button(body,"删除反馈及该客户旧分析",()->confirm("删除反馈",
            "将清除该客户旧分析与反馈，避免被删除的反馈继续影响其他建议。",()->
                mutate("library/feedback/"+id+"/delete",new JSONObject(),()->loadPerson(false))),true,()->true);
        button(body,"删除这份分析快照",()->confirm("删除分析快照",
            "删除本条分析及其反馈，依赖记录可能失效。先前单独保存的记忆不会自动撤销，请另行核对或更正。",()->
                mutate("library/analyses/"+id+"/delete",new JSONObject(),this::loadHistory)),true,()->true);
        button(body,"返回分析历史",this::loadHistory,false,()->true);
        updateInputState();
    }

    private void editFeedback(JSONObject analysis){
        page("填写实际反馈");
        JSONObject old=analysis.optJSONObject("outcome");final String id=analysis.optString("id");
        label(body,"只记录实际观察。不知道是否发送或如何回应时选择未知，不能从建议插入推断积极回应。更正已有反馈会使依赖旧反馈的分析失效。",LensTokens.TEXT_BODY_SP,false);
        Spinner outcome=options("实际反馈状态",OUTCOME_LABELS,outcomeLabel(old==null?"UNKNOWN":old.optString("status")));
        KeyboardAssistantPanel.LocalEditor note=field("实际观察",old==null?"":old.optString("note"),2000,true);
        KeyboardAssistantPanel.LocalEditor draft=field("实际使用的文字（可空）",old==null?"":old.optString("draft"),12000,true);
        outcome.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onItemSelected(AdapterView<?> parent,View view,int position,long itemId){updateInputState();}
            public void onNothingSelected(AdapterView<?> parent){updateInputState();}
        });
        button(body,"核对并保存反馈",()->confirm("保存实际反馈",
            "保存当前实际观察；更正旧反馈时，依赖旧反馈的建议将失效。",()->{
                try{
                    String status=OUTCOMES[outcome.getSelectedItemPosition()];
                    if(!"UNKNOWN".equals(status)&&value(note).isEmpty()){message.setText("非未知反馈请填写实际观察。");return;}
                    JSONObject payload=new JSONObject().put("status",status).put("note",value(note)).put("draft",value(draft));
                    mutate("library/feedback/"+id+"/save",payload,this::loadHistory);
                }catch(Exception failure){message.setText("反馈请求未提交，请核对内容。");}
            }),true,()->outcome.getSelectedItemPosition()==0||!value(note).isEmpty());
        button(body,"放弃修改并返回记录",()->confirm("放弃本页修改","尚未保存的反馈文字将被丢弃。",()->loadAnalysis(id)),false,()->true);
        updateInputState();
    }

    private void confirm(String title,String explanation,Runnable action){
        confirm(title,explanation,action,true);
    }
    private void confirm(String title,String explanation,Runnable action,boolean mutation){
        if(!active||busy||(mutation&&pendingWrite!=null))return;
        removeConfirmation();confirmation=column();confirmation.setPadding(dp(LensTokens.CONFIRM_PADDING_DP),dp(LensTokens.CONFIRM_PADDING_DP),dp(LensTokens.CONFIRM_PADDING_DP),dp(LensTokens.CONFIRM_PADDING_DP));
        navigationConfirmation=!mutation;
        confirmation.setBackground(LensStyle.shape(getContext(),LensStyle.TINT,LensTokens.CONFIRM_RADIUS_DP,true));
        body.addView(confirmation,LensStyle.space(getContext()));
        label(confirmation,title+" · "+selected.name,LensTokens.TEXT_SUBHEADING_SP,true);label(confirmation,explanation,LensTokens.TEXT_BODY_SP,false);
        CheckBox agreed=check(confirmation,"我已核对当前客户和上述影响");
        button(confirmation,"确认"+title,action,true,agreed::isChecked,!mutation);
        button(confirmation,"取消",this::removeConfirmation,false,()->true,true);
        updateInputState();post(()->{if(active&&confirmation!=null)smoothScrollTo(0,confirmation.getTop());});
    }
    private void removeConfirmation(){
        if(confirmation==null)return;
        LinearLayout removed=confirmation;
        actions.removeIf(action->inside(action.button,removed));inputs.removeIf(input->inside(input,removed));
        body.removeView(removed);removed.removeAllViews();confirmation=null;navigationConfirmation=false;
    }
    private static boolean inside(View child,View ancestor){
        android.view.ViewParent parent=child.getParent();
        while(parent instanceof View){if(parent==ancestor)return true;parent=parent.getParent();}
        return false;
    }
    private KeyboardAssistantPanel.LocalEditor field(String hint,String text,int max,boolean multiline){
        KeyboardAssistantPanel.LocalEditor editor=new KeyboardAssistantPanel.LocalEditor(getContext(),editorListener,++nextEditorId,hint);
        editor.setSaveEnabled(false);editor.setSaveFromParentEnabled(false);
        editor.setFilters(new InputFilter[]{new InputFilter.LengthFilter(max)});
        if(multiline){editor.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);editor.setSingleLine(false);editor.setMinLines(ImePanelLayout.EDITOR_MIN_LINES);editor.setMaxLines(ImePanelLayout.DETAILS_EDITOR_MAX_LINES);}
        editor.setText(text);editor.setSelection(editor.length());editors.add(editor);inputs.add(editor);body.addView(editor,LensStyle.space(getContext()));
        editor.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable value){updateInputState();}});
        return editor;
    }
    private Spinner options(String title,String[] values,String selectedValue){
        label(body,title,LensTokens.TEXT_SUPPORT_SP,false);Spinner spinner=new ImeDropdownSpinner(getContext());spinner.setSaveEnabled(false);spinner.setSaveFromParentEnabled(false);
        spinner.setContentDescription(title);spinner.setAdapter(new ArrayAdapter<String>(getContext(),android.R.layout.simple_spinner_dropdown_item,values));
        for(int i=0;i<values.length;i++)if(values[i].equals(selectedValue))spinner.setSelection(i);
        inputs.add(spinner);body.addView(spinner,new LinearLayout.LayoutParams(-1,dp(LensTokens.SELECTOR_MIN_HEIGHT_DP)));return spinner;
    }
    private CheckBox check(LinearLayout parent,String title){
        CheckBox box=new CheckBox(getContext());box.setSaveEnabled(false);box.setSaveFromParentEnabled(false);box.setText(title);box.setContentDescription(title);
        box.setMinHeight(dp(LensTokens.CHECKBOX_MIN_HEIGHT_DP));LensStyle.text(box,LensTokens.TEXT_BODY_SP,false);box.setOnCheckedChangeListener((button,checked)->updateInputState());
        inputs.add(box);parent.addView(box,new LinearLayout.LayoutParams(-1,-2));return box;
    }
    private Button button(LinearLayout parent,String title,Runnable action,boolean needsEditor,BooleanSupplier allowed){
        return button(parent,title,action,needsEditor,allowed,false);
    }
    private Button button(LinearLayout parent,String title,Runnable action,boolean needsEditor,BooleanSupplier allowed,boolean allowedDuringReview){
        Button button=new Button(getContext());button.setSaveEnabled(false);button.setSaveFromParentEnabled(false);button.setText(title);button.setContentDescription(title);
        button.setFocusable(false);LensStyle.button(button,title.startsWith("确认")||title.startsWith("核对"));button.setTextSize(LensTokens.COMPACT_ACTION_TEXT_SP);
        button.setOnClickListener(view->{if(active&&attached&&!busy&&(pendingWrite==null||allowedDuringReview)&&allowed.getAsBoolean()&&(!needsEditor||editorListener.canSubmitEditor()))action.run();});
        actions.add(new Action(button,needsEditor,allowed,allowedDuringReview));parent.addView(button,LensStyle.space(getContext()));return button;
    }
    private LinearLayout column(){LinearLayout column=new LinearLayout(getContext());column.setSaveEnabled(false);column.setSaveFromParentEnabled(false);column.setOrientation(LinearLayout.VERTICAL);return column;}
    private LinearLayout card(){LinearLayout card=column();card.setPadding(dp(LensTokens.CARD_PADDING_X_DP),dp(LensTokens.CARD_PADDING_Y_DP),dp(LensTokens.CARD_PADDING_X_DP),dp(LensTokens.CARD_PADDING_Y_DP));card.setBackground(LensStyle.shape(getContext(),LensStyle.SURFACE,LensTokens.CARD_RADIUS_DP,true));body.addView(card,LensStyle.space(getContext()));return card;}
    private void label(LinearLayout parent,String text,int size,boolean heading){TextView label=new TextView(getContext());label.setSaveEnabled(false);label.setText(text);LensStyle.text(label,size,heading);parent.addView(label,LensStyle.space(getContext()));}
    private static String value(EditText editor){return editor.getText().toString().trim();}
    private static String required(EditText editor,String label) throws Exception {String value=value(editor);if(value.isEmpty())throw new Exception(label);return value;}
    private static String kindLabel(String code){for(int i=0;i<KINDS.length;i++)if(KINDS[i].equals(code))return KIND_LABELS[i];return code;}
    private static String observationKindLabel(String code){return "FACT".equals(code)?"资料观察（待核对）":"SELF_DECLARED".equals(code)?"资料自述（待核对）":"INFERRED".equals(code)?"推测（待核实）":code;}
    private static String outcomeLabel(String code){for(int i=0;i<OUTCOMES.length;i++)if(OUTCOMES[i].equals(code))return OUTCOME_LABELS[i];return OUTCOME_LABELS[0];}
    private static String segmentLabel(String code){return "NEW".equals(code)?"新用户":"MAINTAIN".equals(code)?"老用户":"待分类";}
    private static String emptyLabel(String value){return value.isEmpty()?"未填写":value;}
    private static int countChecked(ArrayList<CheckBox> boxes){int count=0;for(CheckBox box:boxes)if(box.isChecked())count++;return count;}
    private static String errorText(Exception failure){String value=failure.getMessage();if(value==null||value.trim().isEmpty())return "请检查网络或重新登录。";return value.length()>500?value.substring(0,500):value;}
    private int dp(int value){return LensStyle.dp(getContext(),value);}
}
