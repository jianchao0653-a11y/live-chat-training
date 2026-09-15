import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {once} from 'node:events';
import {createCloud} from '../cloud.mjs';
import {roles} from '../engine.mjs';
import {backupCloud,restoreCloud} from '../cloud-maintenance.mjs';
import {openStore} from '../store.mjs';
import {openCloudAuth} from '../cloud-auth.mjs';

// HTTP is loopback-only. Every provider call terminates in this fake implementation.
const syntheticBudget={verified:true,dailyCount:20,dailyMicros:1000000000,monthlyMicros:1000000000,
  inputPerMillion:1000000,outputPerMillion:1000000,currency:'SYNTHETIC'};
const material=(extra={})=>({id:'M1',kind:'PROFILE_TEXT',text:'资料自述：喜欢散步。',
  source:'用户核对的合成资料截图转录',observed_at:'2026-09-10',...extra});
const payload=(person,type='PROFILE',extra={})=>({request_id:randomUUID(),person_id:person.id,pair_id:person.relationship.id,
  task_type:type,mode:'model',approved:true,context:'synthetic-editor',host:'com.synthetic.chat',
  ...(type==='PROFILE'?{materials:[material()]}:{}),...extra});
function modelResult(input) {
  const evidence=input.materials.map((m,index)=>({id:`E${index+1}`,source_id:m.id,quote:m.text,kind:'SELF_DECLARED'}));
  const refs=evidence.map(e=>e.id);
  return {summary:'只记录本次资料中的自述，保留未知。',strategy:'先确认轻松话题',reason:'不能从自述推出其他特征。',
    risk:'资料仍需人工核对。',route:'FAST',alternative:'可以先问候并给对方拒绝空间。',evidence,
    reviews:roles.map(role=>({role,conclusion:'仅使用提供的资料，缺失信息保持未知。',evidence_refs:[...refs]})),
    chief:{goal:input.goal,conclusion:'先核对来源再使用。',conflict:'未知信息不作推断。'},
    candidates:input.task_type==='PROFILE'?[]:[{label:'问候',text:'你好呀，今天过得怎么样？'},{label:'征询话题',text:'有空的话，想聊点什么？'}],
    profile:{observations:evidence.length?[
      {id:'O1',kind:'SELF_DECLARED',content:'材料自述喜欢散步。',evidence_refs:['E1'],uncertainty:'转录内容未独立核实。'},
      {id:'OI',kind:'INFERRED',content:'散步可能是可询问的话题。',evidence_refs:['E1'],uncertainty:'不知道对方现在是否仍感兴趣。'}
    ]:[],unknowns:['当前是否愿意聊天尚不清楚。']}};
}
async function fixture(t,{onCall,mutateResult,judge='PASS'}={}) {
  const parent=resolve(tmpdir()),prefix=join(parent,'lens-customer-task-http-synthetic-'),directory=mkdtempSync(prefix);
  let app,base,instant=Date.UTC(2026,8,10,12);const calls=[];
  const fetcher=async(url,init)=>{
    assert.equal(url,'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions');
    const request=JSON.parse(init.body),input=JSON.parse(request.messages.at(-1).content),isJudge=request.max_tokens===512;
    const call={request,input,isJudge};calls.push(call);await onCall?.(call,calls.length);
    const result=isJudge?{verdict:judge,reason:'合成终审结果。'}:modelResult(input);
    if(!isJudge)mutateResult?.(result,input);
    return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},
      choices:[{finish_reason:'stop',message:{content:JSON.stringify(result)}}]}));
  };
  const start=async()=>{app=createCloud({directory,apiKey:'synthetic-key-never-sent',model:'qwen-plus',fetcher,clock:()=>instant,budget:syntheticBudget});
    app.server.listen(0,'127.0.0.1');await once(app.server,'listening');base=`http://127.0.0.1:${app.server.address().port}/api/native/`;};
  const stop=async()=>{if(app){const closing=app;app=null;await closing.close();}};
  t.after(async()=>{await stop();if(dirname(directory)!==parent||!directory.startsWith(prefix))throw new Error('Unsafe synthetic cleanup');rmSync(directory,{recursive:true,force:true});});
  await start();
  const request=async(path,body,token)=>{const response=await fetch(base+path,{method:body===undefined?'GET':'POST',
    headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    return {status:response.status,body:await response.json()};};
  const activate=async()=>{const invite=app.auth.invite();const result=await request('auth/activate',{code:invite.invite,name:'synthetic',approved:true});assert.equal(result.status,200);return result.body;};
  const person=async(identity,extra={})=>{const result=await request('library/people',{name:'合成人物',platform:'微信',...extra},identity.token);assert.equal(result.status,200);return result.body;};
  return {directory,calls,request,activate,person,start,stop,advance:milliseconds=>{instant+=milliseconds;},get app(){return app;}};
}
const tasks=f=>f.app.auth.all('SELECT * FROM tasks ORDER BY created,rowid');
const postTask=(f,identity,body)=>f.request('analyze',body,identity.token);

test('PROFILE preserves submitted provenance and needs explicit review before selected observations become memories',async t=>{
  const f=await fixture(t),identity=await f.activate(),other=await f.activate(),person=await f.person(identity);
  const materials=['PROFILE_TEXT','MOMENTS_TEXT','CHAT_TEXT','USER_NOTE'].map((kind,i)=>material({id:`M${i+1}`,kind,source:`合成${kind}转录` }));
  const input=payload(person,'PROFILE',{materials,text:'想找一个可询问的话题'}),result=await postTask(f,identity,input);
  assert.equal(result.status,200);assert.equal(result.body.task_type,'PROFILE');assert.equal(result.body.ticket_id,null);
  assert.deepEqual(result.body.candidates,[]);assert.deepEqual(result.body.materials,materials);
  assert.equal(result.body.budget.portrait_used_today,1);assert.equal(f.calls.length,2);assert.equal(tasks(f)[0].task_type,'PROFILE');
  assert.deepEqual(f.calls[0].input.materials,materials);assert.equal(f.calls[0].input.intent,input.text);assert(!Object.hasOwn(f.calls[0].input,'chat'));
  const store=f.app.application(identity.account_id).store,analysisPath=`library/analyses/${result.body.analysis_id}`;
  assert.equal(store.person(person.id).claims.length,0);
  const detail=await f.request(analysisPath,undefined,identity.token);assert.equal(detail.status,200);assert.equal(detail.body.stale,false);
  assert.deepEqual(detail.body.analysis.result.materials,materials);
  assert.equal((await f.request(analysisPath,undefined,other.token)).status,404);
  assert.equal((await f.request(analysisPath+'/memories',{confirmed:true,observation_ids:['O1']},other.token)).status,404);
  for(const body of [{confirmed:false,observation_ids:['O1']},{confirmed:true,observation_ids:[]},{confirmed:true,observation_ids:['missing']},{confirmed:true,observation_ids:['O1','O1']}])
    assert.equal((await f.request(analysisPath+'/memories',body,identity.token)).status,400);
  assert.equal(store.person(person.id).claims.length,0);
  const saved=await f.request(analysisPath+'/memories',{confirmed:true,observation_ids:['O1','OI']},identity.token);
  assert.equal(saved.status,200);assert.equal(saved.body.memories.length,2);
  const fact=saved.body.memories.find(m=>m.kind==='SELF_DECLARED'),inference=saved.body.memories.find(m=>m.kind==='INFERRED');
  assert.equal(fact.review_state,'CONFIRMED');assert.equal(inference.review_state,'PENDING');assert.match(fact.source,/合成PROFILE_TEXT转录/);assert.match(fact.source,/2026-09-10/);
  assert(store.context(person.id).claims.some(m=>m.id===fact.id));assert(!store.context(person.id).claims.some(m=>m.id===inference.id));
  assert.equal((await f.request(analysisPath+'/memories',{confirmed:true,observation_ids:['O1']},identity.token)).status,409);
  const history=await f.request(`library/people/${person.id}/history`,undefined,identity.token);
  assert.equal(history.body.history[0].task_type,'PROFILE');assert.equal(tasks(f).length,1);assert.equal(f.calls.length,2);
});

test('empty-source OPENING returns editable consumable suggestions and cache reuse survives an editor and server restart',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),input=payload(person,'OPENING');
  const result=await postTask(f,identity,input);assert.equal(result.status,200);assert.equal(result.body.task_type,'OPENING');
  assert.equal(result.body.profile.observations.length,0);assert.deepEqual(result.body.evidence,[]);assert(result.body.ticket_id);
  assert.equal(result.body.budget.portrait_used_today,0);assert.equal(tasks(f)[0].task_type,'OPENING');assert.equal(f.calls.length,2);
  const consumePath=`tickets/${result.body.ticket_id}/consume`,draft='这是本人修改后选择插入的合成草稿。';
  assert.equal((await f.request(consumePath,{...input,draft,confirmed:false},identity.token)).status,400);
  const consumed=await f.request(consumePath,{...input,draft,confirmed:true},identity.token);assert.equal(consumed.status,200);assert.equal(consumed.body.draft,draft);
  assert.equal((await f.request(consumePath,{...input,draft,confirmed:true},identity.token)).status,410);
  await f.stop();await f.start();
  const next={...input,request_id:randomUUID(),context:'synthetic-new-editor'},cached=await postTask(f,identity,next);
  assert.equal(cached.status,200);assert.equal(cached.body.analysis_id,result.body.analysis_id);assert(cached.body.ticket_id);
  assert.equal(f.calls.length,2);assert.equal(tasks(f).length,1);assert.equal(cached.body.budget.used_today,1);
  assert.equal((await f.request(`tickets/${cached.body.ticket_id}/consume`,{...next,draft,confirmed:true},identity.token)).status,200);
  const reused=await postTask(f,identity,payload(person,'PROFILE',{request_id:input.request_id}));assert.equal(reused.status,409);assert.equal(tasks(f).length,1);
});

