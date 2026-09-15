package com.conversationlens.ime;

import android.content.Context;
import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.widget.*;
import java.util.ArrayList;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;
import com.conversationlens.ime.KeyboardAssistantPolicy.Mode;

/** User-approved context and editable suggestions, kept inside the active keyboard. */
final class ImeAssistantPanel extends ScrollView {
    private static final String CONTINUATION_EXPIRED = "本次连续维护已到期，临时片段与旧候选已清空。请重新选择客户后开启。";
    private static final String INPUT_EXPIRED = "输入现场已过期，请更换客户后重新选择并核对。";
    enum Task { PROFILE, OPENING, REPLY }
    interface Listener {
        void onBackToCustomers();
        void onInsertRequested(AssistSession session,String draft);
        void onImageRequested(Snapshot snapshot);
        void onCaptureRequested(Snapshot snapshot);
        void onCustomerDetailsRequested(Snapshot snapshot);
    }
    /** Only an explicit system-picker handoff may retain these unsent drafts. */
    static final class Snapshot {
        final KeyboardAssistantPanel.CustomerSelection customer;
        final NativeClient client;
        final Task task;
        final String text,buffer,kind,goal,date;
        final JSONArray materials;
        Snapshot(KeyboardAssistantPanel.CustomerSelection customer,NativeClient client,Task task,String text,String buffer,String kind,String goal,String date,JSONArray materials) {
            this.customer=customer;this.client=client;this.task=task;this.text=text;this.buffer=buffer;this.kind=kind;this.goal=goal;this.date=date;this.materials=materials;
        }
    }
    private static final String[] KINDS={"PROFILE_TEXT","MOMENTS_TEXT","CHAT_TEXT","USER_NOTE"};
    private static final String[] KIND_LABELS={"客户资料","朋友圈动态","聊天片段","本人补充"};
    private final Handler main=new Handler(Looper.getMainLooper());
    private final KeyboardAssistantPanel.Listener editors;
    private final Listener listener;
    private final LinearLayout body, materialRows, results, imageArea;
    private final TextView status;
    private final ArrayList<Button> actions=new ArrayList<>();
    private final ArrayList<JSONObject> materials=new ArrayList<>();
    private KeyboardAssistantPanel.CustomerSelection customer;
    private NativeClient client;
    private AssistSession session;
    private Task task;
    private KeyboardAssistantPanel.LocalEditor text,materialText,draft,observedDate;
    private Spinner kind,goal;
    private CheckBox approved,hostConfirmed,retryConfirmed;
    private Button analyze,insert;
    private Bitmap image;
    private Toast inputLimitToast;
    private boolean active,busy,setting,consuming;
    private int epoch;
    private String pendingRequest,retryOf;
    private String recoveryDraft="";
    private final ConversationContinuationPolicy continuation=new ConversationContinuationPolicy();
    private ConversationContinuationPolicy.Binding continuationBinding;
    private boolean continuationRequested,showContinuationHistory;
    private boolean continuationExpired;
    private int continuationGeneration;
    private Button continuationStart,continuationStop,nextFragment;
    private TextView continuationInfo,continuationHistory;

