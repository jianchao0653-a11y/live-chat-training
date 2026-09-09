package com.conversationlens.ime;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.view.WindowManager;
import android.text.InputType;
import android.widget.*;
import org.json.*;

public final class LibraryActivity extends Activity {
    private LinearLayout body;private TextView status;private NativeClient client;private int generation;private boolean loggingIn;
    private interface Done{void run(JSONObject value)throws Exception;}
    @Override public void onCreate(Bundle state){super.onCreate(state);LensStyle.window(this);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);try{client=NativeClient.load(this);}catch(Exception ignored){}if(client==null)login();else home();}
    @Override protected void onDestroy(){generation++;super.onDestroy();}
    private void page(String title){generation++;ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(LensStyle.dp(this,20),LensStyle.dp(this,24),LensStyle.dp(this,20),LensStyle.dp(this,24));body.setBackgroundColor(LensStyle.BG);scroll.addView(body);
        scroll.setOnApplyWindowInsetsListener((v,i)->{int top=i.getSystemWindowInsetTop(),bottom=i.getSystemWindowInsetBottom();if(android.os.Build.VERSION.SDK_INT>=30){top=i.getInsets(android.view.WindowInsets.Type.systemBars()).top;bottom=i.getInsets(android.view.WindowInsets.Type.systemBars()|android.view.WindowInsets.Type.ime()).bottom;}v.setPadding(0,top,0,bottom);return i;});
        label(title,24);status=label("",14);status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);setContentView(scroll);}
    private TextView label(String text,int size){TextView v=new TextView(this);v.setText(text);LensStyle.text(v,size,size>20);body.addView(v,LensStyle.space(this));return v;}
    private EditText field(String hint,String value,int id,boolean multi){EditText v=new EditText(this);v.setId(id);v.setSaveEnabled(false);v.setHint(hint);v.setText(value);v.setInputType(InputType.TYPE_CLASS_TEXT|(multi?InputType.TYPE_TEXT_FLAG_MULTI_LINE:0));if(multi)v.setMinLines(2);LensStyle.field(v);body.addView(v,LensStyle.space(this));return v;}
    private void button(String title,Runnable action){Button b=new Button(this);b.setText(title);LensStyle.button(b,title.startsWith("保存")||title.startsWith("登录"));b.setOnClickListener(v->action.run());body.addView(b,LensStyle.space(this));}
    private Spinner options(String[] values,String current){Spinner s=new Spinner(this);s.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,values));for(int i=0;i<values.length;i++)if(values[i].equals(current))s.setSelection(i);body.addView(s,LensStyle.space(this));return s;}
    private String value(EditText v){return v.getText().toString().trim();}
    private void call(String path,JSONObject input,Done done){final int ticket=++generation;final NativeClient c=client;status.setText("正在处理…");NativeClient.IO.execute(()->{try{JSONObject result=c.call(path,input);runOnUiThread(()->{if(isDestroyed()||ticket!=generation)return;try{done.run(result);}catch(Exception e){status.setText("资料格式不正确，请重试。");}});}catch(Exception e){runOnUiThread(()->{if(!isDestroyed()&&ticket==generation)status.setText(e.getMessage());});}});}
    private void confirm(String message,Runnable action){new AlertDialog.Builder(this).setTitle("请确认").setMessage(message).setNegativeButton("取消",null).setPositiveButton("确认",(d,w)->action.run()).show();}
    private void login(){page("登录观微");label("输入收到的一次性邀请码。试用期资料保存在项目提供者的电脑后端，网络请求经过 ngrok HTTPS 网关，网关可处理请求内容。只有你批准的聊天片段与必要人物背景会提交给阿里云百炼分析。建议由你编辑、确认并发送。",15);
        label("分析与反馈通常保留最多30天；人物与确认记忆保留至删除。备份最多保留7天。可在人物资料中修改和删除；卸载应用不会删除云端资料。",14);
        EditText code=field("一次性邀请码","",3101,false);code.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox consent=new CheckBox(this);consent.setText("我已了解并同意上述数据处理方式");body.addView(consent,LensStyle.space(this));
        button("登录并开始",()->{if(loggingIn)return;if(!consent.isChecked()){status.setText("请先阅读并同意数据处理说明。");return;}try{
            final NativeClient pending=new NativeClient(CloudSettings.endpoint(this),"");final JSONObject input=new JSONObject().put("code",value(code)).put("name",android.os.Build.MODEL).put("approved",true);
            loggingIn=true;status.setText("正在登录…");NativeClient.IO.execute(()->{try{JSONObject r=pending.call("auth/activate",input);NativeClient connected=new NativeClient(pending.endpoint,r.getString("token"));
                // Persist a successful activation even if rotation destroyed this Activity.
                NativeClient.save(getApplicationContext(),connected);
                runOnUiThread(()->{loggingIn=false;if(isDestroyed())return;client=connected;code.setText("");home();});
            }catch(Exception e){runOnUiThread(()->{loggingIn=false;if(!isDestroyed())status.setText(e.getMessage());});}});
        }catch(Exception e){status.setText("服务配置不可用，请联系安装包提供者。");}});
    }
    private void profile(){page("我的主播档案");button("返回",()->home());call("library/streamer",null,r->{JSONObject p=r.getJSONObject("profile");
        label("当前账号："+r.getString("account_id")+"\n这些资料由你填写，只用于当前账号的回复建议。",14);
        EditText name=field("主播称呼",p.optString("name"),3120,false),tone=field("表达风格",p.optString("tone"),3121,true),phrases=field("常用表达",p.optString("phrases"),3122,true),emojis=field("常用表情",p.optString("emojis"),3123,false),goal=field("沟通目标",p.optString("goal"),3124,true),boundary=field("个人边界",p.optString("boundary"),3125,true),tags=field("本人填写的标签",p.optString("tags"),3126,true);
        button("保存主播档案",()->{try{JSONObject b=new JSONObject().put("name",value(name)).put("tone",value(tone)).put("phrases",value(phrases)).put("emojis",value(emojis)).put("goal",value(goal)).put("boundary",value(boundary)).put("tags",value(tags)).put("input_layout",p.optString("input_layout","SYSTEM"));confirm("保存会清除当前账号的旧分析与反馈，让新建议使用更新后的档案。",()->call("library/streamer",b,v->{AssistSession.clear();home();}));}catch(Exception e){status.setText("请检查填写内容。");}});
    });}
    private void home(){page("人物与聊天记忆");button("我的主播档案",()->profile());button("新建人物",()->editPerson(null));button("返回",()->finish());
        button("退出登录",()->confirm("退出将撤销当前设备登录并清除本机草稿。再次登录需要新的邀请码。",()->call("auth/logout",new JSONObject(),r->{NativeClient.forget(this);AssistSession.clear();AssistSession.feedbackId=null;AssistSession.feedbackName=null;AssistSession.feedbackClient=null;client=null;login();})));
        button("本机登录失效时清除",()->confirm("仅清除本机凭据，不删除云端人物。",()->{NativeClient.forget(this);AssistSession.clear();AssistSession.feedbackId=null;AssistSession.feedbackName=null;AssistSession.feedbackClient=null;client=null;login();}));
        call("library/people",null,r->{status.setText("选择人物查看、修改或删除资料。离线时仍可正常打字。");JSONArray list=r.getJSONArray("people");if(list.length()==0)label("还没有人物，先填写一个昵称即可开始。",16);for(int i=0;i<list.length();i++){JSONObject p=list.getJSONObject(i);button(p.getString("name")+" · "+p.getString("platform"),()->detail(p.optString("id")));}});
    }
    private void editPerson(JSONObject p){page(p==null?"新建人物":"修改人物");EditText name=field("昵称",p==null?"":p.optString("name"),3102,false);label("聊天平台",13);Spinner platform=options(new String[]{"微信","抖音","快手","视频号"},p==null?"微信":p.optString("platform"));label("关系阶段",13);Spinner stage=options(new String[]{"初识","熟悉中","稳定联系","需要修复"},p==null?"初识":p.optString("stage"));
        EditText notes=field("关系背景（选填）",p==null?"":p.optString("notes"),3103,true),boundary=field("沟通边界（选填）",p==null?"":p.optString("boundary"),3104,true);
        button("保存人物",()->{try{JSONObject b=new JSONObject().put("name",value(name)).put("platform",platform.getSelectedItem()).put("stage",stage.getSelectedItem()).put("notes",value(notes)).put("boundary",value(boundary));Runnable save=()->call(p==null?"library/people":"library/people/"+p.optString("id")+"/save",b,r->detail(r.getString("id")));if(p==null)save.run();else confirm("修改资料会清除该人物旧分析与反馈，避免旧资料继续影响建议。",save);}catch(Exception e){status.setText("请检查填写内容。");}});button("取消",()->home());
    }
    private void detail(String id){page("人物资料");button("返回人物列表",()->home());call("library/people/"+id,null,p->{status.setText(p.getString("name")+" · "+p.getString("platform"));label("关系："+p.optString("stage")+"\n背景："+p.optString("notes")+"\n边界："+p.optString("boundary"),15);
        button("修改人物与关系",()->editPerson(p));button("添加记忆或标记",()->memory(id,null));button("查看分析与反馈",()->history(id));
        button("删除人物及关联资料",()->confirm("删除此人物、关系、记忆、分析及反馈。生效后无法在 App 中撤销；备份最多7天清除，恢复时也不得重新出现。",()->call("library/people/"+id+"/delete",new JSONObject(),r->home())));
        JSONArray claims=p.getJSONArray("claims");label("记忆与标记",20);for(int i=0;i<claims.length();i++){JSONObject c=claims.getJSONObject(i);label(("TAG".equals(c.optString("category"))?"标记 · ":"记忆 · ")+kindLabel(c.optString("kind"))+" · "+("PENDING".equals(c.optString("review_state"))?"待确认":"已确认状态")+"\n"+c.optString("content")+"\n来源："+c.optString("source")+"\n"+c.optString("created_at"),15);button("修改或删除",()->memory(id,c));if("PENDING".equals(c.optString("review_state")))button("确认此条推测",()->confirm("确认后可作为推测参考，仍保留推测来源；旧分析与反馈会清除。",()->{try{call("library/memories/"+c.optString("id")+"/confirm",new JSONObject().put("confirmed",true),v->{AssistSession.clear();detail(id);});}catch(Exception e){status.setText("确认失败。");}}));}
    });}
    private static final String[] KINDS={"SELF_DECLARED","FACT","INFERRED","DISPUTED","EXPIRED"};
    private static final String[] KIND_LABELS={"本人填写","聊天中确认的事实","推测（需要确认）","有争议（不用于建议）","已失效（不用于建议）"};
    private static String kindLabel(String code){for(int i=0;i<KINDS.length;i++)if(KINDS[i].equals(code))return KIND_LABELS[i];return code;}
    private void memory(String id,JSONObject c){page(c==null?"添加记忆或标记":"修改记忆或标记");label("请选择真实来源。推测保存后需单独确认，修改推测后也需要重新确认。",14);Spinner kind=options(KIND_LABELS,kindLabel(c==null?"SELF_DECLARED":c.optString("kind"))),category=options(new String[]{"聊天记忆","客户标记"},c!=null&&"TAG".equals(c.optString("category"))?"客户标记":"聊天记忆");EditText content=field("内容",c==null?"":c.optString("content"),3105,true),source=field("来源，例如：哪次聊天中的原话",c==null?"":c.optString("source"),3106,true);
        button("保存记忆或标记",()->{try{JSONObject b=new JSONObject().put("content",value(content)).put("source",value(source)).put("kind",KINDS[kind.getSelectedItemPosition()]).put("category",category.getSelectedItemPosition()==1?"TAG":"MEMORY");Runnable save=()->call(c==null?"library/people/"+id+"/memories":"library/memories/"+c.optString("id")+"/save",b,r->{AssistSession.clear();detail(id);});if(c==null)save.run();else confirm("修改会清除该人物旧分析与反馈，避免旧内容再次被引用。",save);}catch(Exception e){status.setText("请填写内容和来源。");}});
        if(c!=null)button("删除记忆",()->confirm("删除此记忆并清除该人物旧分析与反馈。",()->call("library/memories/"+c.optString("id")+"/delete",new JSONObject(),r->detail(id))));button("取消",()->detail(id));
    }
    private void history(String id){page("分析与反馈");button("返回人物资料",()->detail(id));call("library/people/"+id+"/history",null,r->{status.setText("最近30条记录；插入不代表已经发送或得到积极回应。");JSONArray list=r.getJSONArray("history");for(int i=0;i<list.length();i++){JSONObject a=list.getJSONObject(i);label(a.optString("created_at")+" · "+a.optString("goal")+"\n"+a.optString("summary"),15);JSONObject o=a.optJSONObject("outcome");if(o!=null)label("反馈："+o.optString("status")+"\n"+o.optString("note"),14);button("填写或修改反馈",()->feedback(id,a));button("删除反馈及旧分析",()->confirm("清除此人物的旧分析与反馈，避免已删除的反馈残留在其他分析中。",()->call("library/feedback/"+a.optString("id")+"/delete",new JSONObject(),v->detail(id))));}});}
    private void feedback(String personId,JSONObject a){page("实际反馈");JSONObject old=a.optJSONObject("outcome");String[] codes={"UNKNOWN","POSITIVE","MIXED","NEGATIVE"};Spinner outcome=options(new String[]{"未知／尚无回应","积极回应","混合回应","消极回应"},"");if(old!=null)for(int i=0;i<codes.length;i++)if(codes[i].equals(old.optString("status")))outcome.setSelection(i);EditText note=field("实际观察",old==null?"":old.optString("note"),3107,true);
        button("保存反馈",()->{try{JSONObject b=new JSONObject().put("status",codes[outcome.getSelectedItemPosition()]).put("note",value(note)).put("draft",old==null?"":old.optString("draft"));confirm("保存后清除该人物其他旧分析与反馈，避免旧反馈继续影响建议。",()->call("library/feedback/"+a.optString("id")+"/save",b,r->history(personId)));}catch(Exception e){status.setText("请检查反馈。");}});button("取消",()->history(personId));
    }
}
