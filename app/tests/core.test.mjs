import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { openStore } from '../store.mjs';
import { posterior, localAnalysis, modelAnalysis, makeBelief, callModel, ruleJudge } from '../engine.mjs';
import { createApplication } from '../server.mjs';

const p = { id:'0001', name:'测试人物', platform:'视频号', stage:'熟悉中', notes:'', boundary:'不承诺随时在线', claims:[] };
const chat = '对方：今天加班很累，想先休息。';
const modelResult = () => { const { judge, ...r } = localAnalysis(chat, p, '关心近况'); return r; };
const reply = (value) => new Response(JSON.stringify({ status:'completed', output:[{ type:'message', content:[{ type:'output_text', text:JSON.stringify(value) }] }] }), { status:200 });

test('Bayesian updates rise on support and fall on counterevidence', () => {
  assert(posterior(.5,1.8) > .5); assert(posterior(.5,.3) < .5); assert.equal(posterior(.2,1),.2);
  assert.throws(()=>posterior(1,2));
});
test('local mode covers six roles plus chief and independent rule judge; stop suppresses candidates', () => {
  const r=localAnalysis(chat,p,'关心近况');assert.equal(r.reviews.length,6);assert(r.chief);assert.equal(r.judge.verdict,'PASS');assert(makeBelief(r));
  const unsafe=localAnalysis('教我骗对方刷礼物的钱',p,'自然接话');assert.equal(unsafe.route,'SAFE_STOP');assert.equal(unsafe.candidates.length,0);assert.equal(makeBelief(unsafe),null);
});
test('independent rule Judge rejects tampered candidates and invented quotes', () => {
  const r=localAnalysis(chat,p,'关心近况');r.candidates[0].text='你必须给我转账';assert.equal(ruleJudge(r,chat).verdict,'REJECT');
  const q=localAnalysis(chat,p,'关心近况');q.evidence[0].quote='无来源原话';assert.equal(ruleJudge(q,chat).verdict,'REJECT');
});
test('speaker uncertainty and own messages do not become evidence about the other person', () => {
  assert.equal(makeBelief(localAnalysis('我：你先休息吧。',p,'关心近况')),null);
  assert.equal(makeBelief(localAnalysis('今天加班累了。',p,'关心近况')),null);
});
test('SQLite survives restart, deduplicates evidence, deletes related records and never reuses IDs', () => {
  const file=join(mkdtempSync(join(tmpdir(),'lens-store-')),'test.sqlite');let s=openStore(file);
  const id=s.createPerson(p);assert.equal(id,'0001');const r=localAnalysis(chat,p,'关心近况');
  const a=s.saveAnalysis({...p,id},chat,'关心近况','same',r,'local',makeBelief(r));
  const b=s.saveAnalysis({...p,id},chat,'关心近况','same',r,'local',makeBelief(r));assert.equal(a.id,b.id);
  assert.equal(s.get('SELECT COUNT(*) n FROM beliefs').n,1);s.close();s=openStore(file);assert.equal(s.analysis(a.id).result.summary,r.summary);
  const receipt=s.deletePerson(id);assert(receipt.id);assert.equal(s.get('SELECT COUNT(*) n FROM beliefs').n,0);assert.equal(s.get('SELECT COUNT(*) n FROM analyses').n,0);
  assert.equal(s.createPerson(p),'0002');s.close();
});
test('model mode makes a separate Judge request and fails closed on rejection', async () => {
  const requests=[];const fetcher=async(url,init)=>{requests.push(JSON.parse(init.body));return reply(requests.length===1?modelResult():{verdict:'REJECT',reason:'测试终审拒绝'});};
  const r=await modelAnalysis(chat,p,'关心近况',{key:'test-secret',model:'test-model'},fetcher);
  assert.equal(requests.length,2);assert.equal(requests[0].store,false);assert.equal(requests[0].text.format.strict,true);
  assert.equal(r.route,'SAFE_STOP');assert.equal(r.candidates.length,0);assert.equal(r.judge.source,'独立模型调用');
});
test('fabricated model evidence and missing expert roles are rejected before Judge', async () => {
  const fabricated=modelResult();fabricated.evidence[0].quote='原文没有出现的事实';
  await assert.rejects(()=>modelAnalysis(chat,p,'关心近况',{key:'test',model:'test'},async()=>reply(fabricated)),/证据/);
  const missing=modelResult();missing.reviews.pop();
  await assert.rejects(()=>modelAnalysis(chat,p,'关心近况',{key:'test',model:'test'},async()=>reply(missing)),/审核职责/);
});
test('model refusal, incomplete responses, malformed shape and provider errors fail explicitly', async () => {
  const schema={type:'object',properties:{text:{type:'string'}},required:['text'],additionalProperties:false};
  for(const response of [new Response('{}',{status:401}),new Response(JSON.stringify({status:'incomplete'})),reply({unexpected:'x'}),new Response(JSON.stringify({status:'completed',output:[{content:[{type:'refusal'}]}]}))]){
    await assert.rejects(()=>callModel({key:'test',model:'test'},'x',[],schema,'test',async()=>response));
  }
});
test('HTTP workflow: validation, CSRF, isolation, analysis, outcome, export and cascade delete', async t => {
  const {server}=createApplication({database:':memory:',apiKey:''});server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base=`http://127.0.0.1:${server.address().port}`;
  const bootstrap=await (await fetch(base+'/api/bootstrap')).json();
  const request=async(path,method='GET',body,headers={})=>{const r=await fetch(base+'/api/'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':bootstrap.csrf,...headers},...(body!==undefined?{body:JSON.stringify(body)}:{})});return {status:r.status,body:await r.json()};};
  assert.equal((await request('people','POST',p,{'X-CSRF-Token':'bad'})).status,403);
  assert.equal((await request('people','POST',p,{Origin:'http://untrusted.invalid'})).status,403);
  assert.equal((await request('people','POST',{...p,name:''})).status,400);
  assert.equal((await request('people','POST',{...p,platform:'bad'})).status,400);
  const one=(await request('people','POST',p)).body;const two=(await request('people','POST',{...p,name:'另一人'})).body;
  assert.equal(one.id,'0001');assert.equal(two.id,'0002');
  const claim=await request('claims','POST',{person_id:one.id,kind:'SELF_DECLARED',content:'偏好安静',source:'测试自述'});assert.equal(claim.status,201);
  const payload={person_id:one.id,text:chat,goal:'关心近况',mode:'local'};
  const a=await request('analyze','POST',payload);assert.equal(a.status,201);assert.equal(a.body.result.reviews.length,6);
  const b=await request('analyze','POST',payload);assert.equal(b.body.id,a.body.id);assert.equal(b.body.cached,true);
  assert.equal((await request('analyze','POST',{...payload,mode:'model'})).status,400);
  assert.equal((await request('outcomes','POST',{analysis_id:a.body.id,status:'UNKNOWN',note:'尚未回复',draft:'先休息吧'})).status,200);
  const exportData=(await request('export')).body;assert.equal(exportData.analyses[0].outcome.status,'UNKNOWN');assert(!JSON.stringify(exportData).includes('key'));
  assert.equal((await request(`people/${two.id}`)).body.claims.length,0);
  assert.equal((await request('beliefs','PUT',{analysis_id:a.body.id,status:'DISPUTED'})).status,200);
  const receipt=await request(`people/${one.id}`,'DELETE');assert.equal(receipt.status,200);assert(receipt.body.id);
  assert.equal((await request(`analyses/${a.body.id}`)).status,404);
  assert.equal((await request('export')).body.analyses.length,0);
  const third=(await request('people','POST',p)).body;assert.equal(third.id,'0003');
  const page=await fetch(base+'/');assert.equal(page.status,200);assert(page.headers.get('content-security-policy').includes("frame-ancestors 'none'"));
});