    ImeAssistantPanel(Context context,KeyboardAssistantPanel.Listener editors,Listener listener) {
        super(context);this.editors=editors;this.listener=listener;setFillViewport(false);
        setBackground(LensStyle.shape(context,LensStyle.BG,LensTokens.PANEL_RADIUS_DP,true));
        body=column();body.setFocusableInTouchMode(true);body.setPadding(dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.RELAXED_TOP_DP),dp(ImePanelLayout.GUTTER_DP),dp(ImePanelLayout.GUTTER_DP));addView(body);
        status=new TextView(context);LensStyle.text(status,LensTokens.TEXT_SUPPORT_SP,false);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        materialRows=column();results=column();imageArea=column();setVisibility(GONE);
    }
    @Override protected void onMeasure(int width,int height) {
        int cap=dp(Math.min(ImePanelLayout.ASSISTANT_MAX_DP,Math.max(ImePanelLayout.ASSISTANT_MIN_DP,Math.round(getResources().getConfiguration().screenHeightDp*ImePanelLayout.ASSISTANT_SCREEN_FRACTION))));
        int size=MeasureSpec.getSize(height),mode=MeasureSpec.getMode(height);
        super.onMeasure(width,MeasureSpec.makeMeasureSpec(mode==MeasureSpec.UNSPECIFIED?cap:Math.min(cap,size),MeasureSpec.AT_MOST));
    }
    void open(KeyboardAssistantPanel.CustomerSelection customer,NativeClient client,AssistSession session) {
        close();this.customer=customer;this.client=client;this.session=session;active=true;
        continuationBinding=new ConversationContinuationPolicy.Binding(customer.id,customer.pairId,session.host,session.context,UUID.randomUUID().toString());
        task=customer.mode==Mode.NEW?Task.PROFILE:Task.REPLY;setVisibility(VISIBLE);renderForm(null);
        final AssistSession owner=session;
        main.postDelayed(()->{if(active&&this.session==owner&&!owner.alive()){
            invalidateResult();status.setText(INPUT_EXPIRED);updateInputState();
        }},Math.max(0,owner.started+15*60000-SystemClock.elapsedRealtime()));
    }
    boolean isActive() {return active;}
    boolean permitsInsertion(AssistSession current,String value) {
        return active&&!busy&&!consuming&&session==current&&approved!=null&&approved.isChecked()
                &&hostConfirmed!=null&&hostConfirmed.isChecked()&&draft!=null&&value.equals(draft.getText().toString());
    }
    void revokeForImage() {
        changed();setting=true;if(hostConfirmed!=null)hostConfirmed.setChecked(false);setting=false;updateInputState();
    }
    void close() {
        continuation.stop();continuationGeneration++;continuationRequested=false;showContinuationHistory=false;continuationExpired=false;continuationBinding=null;
        active=false;epoch++;busy=false;consuming=false;setting=true;
        body.requestFocus();clearFields();body.removeAllViews();actions.clear();materials.clear();results.removeAllViews();materialRows.removeAllViews();imageArea.removeAllViews();status.setText("");
        if(image!=null){image.recycle();image=null;}
        customer=null;client=null;session=null;pendingRequest=null;retryOf=null;recoveryDraft="";setting=false;setVisibility(GONE);
    }
    private void clearFields() {
        if(text!=null)text.clearFocus();if(materialText!=null)materialText.clearFocus();if(draft!=null)draft.clearFocus();if(observedDate!=null)observedDate.clearFocus();
        text=null;materialText=null;draft=null;observedDate=null;kind=null;goal=null;insert=null;approved=null;hostConfirmed=null;retryConfirmed=null;
        continuationStart=null;continuationStop=null;nextFragment=null;continuationInfo=null;continuationHistory=null;
    }
    private void renderForm(Snapshot restored) {
        setting=true;body.requestFocus();clearFields();body.removeAllViews();actions.clear();results.removeAllViews();imageArea.removeAllViews();materialRows.removeAllViews();
        button(body,"更换客户",listener::onBackToCustomers);
        button(body,"客户资料、记忆与反馈",()->{if(editors.canSubmitEditor())listener.onCustomerDetailsRequested(snapshot());else status.setText("请先完成候选选字，再打开客户资料。");});
        label(body,"当前客户："+customer.name+" · "+customer.platform,LensTokens.TEXT_HEADING_SP,true);body.addView(status);
        if(!customer.notes.trim().isEmpty())label(body,"客户背景（由你填写，请核对）："+customer.notes,LensTokens.TEXT_SUPPORT_SP,false);
        if(customer.mode==Mode.NEW){
            LinearLayout tasks=new LinearLayout(getContext());body.addView(tasks);
            button(tasks,"新客画像",()->switchTask(Task.PROFILE));button(tasks,"新客破冰",()->switchTask(Task.OPENING));
        }
        label(body,task==Task.PROFILE?"整理有依据的客户画像":task==Task.OPENING?"准备自然的开场话":"准备聊天回复",LensTokens.TEXT_SUBHEADING_SP,true);
        if(task==Task.REPLY){
            continuationInfo=new TextView(getContext());LensStyle.text(continuationInfo,LensTokens.TEXT_SUPPORT_SP,false);body.addView(continuationInfo);
            continuationStart=button(body,"开启本次连续维护",this::startContinuation);
            // Stop remains available while a network request is pending. It revokes late callbacks.
            continuationStop=new Button(getContext());continuationStop.setText("停止本次连续维护");continuationStop.setContentDescription("停止本次连续维护");
            continuationStop.setFocusable(false);LensStyle.button(continuationStop,false);body.addView(continuationStop);
            continuationStop.setOnClickListener(v->{if(active)stopContinuation("已停止本次连续维护，临时片段已清空。已提交的分析可在客户历史中管理。");});
            button(body,"查看本次已批准片段",()->{showContinuationHistory=!showContinuationHistory;refreshContinuation();});
            continuationHistory=new TextView(getContext());LensStyle.text(continuationHistory,LensTokens.TEXT_SUPPORT_SP,false);body.addView(continuationHistory);
            goal=new ImeDropdownSpinner(getContext());goal.setAdapter(new ArrayAdapter<String>(getContext(),android.R.layout.simple_spinner_dropdown_item,new String[]{"自然接话","关心近况","修复误会","表达边界"}));
            goal.setContentDescription("本次回复目标");body.addView(goal);
            if(restored!=null)for(int i=0;i<goal.getCount();i++)if(goal.getItemAtPosition(i).equals(restored.goal))goal.setSelection(i);
            goal.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int i,long id){changed();}public void onNothingSelected(AdapterView<?> p){changed();}});
        }
        text=editor(task==Task.REPLY?"输入或粘贴聊天片段，请注明双方发言":task==Task.PROFILE?"本次画像关注点（选填，最多1000字）":"你想怎样开场（选填，最多1000字）",4301,task==Task.REPLY?4000:1000);
        if(restored!=null)text.setText(restored.text);body.addView(text);text.addTextChangedListener(watcher(this::changed));
        if(task!=Task.REPLY){
            kind=new ImeDropdownSpinner(getContext());kind.setAdapter(new ArrayAdapter<String>(getContext(),android.R.layout.simple_spinner_dropdown_item,KIND_LABELS));kind.setContentDescription("资料来源类型");body.addView(kind);
            if(restored!=null)for(int i=0;i<KINDS.length;i++)if(KINDS[i].equals(restored.kind))kind.setSelection(i);
            label(body,"观察日期默认今天，表示本次收集时间；可改为实际观察日期，不代表原帖发布日期。",LensTokens.TEXT_SUPPORT_SP,false);
            observedDate=new KeyboardAssistantPanel.LocalEditor(getContext(),editors,4304,"观察日期 YYYY-MM-DD");
            observedDate.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
            observedDate.setText(restored==null?new java.text.SimpleDateFormat("yyyy-MM-dd",java.util.Locale.ROOT).format(new java.util.Date()):restored.date);
            observedDate.addTextChangedListener(watcher(this::changed));body.addView(observedDate);
            materialText=editor("填写一份客户资料（最多2000字），校对后加入",4302,2000);
            if(restored!=null)materialText.setText(restored.buffer);body.addView(materialText);
            materialText.addTextChangedListener(watcher(this::changed));
            button(body,"加入这份资料",this::addMaterial);
            detach(materialRows);body.addView(materialRows);renderMaterials();
        }
        button(body,"选择一张图片",()->{if(editors.canSubmitEditor())listener.onImageRequested(snapshot());else status.setText("请先完成候选选字，再选择图片。");});
        button(body,"截取当前画面一次",()->{if(editors.canSubmitEditor())listener.onCaptureRequested(snapshot());else status.setText("请先完成候选选字，再截取画面。");});
        label(body,"截图须经过系统授权；返回后先核对画面、客户与文字。系统所选应用不代表已识别当前联系人。",LensTokens.TEXT_CAPTION_SP,false);
        detach(imageArea);body.addView(imageArea);renderImage();
        hostConfirmed=checkbox("已核对当前聊天对象是「"+customer.name+"」");
        approved=checkbox("已核对文字与资料，同意提交给连接的服务");
        approved.setOnCheckedChangeListener((v,on)->{if(!setting&&!on)invalidateResult();updateInputState();});
        hostConfirmed.setOnCheckedChangeListener((v,on)->{if(!setting&&!on)invalidateResult();updateInputState();});
        retryConfirmed=checkbox("上次请求可能已计费，确认再次生成并占用新的额度");retryConfirmed.setVisibility(retryOf==null?GONE:VISIBLE);
        retryConfirmed.setOnCheckedChangeListener((v,on)->updateInputState());
        analyze=button(body,task==Task.PROFILE?"分析已批准资料":"生成已批准内容",this::analyze);
        if(task==Task.REPLY)nextFragment=button(body,"补充下一段对话",this::nextContinuationFragment);
        detach(results);body.addView(results);
        status.setText(restored==null?"资料只在主动批准后提交。":"已恢复未提交资料，请重新核对客户和内容。旧批准与候选已失效。");
        setting=false;updateInputState();scrollTo(0,0);
    }
    private void switchTask(Task next) {
        if(busy||next==task)return;
        Snapshot keep=snapshot();invalidateResult();task=next;pendingRequest=null;retryOf=null;
        renderForm(new Snapshot(customer,client,next,keep.text,keep.buffer,keep.kind,keep.goal,keep.date,keep.materials));
    }
    Snapshot snapshot() {
        JSONArray saved=new JSONArray();for(JSONObject value:materials)saved.put(value);
        return new Snapshot(customer,client,task,value(text),value(materialText),kind==null?KINDS[0]:KINDS[kind.getSelectedItemPosition()],goal==null?"自然接话":goal.getSelectedItem().toString(),value(observedDate),saved);
    }
    void restore(Snapshot snapshot,Bitmap image,String message) {
        task=snapshot.task;materials.clear();
        for(int i=0;i<snapshot.materials.length();i++){JSONObject item=snapshot.materials.optJSONObject(i);if(item!=null)materials.add(item);}
        this.image=image;renderForm(snapshot);if(message!=null&&!message.isEmpty())status.append("\n"+message);
    }
    void onImage(Bitmap bitmap,String message) {
        if(!active){if(bitmap!=null)bitmap.recycle();return;}
        invalidateResult();if(image!=null)image.recycle();image=bitmap;renderImage();status.setText(message==null?"图片尚未提交，请先在本机识别并校对。":message);
    }
    private void renderImage() {
        imageArea.removeAllViews();if(image==null)return;
        ImageView preview=new ImageView(getContext());preview.setImageBitmap(image);preview.setAdjustViewBounds(true);preview.setMaxHeight(dp(ImePanelLayout.IMAGE_PREVIEW_MAX_DP));preview.setContentDescription("待校对图片，仅保存在本机内存");imageArea.addView(preview);
        button(imageArea,"在本机识别文字",this::recognizeImage);
        button(imageArea,"丢弃图片",()->{if(image!=null)image.recycle();image=null;imageArea.removeAllViews();changed();});
    }
    private void recognizeImage() {
        if(image==null||busy)return;
        if(!editors.canSubmitEditor()){status.setText("请先完成候选选字。");return;}
        final int ticket=++epoch;final Bitmap source=image;setBusy(true);status.setText("正在本机识别，未上传图片…");
        LocalChatOcr.Done done=new LocalChatOcr.Done(){
            public void success(String recognized){main.post(()->{if(!valid(ticket))return;setBusy(false);setting=true;
                KeyboardAssistantPanel.LocalEditor destination=task==Task.REPLY?text:materialText;
                String previous=value(destination);String combined=previous.isEmpty()?recognized:previous+"\n\n"+recognized;
                int limit=task==Task.REPLY?4000:2000;
                if(combined.length()>limit){setting=false;status.setText("识别内容超过单份 "+limit+" 字，请缩小图片范围或拆分为多份资料，未截断原文。");return;}
                destination.setText(combined);setting=false;changed();status.setText("识别完成。请逐字校对；资料图片不判断左右发言人。"+(task==Task.REPLY?"请核对双方发言。":"校对后再加入资料。"));
            });}
            public void failure(){main.post(()->{if(valid(ticket)){setBusy(false);status.setText("本机识别失败，请手动输入或换一张清晰图片。");}});}
        };
        if(task==Task.REPLY)LocalChatOcr.recognize(source,done);else LocalChatOcr.recognizeProfile(source,done);
    }
    private void addMaterial() {
        if(!editors.canSubmitEditor()){status.setText("请先选定候选字。");return;}
        String content=value(materialText).trim();if(content.isEmpty()){status.setText("请先填写资料。");return;}
        if(content.length()>2000){status.setText("单份资料不能超过 2000 字，请拆分后加入。");return;}
        if(OcrReview.hasUnresolvedMarkers(content)){status.setText("请校对并清除非聊天等识别提示后再加入。");return;}
        String date=value(observedDate).trim();
        try{java.text.SimpleDateFormat format=new java.text.SimpleDateFormat("yyyy-MM-dd",java.util.Locale.ROOT);format.setLenient(false);
            if(!date.matches("\\d{4}-\\d{2}-\\d{2}")||!format.format(format.parse(date)).equals(date))throw new IllegalArgumentException();
        }catch(Exception invalid){status.setText("请填写有效的观察日期，例如 2026-09-10。");return;}
        int chars=content.length();for(JSONObject item:materials)chars+=item.optString("text").length();
        if(materials.size()>=8||chars>4000){status.setText("最多加入 8 份资料，合计不超过 4000 字。");return;}
        int index=kind.getSelectedItemPosition();
        try{materials.add(new JSONObject().put("id",UUID.randomUUID().toString()).put("kind",KINDS[index]).put("text",content).put("source","主动提供的"+KIND_LABELS[index]).put("observed_at",date));}
        catch(Exception error){status.setText("资料格式不正确。");return;}
        materialText.setText("");changed();renderMaterials();status.setText("已加入资料，请核对后批准分析。");
    }
    private void renderMaterials() {
        materialRows.removeAllViews();int index=0;JSONArray snapshot=new JSONArray();for(JSONObject item:materials)snapshot.put(item);
        for(JSONObject item:materials){final JSONObject selected=item;label(materialRows,ProfileEvidenceText.material(snapshot,index++),LensTokens.TEXT_BODY_SP,false);button(materialRows,"移除这份资料",()->{materials.remove(selected);changed();renderMaterials();});}
    }
    private void changed() {
        if(setting)return;invalidateResult();pendingRequest=null;
        if(approved!=null){setting=true;approved.setChecked(false);setting=false;}updateInputState();
    }
    private void invalidateResult() {
        invalidateResult(true);
    }
    private void invalidateResult(boolean revokeSession) {
        if(setting)return;epoch++;if(revokeSession&&session!=null&&session.alive()&&(session.result!=null||pendingRequest!=null))session.invalidate();
        recoveryDraft="";
        if(draft!=null&&draft.hasFocus()){body.requestFocus();draft.clearFocus();}draft=null;insert=null;results.removeAllViews();consuming=false;
    }
    private void analyze() {
        if(busy||!validSession()||!editors.canSubmitEditor())return;
        if(!approved.isChecked()||!hostConfirmed.isChecked()){status.setText("请先核对客户，并批准提交内容。");return;}
        if(retryOf!=null&&!retryConfirmed.isChecked()){status.setText("请先确认可能重复计费，再主动生成。");return;}
        if(task!=Task.REPLY&&!value(materialText).trim().isEmpty()){status.setText("还有未加入的资料，请先加入或清空。");return;}
        if(task==Task.PROFILE&&materials.isEmpty()){status.setText("请至少加入一份已校对的客户资料。");return;}
        if(task==Task.REPLY&&value(text).trim().isEmpty()){status.setText("请先提供聊天片段。");return;}
        if(OcrReview.hasUnresolvedMarkers(value(text))){status.setText("请先校对文字并清理识别提示。");return;}
        String retainedDraft=recoveryDraft;
        String request=pendingRequest==null?UUID.randomUUID().toString():pendingRequest;
        String submittedText=value(text),submittedGoal=task==Task.PROFILE?"新客画像":task==Task.OPENING?"新客破冰":goal.getSelectedItem().toString();
        ConversationContinuationPolicy.Request prepared=null;
        if(continuationRequested){
            if(!continuing()){status.setText("本次连续维护已过期，请停止后重新开启。");updateInputState();return;}
            ConversationContinuationPolicy.Decision decision=retryOf==null
                ?continuation.prepare(continuationBinding,submittedText,submittedGoal,session.context,request,true,SystemClock.elapsedRealtime())
                :continuation.explicitRetry(continuationBinding,submittedText,submittedGoal,retryOf,request,true,retryConfirmed.isChecked(),SystemClock.elapsedRealtime());
            if(!decision.canSend()){
                status.setText("DUPLICATE".equals(decision.code.name())?"这段对话已分析，请补充新的内容；本次未请求模型。":"本次片段不能继续提交。请先完成原请求，或停止后重新开启；最多累计 8 段、4000 字。");return;
            }
            prepared=decision.request;request=prepared.requestId;submittedText=prepared.text;submittedGoal=prepared.goal;
            if(!session.context.equals(prepared.context)){stopContinuation("原请求现场已变化，已停止连续维护。请重新核对，服务仍保留原请求的计费记录。");return;}
            invalidateResult(false);
        }else invalidateResult();
        recoveryDraft=retainedDraft;
        pendingRequest=request;final int ticket=++epoch;final AssistSession current=session;final int revision=current.revision;
        final ConversationContinuationPolicy.Request continuousRequest=prepared;
        final Task currentTask=task;final NativeClient currentClient=client;
        try{
            JSONObject payload=new JSONObject().put("person_id",customer.id).put("pair_id",customer.pairId).put("context",current.context).put("host",current.host)
                    .put("approved",true).put("mode","model").put("request_id",request).put("task_type",task.name()).put("text",submittedText)
                    .put("goal",submittedGoal);
            if(task!=Task.REPLY){JSONArray list=new JSONArray();for(JSONObject item:materials)list.put(item);payload.put("materials",list);}
            if(continuousRequest!=null&&continuousRequest.acknowledgePossibleCharge)payload.put("retry_of",continuousRequest.retryOf).put("acknowledge_possible_charge",true);
            else if(retryOf!=null)payload.put("retry_of",retryOf).put("acknowledge_possible_charge",true);
            retryOf=null;retryConfirmed.setVisibility(GONE);
            setBusy(true);status.setText("正在生成，请稍候…");
            NativeClient.IO.execute(()->{try{
                JSONObject response=currentClient.call("analyze",payload);
                main.post(()->{if(!valid(ticket))return;if(!current.alive()||current.revision!=revision){expiredRequest();return;}setBusy(false);
                    JSONObject person=response.optJSONObject("person");
                    if(person==null||!customer.id.equals(person.optString("id"))||!customer.pairId.equals(person.optString("pair_id"))
                            ||!current.context.equals(response.optString("context"))||!current.host.equals(response.optString("host"))||!currentTask.name().equals(response.optString("task_type","REPLY"))){
                        current.invalidate();status.setText("返回内容与本次客户或任务不符，请重新核对。");return;
                    }
                    if(continuousRequest!=null&&!continuation.finish(continuationBinding,continuousRequest,SystemClock.elapsedRealtime())){stopContinuation("本次连续维护已停止或过期，返回结果不再用于插入。");return;}
                    pendingRequest=null;current.result=response;current.deadline=SystemClock.elapsedRealtime()+120000;showResult(response);updateInputState();
                });
            }catch(Exception failure){main.post(()->{if(!valid(ticket))return;if(!current.alive()||current.revision!=revision){expiredRequest();return;}setBusy(false);
                status.setText(failure.getMessage()==null?"请求结果未确认，请检查网络后再操作。":failure.getMessage());
                if(failure instanceof NativeClient.RequestFailure){String retry=((NativeClient.RequestFailure)failure).retryOf;if(!retry.isEmpty()){
                    if(continuousRequest==null||continuation.retryRequired(continuationBinding,continuousRequest,retry,SystemClock.elapsedRealtime())){retryOf=retry;pendingRequest=null;retryConfirmed.setChecked(false);retryConfirmed.setVisibility(VISIBLE);}
                }}
                if(continuousRequest!=null)status.append("\n原片段已锁定，可按原请求重查，或停止本次连续维护；不会自动重试。");
                updateInputState();
            });}});
        }catch(Exception failure){setBusy(false);status.setText("内容格式不正确，请检查后重试。");}
    }
    private void expiredRequest(){
        setBusy(false);invalidateResult();status.setText("本次输入现场已失效，请更换客户后重新选择并核对。");updateInputState();
    }
    private void showResult(JSONObject response) {
        results.removeAllViews();status.setText(task==Task.PROFILE?"画像已生成，请核对依据与不确定项。":"建议已生成，请选择并编辑候选。");
        label(results,KeyboardAssistantPanel.budgetText(response.optJSONObject("budget")),LensTokens.TEXT_SUPPORT_SP,false);
        label(results,response.optString("summary"),LensTokens.TEXT_SUBHEADING_SP,true);
        JSONArray snapshotMaterials=response.optJSONArray("materials"),evidence=response.optJSONArray("evidence");
        if(task==Task.PROFILE){
            label(results,"本次分析的资料快照",LensTokens.TEXT_HEADING_SP,true);
            if(snapshotMaterials==null||snapshotMaterials.length()==0)label(results,"未返回资料快照，来源无法核对。",LensTokens.TEXT_BODY_SP,false);
            else for(int i=0;i<Math.min(8,snapshotMaterials.length());i++)label(results,ProfileEvidenceText.material(snapshotMaterials,i),LensTokens.TEXT_SUPPORT_SP,false);
            JSONObject profile=response.optJSONObject("profile");
            if(profile!=null){JSONArray observations=profile.optJSONArray("observations");if(observations!=null)for(int i=0;i<observations.length();i++){JSONObject item=observations.optJSONObject(i);if(item!=null){String kind=item.optString("kind");String label="INFERRED".equals(kind)?"推测（待核实）": "SELF_DECLARED".equals(kind)?"资料自述（待核对）":"资料观察（待核对）";label(results,label+"："+item.optString("content")+"\n"+ProfileEvidenceText.references(item.optJSONArray("evidence_refs"),evidence,snapshotMaterials,false)+"\n不确定性："+item.optString("uncertainty"),LensTokens.TEXT_BODY_SP,false);}}
                label(results,"尚不清楚："+profile.optString("unknowns"),LensTokens.TEXT_BODY_SP,false);}
        }else{
            JSONArray candidates=response.optJSONArray("candidates");
            if(candidates!=null&&candidates.length()>0&&response.optString("ticket_id").length()>0&&!response.isNull("ticket_id")){
                draft=editor("选择候选后可用本键盘修改",4303,12000);
                draft.addTextChangedListener(watcher(()->{if(session!=null)session.draft=value(draft);updateInputState();}));
                if(!recoveryDraft.isEmpty())button(results,"恢复上次编辑稿（请重新核对）",()->{draft.setText(recoveryDraft);draft.requestFocus();});
                for(int i=0;i<candidates.length();i++){JSONObject item=candidates.optJSONObject(i);if(item==null)continue;final String value=item.optString("text");button(results,value,()->{draft.requestFocus();draft.beginLocalEdit();try{draft.setText(value);draft.setSelection(draft.length());}finally{draft.endLocalEdit();}updateInputState();});}
                results.addView(draft);insert=button(results,"确认正在与「"+customer.name+"」聊天并插入",()->listener.onInsertRequested(session,value(draft)));
            }else label(results,"本次没有可插入的候选。",LensTokens.TEXT_BODY_SP,false);
        }
        label(results,"策略："+response.optString("strategy")+"\n原因："+response.optString("reason")+"\n风险："+response.optString("risk"),LensTokens.TEXT_BODY_SP,false);
        if(evidence!=null)for(int i=0;i<Math.min(24,evidence.length());i++){JSONObject item=evidence.optJSONObject(i);if(item!=null)label(results,ProfileEvidenceText.evidence(snapshotMaterials,item,task==Task.REPLY),LensTokens.TEXT_SUPPORT_SP,false);}
    }
    void setConsuming(boolean value) {consuming=value;setBusy(value);if(value)status.setText("正在确认插入…");}
    void insertionFailed(String message) {insertionFailed(message,true);}
    void insertionFailed(String message,boolean preserveDraft) {
        String retained=preserveDraft&&validSession()?value(draft):"";
        setBusy(false);consuming=false;invalidateResult();
        if(!retained.isEmpty()){
            recoveryDraft=retained;
            label(results,"上次编辑稿暂存于本面板。请先检查聊天输入框；重新生成后可恢复编辑稿。离开面板或到期即清空。",LensTokens.TEXT_SUPPORT_SP,false);
            draft=editor("暂存编辑稿（尚未确认插入）",4303,12000);draft.setText(retained);
            draft.addTextChangedListener(watcher(()->{recoveryDraft=value(draft);}));results.addView(draft);
        }
        status.setText(message);updateInputState();
    }
    private boolean continuing(){return continuationRequested&&continuationBinding!=null&&continuation.alive(continuationBinding,SystemClock.elapsedRealtime());}
    private void startContinuation(){
        if(task!=Task.REPLY||!validSession()||busy||!editors.canSubmitEditor())return;
        if(retryOf!=null||(pendingRequest!=null&&session.result==null)){status.setText("请先查明原请求结果，再开启连续维护。");return;}
        changed();session.invalidate();
        continuationExpired=false;continuationRequested=continuation.start(continuationBinding,SystemClock.elapsedRealtime());
        final int owner=++continuationGeneration;
        long remaining=Math.max(0,Math.min(ConversationContinuationPolicy.LIFETIME_MS,session.started+15*60000-SystemClock.elapsedRealtime()));
        main.postDelayed(()->{if(active&&continuationRequested&&continuationGeneration==owner)stopContinuation(CONTINUATION_EXPIRED);},remaining);
        setting=true;approved.setChecked(false);hostConfirmed.setChecked(false);setting=false;
        status.setText("已开启。每次只补充新的真实对话，核对后主动生成；不会自动读屏或自动发送。");updateInputState();
    }
    private void stopContinuation(String message){
        continuationExpired=CONTINUATION_EXPIRED.equals(message);
        boolean unresolved=continuation.hasPending();
        continuation.stop();continuationGeneration++;continuationRequested=false;showContinuationHistory=false;
        invalidateResult();if(session!=null){session.consuming=false;session.invalidate();}
        pendingRequest=null;retryOf=null;setting=true;
        if(text!=null)text.setText("");if(approved!=null)approved.setChecked(false);if(hostConfirmed!=null)hostConfirmed.setChecked(false);
        if(retryConfirmed!=null){retryConfirmed.setChecked(false);retryConfirmed.setVisibility(GONE);}setting=false;
        setBusy(false);updateInputState();
        // The shared input scene expires at the same deadline as continuation.
        // Keep the specific stop/expiry receipt visible after generic state refresh.
        status.setText(message+(unresolved?"\n已发出的请求可能仍在处理或计费，停止不会撤回已产生的费用。":""));
    }
    private void nextContinuationFragment(){
        if(!continuing()||busy||continuation.hasPending()||session.result==null)return;
        invalidateResult();pendingRequest=null;setting=true;text.setText("");approved.setChecked(false);hostConfirmed.setChecked(false);setting=false;
        status.setText("请补充下一段真实对话。此前已批准的片段会随本次一起提交；建议草稿不会当成已发送记录。");updateInputState();
    }
    boolean afterContinuousInsertion(){
        if(!continuing())return false;
        consuming=false;busy=false;session.consuming=false;nextContinuationFragment();setBusy(false);
        status.setText("已插入草稿，请自行检查并发送。收到新对话后可在本面板补充，再次核对客户和内容。");return true;
    }
    private void refreshContinuation(){
        if(continuationInfo==null)return;
        boolean running=continuing(),waiting=running&&continuation.hasPending();
        continuationStart.setVisibility(continuationRequested?GONE:VISIBLE);continuationStop.setVisibility(continuationRequested?VISIBLE:GONE);
        continuationStop.setEnabled(active);
        continuationInfo.setText(continuationRequested?(running?"本次连续维护：已批准 "+continuation.roundCount()+" 段，累计 "+continuation.approvedText().length()+" / 4000 字。"+(waiting?"正在保留原请求。":"") :"本次连续维护已过期，请停止后重新开启。")
            :"可开启临时连续维护，每轮主动提供并批准新对话；不自动读取聊天。最多 8 段、4000 字、15 分钟，离开此面板（包括选图和客户资料）即停止。已提交分析保存在客户历史中。");
        continuationHistory.setText(running&&showContinuationHistory?continuation.approvedText():"");
        continuationHistory.setVisibility(running&&showContinuationHistory?VISIBLE:GONE);
        if(nextFragment!=null){nextFragment.setVisibility(running?VISIBLE:GONE);nextFragment.setEnabled(running&&!busy&&!waiting&&session!=null&&session.result!=null&&editors.canSubmitEditor());}
        if(!busy){if(text!=null)text.setEnabled(!waiting);if(goal!=null)goal.setEnabled(!waiting);if(approved!=null)approved.setEnabled(!waiting);if(hostConfirmed!=null)hostConfirmed.setEnabled(!waiting);}
    }
    void updateInputState() {
        boolean idle=active&&!busy&&!consuming&&editors.canSubmitEditor();
        if(analyze!=null)analyze.setEnabled(idle&&validSession()&&(!continuationRequested||continuing())&&approved!=null&&approved.isChecked()&&hostConfirmed!=null&&hostConfirmed.isChecked()&&(retryOf==null||retryConfirmed.isChecked()));
        if(insert!=null)insert.setEnabled(idle&&validSession()&&session.result!=null&&SystemClock.elapsedRealtime()<session.deadline&&hostConfirmed.isChecked()&&!value(draft).trim().isEmpty());
        if(active&&session!=null&&!session.alive())status.setText(continuationExpired?CONTINUATION_EXPIRED:INPUT_EXPIRED);
        refreshContinuation();
    }
    private void setBusy(boolean value) {
        busy=value;for(Button button:actions)button.setEnabled(!value);
        for(EditText editor:new EditText[]{text,materialText,draft,observedDate})if(editor!=null)editor.setEnabled(!value);
        if(kind!=null)kind.setEnabled(!value);if(goal!=null)goal.setEnabled(!value);
        if(approved!=null)approved.setEnabled(!value);if(hostConfirmed!=null)hostConfirmed.setEnabled(!value);updateInputState();
    }
    private boolean valid(int ticket) {return active&&ticket==epoch;}
    private boolean validSession() {return active&&session!=null&&session.alive()&&client!=null;}
    private KeyboardAssistantPanel.LocalEditor editor(String hint,int id,int max) {
        KeyboardAssistantPanel.LocalEditor value=new KeyboardAssistantPanel.LocalEditor(getContext(),editors,id,hint);
        value.setSingleLine(false);value.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);value.setMaxLines(ImePanelLayout.ASSISTANT_EDITOR_MAX_LINES);value.setMinLines(ImePanelLayout.EDITOR_MIN_LINES);
        value.setFilters(new InputFilter[]{(source,start,end,destination,replaceStart,replaceEnd)->{
            CharSequence replacement=WholeEditLimitPolicy.filter(source,start,end,destination,replaceStart,replaceEnd,max);
            if(replacement!=null){
                String message="本次输入会超过 "+max+" 个字符，未加入；原文字与所选内容已保留。请缩短或分段输入。";
                status.setText(message);
                if(inputLimitToast!=null)inputLimitToast.cancel();
                inputLimitToast=Toast.makeText(getContext(),"超过 "+max+" 字符，本次输入未加入，原文字已保留",Toast.LENGTH_SHORT);
                inputLimitToast.show();
            }
            return replacement;
        }});
        value.setSaveEnabled(false);return value;
    }
    private CheckBox checkbox(String title) {CheckBox box=new CheckBox(getContext());box.setText(title);box.setTextColor(LensStyle.INK);box.setTextSize(LensTokens.CHECKBOX_TEXT_SP);box.setMinHeight(dp(LensTokens.CHECKBOX_MIN_HEIGHT_DP));box.setButtonTintList(android.content.res.ColorStateList.valueOf(LensStyle.GREEN));box.setFocusable(false);body.addView(box);return box;}
    private Button button(LinearLayout parent,String title,Runnable action) {Button button=new Button(getContext());button.setText(title);button.setContentDescription(title);button.setFocusable(false);LensStyle.button(button,false);button.setTextSize(LensTokens.COMPACT_ACTION_TEXT_SP);button.setPadding(dp(LensTokens.COMPACT_ACTION_PADDING_X_DP),dp(LensTokens.ASSISTANT_ACTION_PADDING_Y_DP),dp(LensTokens.COMPACT_ACTION_PADDING_X_DP),dp(LensTokens.ASSISTANT_ACTION_PADDING_Y_DP));button.setOnClickListener(v->{if(active&&!busy)action.run();});parent.addView(button,parent.getOrientation()==LinearLayout.HORIZONTAL?new LinearLayout.LayoutParams(0,-2,1):new LinearLayout.LayoutParams(-1,-2));actions.add(button);return button;}
    private LinearLayout column() {LinearLayout layout=new LinearLayout(getContext());layout.setOrientation(LinearLayout.VERTICAL);return layout;}
    private void detach(View view) {if(view.getParent()!=null)((LinearLayout)view.getParent()).removeView(view);}
    private void label(LinearLayout parent,String text,int size,boolean heading) {if(text==null||text.isEmpty())return;TextView label=new TextView(getContext());LensStyle.text(label,size,heading);label.setText(text);parent.addView(label,LensStyle.space(getContext()));}
    private static String value(EditText editor) {return editor==null?"":editor.getText().toString();}
    private TextWatcher watcher(Runnable changed) {return new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable text){changed.run();}};}
    private int dp(int value) {return LensStyle.dp(getContext(),value);}
}