test('invalid source data, wrong customer segment and cross-account requests are rejected before reserving or calling a model',async t=>{
  const f=await fixture(t),identity=await f.activate(),other=await f.activate(),person=await f.person(identity);
  const maintain=await f.person(identity,{segment:'MAINTAIN'}),unclassified=await f.person(identity,{segment:'UNCLASSIFIED'});
  const invalid=[{materials:[]},{materials:[material({kind:'IMAGE'})]},{materials:[material({kind:'URL'})]},
    {materials:[material({text:'data:image/png;base64,AAAA'})]},{materials:[material({image:'unapproved-image'})]},
    {materials:[material({source:''})]},{materials:[material({observed_at:'2026-02-30'})]},
    {task_type:'UNKNOWN'},{mode:'local'},{goal:'新客破冰'},{approved:false},{context:''},{host:'invalid/host'}];
  for(const extra of invalid)assert.equal((await postTask(f,identity,payload(person,'PROFILE',extra))).status,400,JSON.stringify(extra));
  assert.equal((await postTask(f,other,payload(person))).status,404);
  for(const customer of [maintain,unclassified])assert.equal((await postTask(f,identity,payload(customer))).status,409);
  assert.equal(tasks(f).length,0);assert.equal(f.calls.length,0);assert.equal(f.app.budget.summary(identity.account_id).portrait_used_today,0);
});

