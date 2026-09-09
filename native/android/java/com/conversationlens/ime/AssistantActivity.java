package com.conversationlens.ime;

import android.app.Activity;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.text.*;
import android.widget.*;
import org.json.*;
import android.content.Intent;
import android.app.NotificationManager;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjectionManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import java.io.*;

public final class AssistantActivity extends Activity {
    private LinearLayout body, results;
    private TextView status;
    private EditText endpoint, code, transcript, draft;
    private Spinner people, goal, mode;
    private CheckBox approved;
    private NativeClient client;
    private AssistSession session;
    private JSONArray roster=new JSONArray();
    private int work, rosterWork;
    private boolean setting;
    private boolean cloud;
    private String pendingRequest;
    private String acknowledgedRetry;
    private JSONObject feedbackResult;
    private LinearLayout imagePanel;
    private TransientForm restored;
    private static final class TransientForm {
        String text, personId; int goal, mode;
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);LensStyle.window(this);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);cloud=CloudSettings.enabled(this);
        session=AssistSession.current;
        restored=(TransientForm)getLastNonConfigurationInstance();
        ScrollView scroll=new ScrollView(this);body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(LensStyle.dp(this,20),LensStyle.dp(this,20),LensStyle.dp(this,20),LensStyle.dp(this,24));body.setBackgroundColor(LensStyle.BG);scroll.setFillViewport(true);scroll.addView(body);
        scroll.setOnApplyWindowInsetsListener((v,i)->{int top=i.getSystemWindowInsetTop(),bottom=i.getSystemWindowInsetBottom();if(android.os.Build.VERSION.SDK_INT>=30){top=i.getInsets(android.view.WindowInsets.Type.systemBars()).top;bottom=i.getInsets(android.view.WindowInsets.Type.systemBars()|android.view.WindowInsets.Type.ime()).bottom;}v.setPadding(0,top,0,bottom);return i;});
        label("观微 · 聊天建议",24);label("仅分析你核对并批准的片段。返回聊天后再次确认人物，候选只插入输入框，发送由你完成。",15);
        status=label("请连接服务，再准备聊天片段",14);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        LensStyle.section(body,cloud?"账号与人物":"设备连接");
        endpoint=edit("服务地址",2101,false);endpoint.setText("http://127.0.0.1:4317");endpoint.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        code=edit("电脑设置页的六位配对码",2102,false);code.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        if(cloud){endpoint.setVisibility(View.GONE);code.setVisibility(View.GONE);button("登录与人物资料",()->{changed();startActivity(new Intent(this,LibraryActivity.class));});}
        else {button("配对连接",()->pair());button("断开并清除本机连接",()->disconnect());}
        try{client=NativeClient.load(this);if(client!=null){endpoint.setText(client.endpoint);loadRoster();}}catch(Exception e){status.setText("连接凭据不可用，请重新配对");}
        feedbackControls();
        if(session==null || !session.alive()){label("连接后，请回到聊天输入框，点击键盘上的“建议”。",16);setContentView(scroll);return;}
        label("原输入应用："+session.host,13);
        LensStyle.section(body,"01  核对人物与目标");
        label("人物",13);people=spinner(new String[]{"正在加载人物"});label("本次目标",13);goal=spinner(new String[]{"自然接话","关心近况","修复误会","表达边界"});label("分析方式",13);mode=spinner(cloud?new String[]{"联网聊天建议"}:new String[]{"本机服务规则试算","GPT 分析（需电脑配置）"});
        LensStyle.section(body,"02  准备聊天片段");
        transcript=edit("粘贴或输入你批准的聊天片段，标明说话人",2103,true);
        label("截图在本机识别。请将发言校对为“我：”和“对方：”，删除标题、时间等内容；受保护的黑屏请改用粘贴。",14);
        button("截取一次屏幕（系统授权）",()->requestCapture());
        button("选择一张聊天截图",()->{changed();startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE),42);});
        imagePanel=new LinearLayout(this);imagePanel.setOrientation(LinearLayout.VERTICAL);body.addView(imagePanel);
        approved=new CheckBox(this);approved.setText("已核对人物和片段，同意提交给连接的服务");approved.setTextColor(LensStyle.INK);approved.setTextSize(15);approved.setMinHeight(LensStyle.dp(this,48));approved.setButtonTintList(android.content.res.ColorStateList.valueOf(LensStyle.GREEN));body.addView(approved,LensStyle.space(this));
        button("分析已批准片段",()->analyze());
        LensStyle.section(body,"03  审阅与编辑候选");
        results=new LinearLayout(this);results.setOrientation(LinearLayout.VERTICAL);body.addView(results);
        button("取消建议并返回",()->{AssistSession.clear();returnToChat();});
        TextWatcher watcher=new TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){changed();}public void afterTextChanged(Editable e){}};
        transcript.addTextChangedListener(watcher);
        android.widget.AdapterView.OnItemSelectedListener listener=new android.widget.AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int pos,long id){changed();}public void onNothingSelected(AdapterView<?> p){changed();}};
        people.setOnItemSelectedListener(listener);goal.setOnItemSelectedListener(listener);mode.setOnItemSelectedListener(listener);
        approved.setOnCheckedChangeListener((b,on)->{if(!on)changed();});
        if(restored!=null){setting=true;transcript.setText(restored.text);goal.setSelection(restored.goal);mode.setSelection(restored.mode);setting=false;status.setText("已保留片段；界面变化后的旧候选失效，请重新批准分析");}
        setContentView(scroll);
    }
    @Override public Object onRetainNonConfigurationInstance(){
        if(transcript==null||session==null||client==null)return null;TransientForm form=new TransientForm();form.text=transcript.getText().toString();form.goal=goal.getSelectedItemPosition();form.mode=mode.getSelectedItemPosition();int index=people.getSelectedItemPosition();form.personId=index>=0&&index<roster.length()?roster.optJSONObject(index).optString("id"):"";return form;
    }
    @Override protected void onResume(){super.onResume();AssistSession.helperShowing=true;showImage();if(cloud){try{NativeClient loaded=NativeClient.load(this);if(loaded!=null){if(client==null||!loaded.token.equals(client.token))resetAccountForm();client=loaded;loadRoster();}else{client=null;resetAccountForm();status.setText("请先登录并建立人物资料。");}}catch(Exception e){client=null;resetAccountForm();status.setText("请重新登录。");}}}
    private void resetAccountForm(){changed();rosterWork++;roster=new JSONArray();restored=null;
        if(transcript!=null)transcript.setText("");if(draft!=null)draft.setText("");
        if(people!=null)people.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[0]));
        if(session!=null){session.clearImage();session.captureMessage="";}showImage();
        AssistSession.clearFeedback();
    }
    @Override protected void onPause(){AssistSession.helperShowing=false;super.onPause();}
    private void changed(){if(setting)return;work++;pendingRequest=null;feedbackResult=null;if(session!=null)session.invalidate();if(results!=null)results.removeAllViews();if(approved!=null){setting=true;approved.setChecked(false);setting=false;}}
    private void pair(){
        changed();final int token=++work;final String url=endpoint.getText().toString(),pin=code.getText().toString();status.setText("正在配对…");
        NativeClient.IO.execute(()->{try{NativeClient pending=new NativeClient(url,"");JSONObject response=pending.call("pair",new JSONObject().put("code",pin).put("name",android.os.Build.MODEL));NativeClient connected=new NativeClient(pending.endpoint,response.getString("token"));runOnUiThread(()->{if(isDestroyed()||token!=work)return;try{NativeClient.save(this,connected);client=connected;code.setText("");loadRoster();}catch(Exception e){error(e);}});}catch(Exception e){report(token,e);}});
    }
    private void disconnect(){
        changed();AssistSession.clear();session=null;client=null;restored=null;roster=new JSONArray();
        AssistSession.clearFeedback();
        NativeClient.forget(this);stopService(new Intent(this,CaptureService.class));
        setting=true;
        if(transcript!=null)transcript.setText("");if(draft!=null)draft.setText("");code.setText("");
        if(people!=null)people.setAdapter(null);
        setting=false;hideKeyboard();
        // Recreate the disconnected page to remove feedback closures and all private views.
        // onRetainNonConfigurationInstance must not carry a disconnected transcript forward.
        recreate();
    }
    private void loadRoster(){
        final NativeClient c=client;final int ticket=++rosterWork;
        final int oldIndex=people==null?-1:people.getSelectedItemPosition();
        final String selectedId=oldIndex>=0&&oldIndex<roster.length()?roster.optJSONObject(oldIndex).optString("id"):restored==null?"":restored.personId;
        NativeClient.IO.execute(()->{try{JSONObject response=c.call("roster",null);runOnUiThread(()->{
            if(isDestroyed()||c!=client||ticket!=rosterWork)return;
            JSONArray next=response.optJSONArray("people");if(next==null){status.setText("人物列表不可用，请重试。");return;}
            JSONObject streamer=response.optJSONObject("streamer");String name=streamer==null?"待设置主播":streamer.optString("name","待设置主播");
            JSONObject budget=response.optJSONObject("budget");
            status.setText(cloud?"主播："+name+" · "+next.length()+" 位客户 · 今日已用 "+(budget==null?0:budget.optInt("used_today"))+" 次":"已连接 · 主播 "+name);
            if(!next.toString().equals(roster.toString()) || people!=null&&people.getAdapter().getCount()!=next.length()){
                changed();roster=next;
                if(people!=null){String[] names=new String[roster.length()];int selected=0;
                    for(int i=0;i<names.length;i++){JSONObject p=roster.optJSONObject(i);names[i]=p.optString("name")+" · "+p.optString("platform");if(p.optString("id").equals(selectedId))selected=i;}
                    people.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,names));people.setSelection(selected);
                }
            }
            if(session!=null)session.client=c;
        });}catch(Exception e){runOnUiThread(()->{if(!isDestroyed()&&c==client&&ticket==rosterWork)error(e);});}});
    }
    private void analyze(){
        if(session==null||!session.alive()){status.setText("输入现场已失效，请返回聊天重新点击建议");return;}
        if(client==null||roster.length()==0||people.getSelectedItemPosition()<0){status.setText(cloud?"请先登录，并在人物资料中新建人物":"请先配对，并在电脑建立人物关系");return;}
        if(!approved.isChecked()){status.setText("请先核对并批准片段");return;}
        if(transcript.getText().toString().contains("待核对")){status.setText("请先校对识别结果：将发言标为“我：”或“对方：”，删除标题、时间等非聊天内容。");return;}
        final String requestId=pendingRequest==null?java.util.UUID.randomUUID().toString():pendingRequest;
        changed();pendingRequest=requestId;final int token=++work;final AssistSession s=session;final int revision=s.revision;final NativeClient c=client;s.client=c;
        try{
            JSONObject person=roster.getJSONObject(people.getSelectedItemPosition());JSONObject payload=new JSONObject().put("person_id",person.getString("id")).put("pair_id",person.getString("pair_id")).put("context",s.context).put("host",s.host).put("approved",true).put("text",transcript.getText().toString()).put("goal",goal.getSelectedItem().toString()).put("mode",cloud||mode.getSelectedItemPosition()!=0?"model":"local");
            if(cloud)payload.put("request_id",requestId);
            if(acknowledgedRetry!=null){payload.put("retry_of",acknowledgedRetry).put("acknowledge_possible_charge",true);acknowledgedRetry=null;}
            status.setText("正在分析…");hideKeyboard();
            NativeClient.IO.execute(()->{try{JSONObject response=c.call("analyze",payload);runOnUiThread(()->{if(isDestroyed()||token!=work||!s.alive()||s.revision!=revision)return;s.result=response;s.deadline=SystemClock.elapsedRealtime()+120000;showResult(response);});}catch(Exception e){report(token,e);}});
        }catch(Exception e){error(e);}
    }
    private void showResult(JSONObject response){
        status.setText(response.optString("mode").equals("model")?(cloud?"聊天建议已生成 · 请审阅候选":"GPT 分析完成 · 请审阅候选"):"规则试算完成 · 未调用 GPT");results.removeAllViews();feedbackResult=response;
        TextView summary=new TextView(this);summary.setText(response.optString("summary"));LensStyle.text(summary,15,false);results.addView(summary,LensStyle.space(this));
        Button details=new Button(this);details.setText("查看策略、风险与原话依据");LensStyle.button(details,false);
        details.setOnClickListener(v->{StringBuilder text=new StringBuilder("策略：").append(response.optString("strategy")).append("\n原因：").append(response.optString("reason")).append("\n风险：").append(response.optString("risk")).append("\n\n原话依据：");JSONArray evidence=response.optJSONArray("evidence");if(evidence!=null)for(int i=0;i<evidence.length();i++)text.append("\n• ").append(evidence.optJSONObject(i).optString("quote"));new android.app.AlertDialog.Builder(this).setTitle("本次建议的依据").setMessage(text.toString()).setPositiveButton("关闭",null).show();});results.addView(details,LensStyle.space(this));
        JSONArray candidates=response.optJSONArray("candidates");
        if(candidates==null||candidates.length()==0){summary.append("\n本次没有可插入候选。");return;}
        draft=new EditText(this);draft.setId(2104);draft.setSaveEnabled(false);draft.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);draft.setHint("选择候选后可修改");LensStyle.field(draft);draft.setMinLines(3);
        for(int i=0;i<candidates.length();i++){final String text=candidates.optJSONObject(i).optString("text");Button b=new Button(this);LensStyle.button(b,false);b.setGravity(android.view.Gravity.START|android.view.Gravity.CENTER_VERTICAL);b.setText(text);b.setOnClickListener(v->draft.setText(text));results.addView(b,LensStyle.space(this));}
        results.addView(draft,LensStyle.space(this));Button back=new Button(this);LensStyle.button(back,true);back.setText("保留草稿并返回原聊天");back.setOnClickListener(v->{if(session==null||!session.alive()||session.result!=response||SystemClock.elapsedRealtime()>=session.deadline){status.setText("候选已失效，请重新分析");return;}if(draft.getText().toString().trim().isEmpty()){status.setText("请先选择或填写草稿");return;}session.draft=draft.getText().toString();hideKeyboard();returnToChat();});results.addView(back,LensStyle.space(this));
    }
    private void returnToChat(){if(isTaskRoot())finishAndRemoveTask();else finish();}
    private void requestCapture(){
        if(session==null||!session.alive()){status.setText("请从聊天输入框重新打开建议");return;}
        CaptureService.channel(this);
        if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},43);status.setText("允许通知后，再点击截图；通知用于显示停止和预览入口");return;}
        if(!((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).areNotificationsEnabled()){status.setText("请先在系统设置允许观微通知，以便停止截图和打开预览");return;}
        changed();session.clearImage();showImage();
        startActivityForResult(((MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE)).createScreenCaptureIntent(),41);
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(result!=RESULT_OK || data==null){status.setText("已取消，未读取图片");return;}
        if(session==null||!session.alive()){status.setText("输入现场已失效");return;}
        if(request==41){
            session.captureMessage="正在等待单帧截图";
            try{startForegroundService(new Intent(this,CaptureService.class).putExtra("permission",data).putExtra("context",session.context));moveTaskToBack(true);}catch(RuntimeException e){session.captureMessage="截图服务无法启动，请改用选择图片";error(e);}return;
        }
        if(request==42){
            final int token=++work;final AssistSession s=session;final android.net.Uri uri=data.getData();status.setText("正在读取所选图片…");
            NativeClient.IO.execute(()->{try{
                ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=getContentResolver().openInputStream(uri)){byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>15000000)throw new Exception("图片过大，请选择 15 MB 以内的截图");out.write(buffer,0,n);}}
                byte[] bytes=out.toByteArray();BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
                if(options.outWidth<=0 || options.outHeight<=0)throw new Exception("不支持此图片格式");options.inSampleSize=1;while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>1600)options.inSampleSize*=2;
                options.inJustDecodeBounds=false;Bitmap image=BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);if(image==null)throw new Exception("图片无法读取");
                runOnUiThread(()->{if(isDestroyed()||token!=work||!s.alive()){image.recycle();return;}s.clearImage();s.image=image;s.captureMessage="已读取你选择的图片 · 尚未上传";showImage();});
            }catch(Exception e){report(token,e);}});
        }
    }
    private void showImage(){
        if(imagePanel==null)return;imagePanel.removeAllViews();
        if(session==null || !session.alive())return;
        if(!session.captureMessage.isEmpty())status.setText(session.captureMessage);
        if(session.image==null)return;
        ImageView preview=new ImageView(this);preview.setImageBitmap(session.image);preview.setAdjustViewBounds(true);preview.setMaxHeight(600);preview.setContentDescription("待批准的截图预览");imagePanel.addView(preview);
        Button upload=new Button(this);LensStyle.button(upload,true);upload.setText("在本机识别文字");upload.setOnClickListener(v->extractImage());imagePanel.addView(upload,LensStyle.space(this));
        Button discard=new Button(this);LensStyle.button(discard,false);discard.setText("丢弃截图");discard.setOnClickListener(v->{changed();session.clearImage();showImage();status.setText("截图已丢弃");});imagePanel.addView(discard,LensStyle.space(this));
    }
    private void extractImage(){
        if(session==null||!session.alive()||session.image==null){status.setText("请先选择截图");return;}
        changed();final int token=++work;final AssistSession s=session;final int revision=s.revision;
        status.setText("正在本机识别… 图片不提交给分析服务");
        try{LocalChatOcr.recognize(s.image,new LocalChatOcr.Done(){
            public void success(String text){if(isDestroyed()||token!=work||!s.alive()||s.revision!=revision)return;
                if(text.trim().isEmpty()){status.setText("未识别到文字，可能是受保护画面。请改为粘贴聊天片段。");return;}
                transcript.setText(text);status.setText("请结合预览校对：改为“我：”或“对方：”，删除非聊天内容，再批准分析。");}
            public void failure(){if(!isDestroyed()&&token==work)status.setText("本机识别失败，请重试或粘贴聊天片段。");}
        });}catch(RuntimeException e){status.setText("本机识别无法启动，请粘贴聊天片段。");}
    }
    private void feedbackControls(){
        if(AssistSession.feedbackId==null)return;
        final String id=AssistSession.feedbackId;final NativeClient c=AssistSession.feedbackClient;
        label("上次插入 · "+AssistSession.feedbackName+" · 只记录实际后续，不把插入等同于发送或好评",14);
        Spinner outcome=spinner(new String[]{"未知 / 尚未反馈","积极回应","混合回应","消极回应"});
        EditText note=edit("实际观察到的后续（非未知反馈必填）",2105,true);
        EditText insertedDraft=edit("本次插入稿（不代表已发送，可修正）",2106,true);insertedDraft.setText(AssistSession.feedbackDraft==null?"":AssistSession.feedbackDraft);
        button("记录实际反馈",()->{if(!id.equals(AssistSession.feedbackId)||c!=AssistSession.feedbackClient){status.setText("此反馈入口已关闭");return;}String text=note.getText().toString();int index=outcome.getSelectedItemPosition();if(index!=0&&text.trim().isEmpty()){status.setText("请填写实际观察到的后续");return;}
            final String edited=insertedDraft.getText().toString();
            NativeClient.IO.execute(()->{try{c.call("outcome",new JSONObject().put("analysis_id",id).put("status",new String[]{"UNKNOWN","POSITIVE","MIXED","NEGATIVE"}[index]).put("note",text).put("draft",edited));runOnUiThread(()->{if(isDestroyed())return;status.setText("实际反馈已记录");if(id.equals(AssistSession.feedbackId)){AssistSession.feedbackId=null;AssistSession.feedbackDraft=null;insertedDraft.setText("");AssistSession.feedbackClient=null;}});}catch(Exception e){runOnUiThread(()->{if(!isDestroyed())error(e);});}});
        });
    }
    private void hideKeyboard(){View focus=getCurrentFocus();if(focus!=null)((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(focus.getWindowToken(),0);}
    private void report(int token,Exception e){runOnUiThread(()->{if(!isDestroyed()&&token==work)error(e);});}
    private void error(Exception e){status.setText(e.getMessage()==null?"连接失败，请检查网络与服务":e.getMessage());if(e instanceof NativeClient.RequestFailure){String retry=((NativeClient.RequestFailure)e).retryOf;if(!retry.isEmpty())new android.app.AlertDialog.Builder(this).setTitle("确认重新分析").setMessage("原请求可能已经计费。重新分析会占用新的额度，原记录与费用预留将保留。请核对当前人物和片段后决定。").setNegativeButton("取消",null).setPositiveButton("确认再次分析",(d,w)->{acknowledgedRetry=retry;pendingRequest=null;setting=true;approved.setChecked(true);setting=false;analyze();}).show();}}
    private TextView label(String value,int size){TextView t=new TextView(this);t.setText(value);LensStyle.text(t,size,size>=18);body.addView(t,LensStyle.space(this));return t;}
    private EditText edit(String hint,int id,boolean multi){EditText e=new EditText(this);e.setHint(hint);e.setId(id);e.setSaveEnabled(false);e.setInputType(InputType.TYPE_CLASS_TEXT|(multi?InputType.TYPE_TEXT_FLAG_MULTI_LINE:0));if(multi)e.setMinLines(3);LensStyle.field(e);body.addView(e,LensStyle.space(this));return e;}
    private Spinner spinner(String[] names){Spinner s=new Spinner(this);s.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,names));s.setMinimumHeight(LensStyle.dp(this,52));s.setPadding(LensStyle.dp(this,12),0,LensStyle.dp(this,12),0);s.setBackgroundTintList(android.content.res.ColorStateList.valueOf(LensStyle.GREEN));body.addView(s,LensStyle.space(this));return s;}
    private void button(String title,Runnable action){Button b=new Button(this);b.setText(title);LensStyle.button(b,title.equals("分析已批准片段")||title.equals("配对连接"));b.setOnClickListener(v->action.run());body.addView(b,LensStyle.space(this));}
    @Override protected void onDestroy(){work++;if(session!=null&&session.draft.isEmpty()&&AssistSession.current==session)session.invalidate();super.onDestroy();}
}
