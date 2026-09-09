import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import net from 'node:net';
import {hostingSettings,startHosted} from '../hosted.mjs';
import {createCloud} from '../cloud.mjs';

test('managed configuration cannot override isolation or enable synthetic mode',()=>{
  const settings=hostingSettings({LENS_CLOUD_DATA:join(tmpdir(),'lens-synthetic'),LENS_CLOUD_CONFIG_JSON:JSON.stringify({directory:'elsewhere',synthetic:true,apiKey:'injected',provider:'other'})});
  assert.equal(settings.options.directory,join(tmpdir(),'lens-synthetic'));
  assert.equal(settings.options.provider,'bailian');assert.equal(settings.options.apiKey,'');
  assert.equal(settings.options.synthetic,undefined);
  for(const PORT of ['0','65536','10000x','-1'])assert.throws(()=>hostingSettings({LENS_CLOUD_DATA:tmpdir(),PORT}));
  assert.throws(()=>hostingSettings({LENS_CLOUD_DATA:'relative'}));
  assert.equal(hostingSettings({LENS_CLOUD_DATA:tmpdir()}).options.budget.verified,false);
});

test('managed probe exposes no library; missing key blocks paid calls and account survives restart',async t=>{
  const directory=mkdtempSync(join(tmpdir(),'lens-hosting-synthetic-'));
  let app;const open=async()=>{app=createCloud(hostingSettings({LENS_CLOUD_DATA:directory}).options);app.server.listen(0,'127.0.0.1');await once(app.server,'listening');return `http://127.0.0.1:${app.server.address().port}`;};
  let base=await open();t.after(async()=>{await app.close();rmSync(directory,{recursive:true,force:true});});
  const req=async(path,body,token)=>fetch(base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
  assert.deepEqual(await (await req('/api/native/health')).json(),{status:'ok',version:'0.17.3',quality_accepted:false});
  for(const p of ['/','/api/settings','/api/export','/api/native/health?details=true'])assert.equal((await req(p)).status,403);
  assert.equal((await req('/api/native/library/people')).status,401);
  const invite=app.auth.invite();const login=await (await req('/api/native/auth/activate',{code:invite.invite,name:'synthetic',approved:true})).json();
  const person=await (await req('/api/native/library/people',{name:'合成人物',platform:'微信'},login.token)).json();
  await app.close();base=await open();
  assert.equal((await req('/api/native/auth/me',null,login.token)).status,200);
  const people=await (await req('/api/native/library/people',null,login.token)).json();assert.equal(people.people[0].id,person.id);
  assert.equal((await req('/api/native/analyze',{person_id:person.id,pair_id:person.relationship.id,approved:true,text:'合成片段',goal:'自然接话',mode:'model'},login.token)).status,503);
});

test('managed lifecycle listens on assigned port and gracefully releases database lock',async t=>{
  const directory=mkdtempSync(join(tmpdir(),'lens-hosting-lifecycle-'));
  const probe=net.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');
  const port=probe.address().port;await new Promise(r=>probe.close(r));
  let service;t.after(async()=>{await service?.close();rmSync(directory,{recursive:true,force:true});});
  const env={LENS_CLOUD_DATA:directory,PORT:String(port)};
  service=await startHosted(env);
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/native/health`)).status,200);
  await Promise.all([service.close(),service.close()]);
  service=await startHosted(env);
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/native/health`)).status,200);
});