test('ten profiles per account and twenty tasks across accounts both apply while cached work stays reusable',async t=>{
  const f=await fixture(t),a=await f.activate(),b=await f.activate(),first=await f.person(a),second=await f.person(a),third=await f.person(b);
  const original=payload(first,'PROFILE',{text:'合成画像意图0'});assert.equal((await postTask(f,a,original)).status,200);
  for(let i=1;i<10;i++)assert.equal((await postTask(f,a,payload(i%2?second:first,'PROFILE',{text:`合成画像意图${i}`}))).status,200);
  const eleventh=await postTask(f,a,payload(first,'PROFILE',{text:'第十一次不同画像'}));assert.equal(eleventh.status,429);assert.match(eleventh.body.error,/新客画像/);
  assert.equal((await postTask(f,b,payload(third))).status,200);
  f.advance(61000); // Keep this a daily-quota test, independent of the existing minute limiter.
  for(let i=0;i<9;i++)assert.equal((await postTask(f,a,payload(first,'OPENING',{text:`合成开场意图${i}`}))).status,200);
  assert.equal(tasks(f).length,20);assert.equal(f.calls.length,40);
  const blocked=await postTask(f,b,payload(third,'OPENING',{text:'项目已达二十次'}));assert.equal(blocked.status,429);assert.match(blocked.body.error,/项目今天/);
  const cached=await postTask(f,a,{...original,request_id:randomUUID(),context:'quota-cached-editor'});
  assert.equal(cached.status,200);assert.equal(f.calls.length,40);assert.equal(tasks(f).length,20);assert.equal(cached.body.budget.portrait_used_today,10);
  f.advance(86400000);
  const reset=await postTask(f,a,payload(first,'PROFILE',{text:'新一天的新画像'}));assert.equal(reset.status,200);
  assert.equal(reset.body.budget.portrait_used_today,1);assert.equal(reset.body.budget.used_today,1);assert.equal(reset.body.budget.day_timezone,'UTC');
  assert.equal(reset.body.budget.reset_at,Date.UTC(2026,8,12));
});

