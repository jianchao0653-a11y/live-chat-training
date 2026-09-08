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
  await assert.rejects(()=>backupCloud(directory,join(root,'backups'),key));await app.close();
  const snap=await backupCloud(directory,join(root,'backups'),key);
  assert(!readFileSync(snap.destination).includes(Buffer.from('synthetic secret')));
  app=createCloud({directory,budget});
  app.auth.run('INSERT INTO deletions(account,person,entire,created) VALUES(?,?,1,?)',account.account_id,id,Date.now());
  app.application(account.account_id).store.deletePerson(id);
  const taskId=randomUUID();app.budget.reserve(taskId,account.account_id,'synthetic-fingerprint');
  await app.close();
  await assert.rejects(()=>restoreCloud(snap.destination,Buffer.alloc(32,8),directory,join(root,'wrong-key')));
  const target=join(root,'restored'),result=await restoreCloud(snap.destination,key,directory,target);
  assert.equal(result.discarded_person_snapshots,1);assert.equal(result.budgetRolledBack,false);
  const restored=openStore(join(target,'accounts',account.account_id+'.sqlite'));
  try{assert.equal(restored.person(id),null);}finally{restored.close();}
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
