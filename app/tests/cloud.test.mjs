import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {randomUUID} from 'node:crypto';
import {createCloud} from '../cloud.mjs';
import {localAnalysis} from '../engine.mjs';
import {providerEndpoint} from '../provider.mjs';
import {backupCloud,restoreCloud} from '../cloud-maintenance.mjs';
import {openCloudAuth} from '../cloud-auth.mjs';
import {openStore} from '../store.mjs';
import {createBudget} from '../cloud-budget.mjs';
test('project daily count cannot be multiplied by creating another account',()=>{
  const auth=openCloudAuth(':memory:');
  try {
    const a=auth.invite().account_id,b=auth.invite().account_id;
    const limits=createBudget(auth,{verified:true,dailyCount:1,dailyMicros:10000000,monthlyMicros:100000000,inputPerMillion:800000,outputPerMillion:2000000});
    const id=randomUUID();limits.reserve(id,a,'first');limits.finish(id,null);
    assert.throws(()=>limits.reserve(randomUUID(),b,'second'),e=>e.status===429);
    assert.equal(limits.reserve(id,a,'first').existing.id,id);
  }finally{auth.close();}
});
const chat='对方：今天加班很累，想安静休息。';
const budget={verified:true,inputPerMillion:1000000,outputPerMillion:1000000,dailyMicros:10000000,monthlyMicros:100000000,dailyCount:20,currency:'SYNTHETIC'};
async function fixture(t,options={}) {
  const directory=mkdtempSync(join(tmpdir(),'lens-cloud-synthetic-'));let now=Date.now(),calls=0;
  const fetcher=async(_url,opts)=>{
    calls++;const input=JSON.parse(opts.body);const judge=input.max_tokens===512;
    const {judge:_,...result}=localAnalysis(chat,{name:'合成',claims:[]},'关心近况');
    return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},choices:[{finish_reason:'stop',message:{content:JSON.stringify(judge?{verdict:'PASS',reason:'合成终审'}:result)}}]}));
  };
  const create=()=>createCloud({directory,apiKey:'synthetic-key',clock:()=>now,fetcher,budget,...options});
  let app=create(),base;
  const listen=async()=>{app.server.listen(0,'127.0.0.1');await once(app.server,'listening');base=`http://127.0.0.1:${app.server.address().port}`;};await listen();
  t.after(async()=>{await app.close();rmSync(directory,{recursive:true,force:true});});
  const request=async(path,body,token,method)=>{const r=await fetch(base+path,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});return {status:r.status,body:await r.json()};};
  const activate=async()=>{const i=app.auth.invite();return (await request('/api/native/auth/activate',{code:i.invite,name:'synthetic',approved:true})).body;};
  const person=async d=>(await request('/api/native/library/people',{name:'合成人物',platform:'微信'},d.token)).body;
  return {get app(){return app;},request,activate,person,get calls(){return calls;},advance:n=>now+=n,restart:async()=>{await app.close();app=create();await listen();}};
}
const payload=p=>({request_id:randomUUID(),person_id:p.id,pair_id:p.relationship.id,context:'editor-one',host:'com.synthetic.chat',approved:true,text:chat,goal:'关心近况',mode:'model'});

test('busy rejection creates no task, preserves the first editor, and retries successfully after completion',async t=>{
 let release,enter,calls=0;const hold=new Promise(r=>release=r),ready=new Promise(r=>enter=r);
 const f=await fixture(t,{fetcher:async(_u,o)=>{calls++;if(calls===1){enter();await hold;}const input=JSON.parse(o.body),{judge,...r}=localAnalysis(chat,{name:'synthetic',claims:[]},'关心近况');return new Response(JSON.stringify({model:'synthetic',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},choices:[{finish_reason:'stop',message:{content:JSON.stringify(input.max_tokens===512?{verdict:'PASS',reason:'synthetic'}:r)}}]}));}});
 const account=await f.activate(),p=await f.person(account),one=payload(p),two={...payload(p),text:chat+' 第二段',context:'another-editor'};
 const pending=f.request('/api/native/analyze',one,account.token);await ready;
 try{
 assert.equal((await f.request('/api/native/analyze',two,account.token)).status,409);
 assert.equal(f.app.auth.get('SELECT id FROM tasks WHERE id=?',two.request_id),undefined);
 release();assert.equal((await pending).status,200);
 assert.equal((await f.request('/api/native/analyze',{...two,request_id:randomUUID()},account.token)).status,200);assert.equal(calls,4);
 }finally{release();await pending;}
});