test('in-flight task and global concurrency rejection leave no extra reservations or classification changes',async t=>{
  let release,firstEntered,secondEntered,entered=0;
  const hold=new Promise(resolve=>release=resolve),firstWait=new Promise(resolve=>firstEntered=resolve),secondWait=new Promise(resolve=>secondEntered=resolve);
  const f=await fixture(t,{onCall:async call=>{if(!call.isJudge){if(++entered===1)firstEntered();if(entered===2)secondEntered();await hold;}}});
  const a=await f.activate(),b=await f.activate(),c=await f.activate(),p=await f.person(a),q=await f.person(b),r=await f.person(c);
  const first=postTask(f,a,payload(p));await firstWait;let second;
  try{
    assert.equal((await postTask(f,a,payload(p,'OPENING'))).status,409);
    assert.equal((await f.request(`library/people/${p.id}/segment`,{segment:'MAINTAIN'},a.token)).status,409);
    second=postTask(f,b,payload(q));await secondWait;
    assert.equal((await postTask(f,c,payload(r))).status,429);assert.equal(tasks(f).length,2);
    assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,0);
  }finally{release();}
  assert.equal((await first).status,200);assert.equal((await second).status,200);assert.equal(f.calls.length,4);
});

test('classification preserves profile history and evidence while invalidating old conclusions and opening tickets',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity);
  const profile=await postTask(f,identity,payload(person));assert.equal(profile.status,200);
  const input=payload(person,'OPENING'),opening=await postTask(f,identity,input);assert.equal(opening.status,200);
  const store=f.app.application(identity.account_id).store,before=store.analysis(profile.body.analysis_id);
  assert.equal((await f.request(`library/people/${person.id}/segment`,{segment:'MAINTAIN'},identity.token)).status,200);
  const analysisPath=`library/analyses/${profile.body.analysis_id}`,detail=await f.request(analysisPath,undefined,identity.token);
  assert.equal(detail.status,200);assert.equal(detail.body.stale,true);assert.deepEqual(detail.body.analysis,before);
  assert.equal((await f.request(analysisPath+'/memories',{confirmed:true,observation_ids:['O1']},identity.token)).status,409);
  assert.equal((await f.request(`tickets/${opening.body.ticket_id}/consume`,{...input,confirmed:true,draft:'旧开场草稿'},identity.token)).status,409);
  assert.equal(store.person(person.id).claims.length,0);assert.equal(store.all('SELECT * FROM analyses').length,2);
  assert.equal((await postTask(f,identity,payload(person))).status,409);assert.equal(f.calls.length,4);
});

test('new customer information makes older profile conclusions stale before they can be saved as memories',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),profile=await postTask(f,identity,payload(person));
  assert.equal(profile.status,200);
  const memory=await f.request(`library/people/${person.id}/memories`,{kind:'SELF_DECLARED',content:'现在不喜欢散步。',source:'新近合成自述'},identity.token);
  assert.equal(memory.status,200);
  const path=`library/analyses/${profile.body.analysis_id}`,detail=await f.request(path,undefined,identity.token);
  assert.equal(detail.status,200);assert.equal(detail.body.stale,true);
  assert.equal((await f.request(path+'/memories',{confirmed:true,observation_ids:['O1']},identity.token)).status,409);
  assert.equal(f.app.application(identity.account_id).store.person(person.id).claims.length,1);assert.equal(f.calls.length,2);
});

test('independent rejection produces no insert ticket and no profile observation that can become a memory',async t=>{
  const f=await fixture(t,{judge:'REJECT'}),identity=await f.activate(),person=await f.person(identity);
  for(const type of ['PROFILE','OPENING']){
    const result=await postTask(f,identity,payload(person,type));assert.equal(result.status,200);assert.equal(result.body.route,'SAFE_STOP');
    assert.equal(result.body.ticket_id,null);assert.deepEqual(result.body.candidates,[]);assert.deepEqual(result.body.profile.observations,[]);
    assert.equal((await f.request(`library/analyses/${result.body.analysis_id}/memories`,{confirmed:true,observation_ids:['O1']},identity.token)).status,400);
  }
  assert.equal(f.app.application(identity.account_id).store.person(person.id).claims.length,0);assert.equal(f.calls.length,4);
});