test('identical feedback is inert and a correction preserves independent recent histories',async t=>{
 const f=await fixture(t),account=await f.activate(),p=await f.person(account),s=f.app.application(account.account_id).store;
 const a=(await f.request('/api/native/analyze',payload(p),account.token)).body;
 const b=(await f.request('/api/native/analyze',{...payload(p),text:chat+' 独立记录'},account.token)).body;
 const send=value=>f.request('/api/native/outcome',value,account.token);
 const feedback={analysis_id:a.analysis_id,status:'POSITIVE',note:'synthetic note',draft:'synthetic draft'};
 await send(feedback);const revision=s.person(p.id).relationship.revision,events=s.get('SELECT COUNT(*) n FROM context_events').n,journal=f.app.auth.get('SELECT COUNT(*) n FROM deletions').n;
 assert.equal((await send(feedback)).body.unchanged,true);assert.equal(s.person(p.id).relationship.revision,revision);assert.equal(s.get('SELECT COUNT(*) n FROM context_events').n,events);assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM deletions').n,journal);
 assert.equal((await send({...feedback,note:'corrected synthetic note'})).status,200);assert.ok(s.analysis(b.analysis_id));assert.equal(s.analysis(a.analysis_id).outcome.note,'corrected synthetic note');
});

test('uncertain paid request exposes a correlated confirmation flow; acknowledgement retains old ledger',async t=>{
 let calls=0;
 const f=await fixture(t,{fetcher:async(_u,o)=>{if(++calls===1)throw Error('synthetic provider transport failure');const input=JSON.parse(o.body),{judge,...r}=localAnalysis(chat,{name:'synthetic',claims:[]},'关心近况');return new Response(JSON.stringify({model:'synthetic',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},choices:[{finish_reason:'stop',message:{content:JSON.stringify(input.max_tokens===512?{verdict:'PASS',reason:'synthetic'}:r)}}]}));}});
 const a=await f.activate(),p=await f.person(a),body=payload(p),send=b=>f.request('/api/native/analyze',b,a.token);
 const first=await send(body);assert.equal(first.status,500);assert.ok(first.body.request_id);
 const retry=await send({...body,request_id:randomUUID()});assert.equal(retry.status,409);assert.equal(retry.body.retry_of,body.request_id);assert.equal(calls,1);
 const original=f.app.auth.get('SELECT * FROM tasks WHERE id=?',body.request_id);
 assert.equal((await send({...body,request_id:randomUUID(),retry_of:retry.body.retry_of,acknowledge_possible_charge:true})).status,200);
 assert.deepEqual(f.app.auth.get('SELECT * FROM tasks WHERE id=?',body.request_id),original);assert.equal(calls,3);
});

test('streamer profile persists per account and changes invalidate existing suggestions',async t=>{
  const f=await fixture(t),a=await f.activate(),b=await f.activate(),p=await f.person(a);
  const prior=(await f.request('/api/native/analyze',payload(p),a.token)).body;
  const value={name:'合成主播甲',tone:'简短自然',goal:'关心近况',boundary:'不承诺见面',tags:'本人填写：直率'};
  assert.equal((await f.request('/api/native/library/streamer',value,a.token)).status,200);
  assert.equal(f.app.application(a.account_id).store.analysis(prior.analysis_id),null);
  assert.equal((await f.request(`/api/native/tickets/${prior.ticket_id}/consume`,{...payload(p),confirmed:true,draft:'旧建议'},a.token)).status,409);
  await f.restart();
  const mine=(await f.request('/api/native/library/streamer',null,a.token)).body;
  assert.equal(mine.account_id,a.account_id);assert.equal(mine.profile.goal,value.goal);
  assert.notEqual((await f.request('/api/native/library/streamer',null,b.token)).body.profile.name,value.name);
});

test('inferred tags require explicit confirmation and retain their origin after confirmation',async t=>{
  const f=await fixture(t),a=await f.activate(),b=await f.activate(),p=await f.person(a);
  const c=(await f.request(`/api/native/library/people/${p.id}/memories`,{content:'可能偏好简短回复',source:'合成推测',kind:'INFERRED',category:'TAG'},a.token)).body;
  const s=f.app.application(a.account_id).store;
  assert.equal(c.review_state,'PENDING');assert.equal(s.context(p.id).claims.length,0);
  const route=`/api/native/library/memories/${c.id}/confirm`;
  assert.equal((await f.request(route,{confirmed:true},b.token)).status,404);
  assert.equal((await f.request(route,{},a.token)).status,400);
  assert.equal((await f.request(route,{confirmed:true},a.token)).status,200);
  assert.equal(s.context(p.id).claims[0].kind,'INFERRED');
  await f.request(`/api/native/library/memories/${c.id}/save`,{content:'修订推测',source:'新的合成线索'},a.token);
  assert.equal(s.context(p.id).claims.length,0);
  await f.request(`/api/native/library/memories/${c.id}/delete`,{},a.token);
  assert.equal(s.person(p.id).claims.length,0);
});

test('cloud activation is single use, persistent and revocable; private routes require identity',async t=>{
  const f=await fixture(t);const invite=f.app.auth.invite();
  const body={code:invite.invite,name:'test',approved:true};
  const a=(await f.request('/api/native/auth/activate',body)).body;
  assert.equal((await f.request('/api/native/auth/activate',body)).status,401);
  assert.equal((await f.request('/api/native/library/people')).status,401);
  for(const path of ['/','/api/export','/api/settings','/api/bootstrap'])assert.equal((await f.request(path)).status,403);
  await f.restart();assert.equal((await f.request('/api/native/auth/me',null,a.token)).status,200);
  assert.equal((await f.request('/api/native/auth/logout',{},a.token)).status,200);
  assert.equal((await f.request('/api/native/roster',null,a.token)).status,401);
});

test('cloud accounts cannot read, mutate, analyze, delete or feed back another account resources',async t=>{
  const f=await fixture(t),a=await f.activate(),b=await f.activate(),p=await f.person(a);
  assert(p.relationship);
  const mem=(await f.request(`/api/native/library/people/${p.id}/memories`,{content:'周末不聊工作',source:'用户确认'},a.token)).body;
  for(const [path,body] of [[`people/${p.id}`,null],[`people/${p.id}/save`,{}],[`people/${p.id}/delete`,{}],[`people/${p.id}/history`,null],[`people/${p.id}/memories`,{content:'x',source:'x'}],[`memories/${mem.id}/delete`,{}],[`memories/${mem.id}/save`,{content:'x',source:'x'}]])assert.equal((await f.request('/api/native/library/'+path,body,b.token)).status,404,path);
  assert.equal((await f.request('/api/native/analyze',payload(p),b.token)).status,404);
  const result=(await f.request('/api/native/analyze',payload(p),a.token)).body;
  assert(result.analysis_id);
  assert.equal((await f.request(`/api/native/library/feedback/${result.analysis_id}/save`,{status:'UNKNOWN'},b.token)).status,404);
  assert.equal((await f.request('/api/native/outcome',{analysis_id:result.analysis_id,status:'UNKNOWN'},b.token)).status,404);
  assert.equal((await f.request(`/api/native/tickets/${result.ticket_id}/consume`,{...payload(p),confirmed:true,draft:'x'},b.token)).status,410);
  assert.equal(f.calls,2);
});

test('cloud retries reuse completed paid work; ledger survives restart and budgets stop provider calls',async t=>{
  const f=await fixture(t,{budget:{...budget,dailyCount:1}}),a=await f.activate(),p=await f.person(a),body=payload(p);
  const result=await f.request('/api/native/analyze',body,a.token);assert.equal(result.status,200);
  assert.equal((await f.request('/api/native/analyze',body,a.token)).status,200);assert.equal(f.calls,2);
  await f.restart();assert.equal((await f.request('/api/native/analyze',body,a.token)).status,200);assert.equal(f.calls,2);
  assert.equal((await f.request('/api/native/analyze',{...body,request_id:randomUUID(),text:chat+'谢谢'},a.token)).status,429);assert.equal(f.calls,2);
});

test('cloud memory edits erase derived copies, invalidate old tickets and preserve account isolation',async t=>{
  const f=await fixture(t),a=await f.activate(),p=await f.person(a);
  const m=(await f.request(`/api/native/library/people/${p.id}/memories`,{content:'旧合成记忆',source:'确认'},a.token)).body;
  const r=(await f.request('/api/native/analyze',payload(p),a.token)).body;
  assert.equal((await f.request(`/api/native/library/memories/${m.id}/save`,{content:'修正记忆',source:'新确认'},a.token)).status,200);
  assert.equal(f.app.application(a.account_id).store.analysis(r.analysis_id),null);
  assert.equal((await f.request(`/api/native/tickets/${r.ticket_id}/consume`,{...payload(p),confirmed:true,draft:'旧草稿'},a.token)).status,409);
  assert.equal((await f.request(`/api/native/library/people/${p.id}`,null,a.token)).body.claims[0].content,'修正记忆');
  await f.request(`/api/native/library/people/${p.id}/delete`,{},a.token);
  assert.equal((await f.request(`/api/native/library/people/${p.id}`,null,a.token)).status,404);
  assert.equal(f.app.auth.all('SELECT * FROM deletions').length,2);
});

test('cloud failure retains reservation and cannot silently repeat; expiry blocks login',async t=>{
  let calls=0;const f=await fixture(t,{fetcher:async()=>{calls++;throw new Error('synthetic timeout');}}),a=await f.activate(),p=await f.person(a),body=payload(p);
  assert.equal((await f.request('/api/native/analyze',body,a.token)).status,500);
  assert.equal((await f.request('/api/native/analyze',body,a.token)).status,409);assert.equal(calls,1);
  assert.equal((await f.request('/api/native/analyze',{...body,request_id:randomUUID(),context:'after-rotation'},a.token)).status,409);assert.equal(calls,1);
  const task=f.app.auth.get('SELECT * FROM tasks WHERE id=?',body.request_id);assert(task.reserved>0);
  await f.restart();assert.equal((await f.request('/api/native/analyze',body,a.token)).status,409);
  f.advance(31*86400000);assert.equal((await f.request('/api/native/auth/me',null,a.token)).status,401);
});