test('rejected model evidence retains charged work and requires acknowledged retry without silently calling again',async t=>{
  let malformed=true;
  const f=await fixture(t,{mutateResult:result=>{if(malformed)result.evidence[0].quote='这句话不在任何合成资料中';}}),identity=await f.activate(),person=await f.person(identity),input=payload(person);
  const failed=await postTask(f,identity,input);assert.equal(failed.status,500);assert.equal(f.calls.length,1);
  const original={...tasks(f)[0]};assert.equal(original.state,'FAILED');assert.equal(original.calls,1);assert(original.charged>0);
  assert.equal(f.app.application(identity.account_id).store.all('SELECT * FROM analyses').length,0);
  const uncertain=await postTask(f,identity,{...input,request_id:randomUUID()});assert.equal(uncertain.status,409);assert.equal(uncertain.body.retry_of,input.request_id);assert.equal(f.calls.length,1);
  malformed=false;
  const retried=await postTask(f,identity,{...input,request_id:randomUUID(),retry_of:input.request_id,acknowledge_possible_charge:true});
  assert.equal(retried.status,200);assert.equal(f.calls.length,3);assert.equal(tasks(f).length,2);assert.deepEqual({...tasks(f)[0]},original);
  assert.equal(retried.body.budget.portrait_used_today,2);
});

test('deleting reviewed source records invalidates dependent suggestions and an older backup cannot revive deleted content',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),key=Buffer.alloc(32,13);
  const profile=await postTask(f,identity,payload(person));assert.equal(profile.status,200);
  const original=await postTask(f,identity,payload(person,'OPENING',{text:'第一次合成开场'}));assert.equal(original.status,200);
  assert.equal((await f.request('outcome',{analysis_id:original.body.analysis_id,status:'POSITIVE',note:'对方合成反馈愿意聊聊',draft:'本人采用的合成开场'},identity.token)).status,200);
  const nextInput=payload(person,'OPENING',{text:'使用已确认反馈的后续合成开场'}),dependent=await postTask(f,identity,nextInput);assert.equal(dependent.status,200);
  assert(f.app.application(identity.account_id).store.analysis(dependent.body.analysis_id).result.context_receipt.outcome_ids.includes(original.body.analysis_id));
  await f.stop();const snapshot=await backupCloud(f.directory,join(f.directory,'synthetic-backups'),key);await f.start();
  for(const result of [profile,original]){
    const path=`library/analyses/${result.body.analysis_id}`;
    assert.equal((await f.request(path+'/delete',{},identity.token)).status,200);
    assert.equal((await f.request(path,undefined,identity.token)).status,404);
  }
  const invalidated=await f.request(`library/analyses/${dependent.body.analysis_id}`,undefined,identity.token);
  assert.equal(invalidated.status,200);assert.equal(invalidated.body.analysis.result.route,'SAFE_STOP');assert.deepEqual(invalidated.body.analysis.result.candidates,[]);
  assert.equal(invalidated.body.analysis.result.task_type,'OPENING');
  const ledgerBefore=tasks(f).map(row=>({...row}));
  await f.stop();const target=join(f.directory,'synthetic-restored'),restored=await restoreCloud(snapshot.destination,key,f.directory,target);
  assert.equal(restored.budgetRolledBack,false);assert.equal(restored.discarded_person_snapshots,1);
  const store=openStore(join(target,'accounts',identity.account_id+'.sqlite')),auth=openCloudAuth(join(target,'identity.sqlite'));
  try{
    assert.equal(store.person(person.id),null);assert.equal(store.all('SELECT * FROM analyses').length,0);assert.equal(store.all('SELECT * FROM outcomes').length,0);
    assert.deepEqual(auth.all('SELECT * FROM tasks ORDER BY created,rowid').map(row=>({...row})),ledgerBefore);
    assert.throws(()=>auth.authorize(identity.token),error=>error.status===401);
  }finally{store.close();auth.close();}
});