test('cloud backup is encrypted, requires service stop, and restore replays later deletions without restoring spend or sessions',async t=>{
  const root=mkdtempSync(join(tmpdir(),'lens-backup-synthetic-')),directory=join(root,'live'),key=Buffer.alloc(32,7);
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  let app=createCloud({directory,budget});const account=app.auth.invite(),d=app.auth.activate(account.invite,'test'),s=app.application(account.account_id).store;
  const id=s.createPerson({name:'synthetic secret',platform:'微信',stage:'初识'},randomUUID());
  s.updateStreamer('0001',{name:'synthetic old profile',tone:'old tone',phrases:'',emojis:'',boundary:'old boundary',goal:'old goal',tags:'old tags',input_layout:'NINE'});
  await assert.rejects(()=>backupCloud(directory,join(root,'backups'),key));await app.close();
  const snap=await backupCloud(directory,join(root,'backups'),key);
  assert(!readFileSync(snap.destination).includes(Buffer.from('synthetic secret')));
  app=createCloud({directory,budget});
  app.auth.run('INSERT INTO deletions(account,person,entire,created) VALUES(?,?,1,?)',account.account_id,id,Date.now());
  app.application(account.account_id).store.deletePerson(id);
  app.auth.run('INSERT INTO deletions(account,person,entire,created) VALUES(?,?,0,?)',account.account_id,'@streamer',Date.now());
  const taskId=randomUUID();app.budget.reserve(taskId,account.account_id,'synthetic-fingerprint');
  await app.close();
  await assert.rejects(()=>restoreCloud(snap.destination,Buffer.alloc(32,8),directory,join(root,'wrong-key')));
  const target=join(root,'restored'),result=await restoreCloud(snap.destination,key,directory,target);
  assert.equal(result.discarded_person_snapshots,1);assert.equal(result.budgetRolledBack,false);
  const restored=openStore(join(target,'accounts',account.account_id+'.sqlite'));
  try{assert.equal(restored.person(id),null);const profile=restored.streamers()[0];assert.equal(profile.name,'待设置主播');assert.equal(profile.goal,'');assert.equal(profile.tags,'');assert.equal(profile.input_layout,'SYSTEM');assert.equal(restored.all('SELECT * FROM context_events').length,0);}finally{restored.close();}
  const auth=openCloudAuth(join(target,'identity.sqlite'));
  try{assert(auth.get('SELECT reserved FROM tasks WHERE id=?',taskId).reserved>0);assert.throws(()=>auth.authorize(d.token),e=>e.status===401);}finally{auth.close();}
  await assert.rejects(()=>restoreCloud(snap.destination,key,directory,target));
});

test('cloud logout during provider work prevents result persistence and ticket creation',async t=>{
  let release,entered;const ready=new Promise(r=>entered=r),hold=new Promise(r=>release=r);let calls=0;
  const f=await fixture(t,{fetcher:async(_u,o)=>{calls++;if(calls===1){entered();await hold;}const {judge,...r}=localAnalysis(chat,{name:'合成',claims:[]},'关心近况');return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2},choices:[{finish_reason:'stop',message:{content:JSON.stringify(calls===1?r:{verdict:'PASS',reason:'test'})}}]}));}});
  const a=await f.activate(),p=await f.person(a);const pending=f.request('/api/native/analyze',payload(p),a.token);await ready;
  await f.request('/api/native/auth/logout',{},a.token);release();assert.equal((await pending).status,401);
  assert.equal(f.app.application(a.account_id).store.get('SELECT COUNT(*) n FROM analyses').n,0);
});

test('missing monetary configuration blocks all paid provider calls',async t=>{
  const f=await fixture(t,{budget:{}}),a=await f.activate(),p=await f.person(a);
  assert.equal((await f.request('/api/native/analyze',payload(p),a.token)).status,503);assert.equal(f.calls,0);
});

test('Bailian endpoint rejects arbitrary hosts, credentials, redirects and extra paths',()=>{
  assert(providerEndpoint().startsWith('https://dashscope.aliyuncs.com/'));
  for(const u of ['http://dashscope.aliyuncs.com/compatible-mode/v1','https://evil.test/compatible-mode/v1','https://dashscope.aliyuncs.com.evil.test/compatible-mode/v1','https://user:secret@dashscope.aliyuncs.com/compatible-mode/v1','https://dashscope.aliyuncs.com/compatible-mode/v1?x=1'])assert.throws(()=>providerEndpoint(u));
});
