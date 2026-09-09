import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { openStore, now } from '../store.mjs';
import { observeConversation, strategyLearning, packContext, expressionPlan } from '../context.mjs';
import { localAnalysis } from '../engine.mjs';
import { createApplication } from '../server.mjs';

const person = {name:'合成人物',platform:'视频号',stage:'熟悉中',notes:'仅甲主播的认识经过',boundary:'不问住址'};
const chat = '对方：今天加班很累，想休息。\n我：先休息吧。';
async function start(t, options={}) {
  const app=createApplication({database:':memory:',apiKey:'',...options});
  app.server.listen(0,'127.0.0.1'); await once(app.server,'listening');
  t.after(()=>new Promise(resolve=>app.server.close(resolve)));
  const base=`http://127.0.0.1:${app.server.address().port}`;
  const b=await (await fetch(base+'/api/bootstrap')).json();
  return {...app,request:async(path,method='GET',body)=>{
    const r=await fetch(base+'/api/'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':b.csrf},...(body?{body:JSON.stringify(body)}:{})});
    return {status:r.status,body:await r.json()};
  }};
}

test('legacy database migrates atomically to default pair without copying it to other streamers', () => {
  const file=join(mkdtempSync(join(tmpdir(),'lens-migration-')),'legacy.sqlite');
  const db=new DatabaseSync(file);
  db.exec(`CREATE TABLE people(id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,stage TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',boundary TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
    INSERT INTO people VALUES('0009','旧人物','抖音','熟悉中','旧关系原文','原有边界','2026-09-01');`);
  db.close();let s=openStore(file);
  assert.equal(s.person('0009').notes,'旧关系原文');assert.equal(s.streamers().length,6);
  assert.equal(s.person('0009','0002').relationship,null);assert.equal(s.person('0009','0002').notes,'');
  assert.equal(s.createPerson(person),'0010');s.close();s=openStore(file);
  assert.equal(s.get('PRAGMA user_version').user_version,2);assert.equal(s.all('SELECT * FROM pairs').length,2);
  assert.equal(s.streamers()[0].goal,'');assert.equal(s.streamers()[0].tags,'');s.close();
});

test('pair-scoped memories, hypotheses and feedback do not leak between streamers', async t => {
  const {request,store}=await start(t);
  const p=(await request('people','POST',person)).body;
  assert.equal((await request('analyze','POST',{person_id:p.id,streamer_id:'0002',text:chat,goal:'关心近况',mode:'local'})).status,404);
  await request(`people/${p.id}?streamer_id=0002`,'PUT',{...person,notes:'乙主播独立背景'});
  const claim=(await request('claims','POST',{person_id:p.id,kind:'SELF_DECLARED',content:'甲关系私聊记录',source:'合成样本'})).body;
  assert.equal(store.context(p.id,'0001').claims[0].id,claim.id);
  assert.equal(store.context(p.id,'0002').claims.length,0);
  assert.equal(store.context(p.id,'0002').notes,'乙主播独立背景');
  const a=(await request('analyze','POST',{person_id:p.id,text:chat,goal:'关心近况',mode:'local'})).body;
  await request('outcomes','POST',{analysis_id:a.id,status:'NEGATIVE',note:'合成反应：不希望追问',draft:'合成草稿'});
  await request('beliefs','PUT',{analysis_id:a.id,status:'DISPUTED'});
  assert.equal(store.context(p.id).outcomes.length,1);assert.equal(store.context(p.id,'0002').outcomes.length,0);
  assert.equal(store.context(p.id,'0002').beliefs.length,0);
  assert.equal((await request('analyses?streamer_id=0002')).body.length,0);
  await request(`people/${p.id}`,'DELETE');
  for(const table of ['pairs','analyses','claims','beliefs','outcomes','context_events']) assert.equal(store.get(`SELECT COUNT(*) n FROM ${table}`).n,0);
});

test('feedback/corrections invalidate cache; identical requests still deduplicate; corrections are audited', async t => {
  const {request,store}=await start(t);
  const p=(await request('people','POST',person)).body;
  const payload={person_id:p.id,text:chat,goal:'关心近况',mode:'local'};
  const first=(await request('analyze','POST',payload)).body;
  assert.equal((await request('analyze','POST',payload)).body.id,first.id);
  assert.equal((await request('outcomes','POST',{analysis_id:first.id,status:'NEGATIVE',note:'',draft:''})).status,400);
  await request('outcomes','POST',{analysis_id:first.id,status:'NEGATIVE',note:'明确说不要追问',draft:'要聊聊吗？'});
  const second=(await request('analyze','POST',payload)).body;
  assert.notEqual(first.id,second.id);assert.deepEqual(second.result.context_receipt.outcome_ids,[first.id]);
  assert.equal(second.result.strategy_learning[0].beta,2);
  assert.equal((await request('analyze','POST',payload)).body.id,second.id);
  await request('outcomes','POST',{analysis_id:first.id,status:'UNKNOWN',note:'更正：还没有看到反应',draft:'要聊聊吗？'});
  await request('beliefs','PUT',{analysis_id:first.id,status:'RETIRED'});
  const third=(await request('analyze','POST',payload)).body;
  assert.notEqual(third.id,second.id);assert.equal(third.result.strategy_learning[0].samples,0);
  assert.equal(store.context(p.id).beliefs[0].status,'RETIRED');
  assert.equal(third.belief,null);assert(third.result.belief_suppressed);
  assert.equal(store.all("SELECT * FROM context_events WHERE type='OUTCOME_RECORDED'").length,2);
});

test('disputed/expired claims are excluded and status revisions survive restart', () => {
  const file=join(mkdtempSync(join(tmpdir(),'lens-revisions-')),'test.sqlite');let s=openStore(file);
  const id=s.createPerson(person);const claim={id:randomUUID(),person_id:id,pair_id:s.pair(id).id,kind:'SELF_DECLARED',content:'临时很忙',source:'合成原话',created_at:now()};
  s.addClaim(claim);s.setClaimStatus(claim.id,'EXPIRED');s.close();s=openStore(file);
  assert.equal(s.context(id).claims.length,0);assert.equal(s.context(id).excluded_memories[0].content,'临时很忙');
  const before=s.pair(id).revision;s.setClaimStatus(claim.id,'DISPUTED');assert(s.pair(id).revision>before);
  s.deleteClaim(claim.id);assert.equal(s.context(id).excluded_memories.length,0);s.close();
});

test('objective metrics do not invent speaker identity or timestamps', () => {
  const o=observeConversation('我：要聊聊吗？\n对方：累了。\n无明确标签的下一行');
  assert.equal(o.metrics.unknown_lines,1);assert.equal(o.metrics.self_question_lines,1);
  assert.equal(o.metrics.response_latency_seconds,null);assert.equal(o.metrics.relationship_trend,'UNKNOWN');
  assert(o.messages.every(m=>m.timestamp===null));
});

test('re-analysis is not independent evidence and latest correction wins even within one timestamp', () => {
  const s=openStore(':memory:');const id=s.createPerson(person);const p=s.person(id);
  const r=localAnalysis(chat,p,'关心近况');r.situation='listen';
  const a=s.saveAnalysis(p,chat,'关心近况','one',r,'local',null);
  const b=s.saveAnalysis(p,chat,'关心近况','two',r,'local',null);
  s.saveOutcome(a.id,{status:'POSITIVE',note:'合成正面',draft:'休息吧'});
  s.saveOutcome(b.id,{status:'NEGATIVE',note:'合成负面',draft:'休息吧'});
  s.saveOutcome(a.id,{status:'UNKNOWN',note:'更正为未观察',draft:'休息吧'});
  s.run("UPDATE outcomes SET created_at='2026-09-07T00:00:00.000Z'");
  const context=s.context(id);assert.equal(context.outcomes.length,1);assert.equal(context.outcomes[0].status,'UNKNOWN');
  assert.equal(strategyLearning(context.strategy_observations,'关心近况','listen')[0].samples,0);s.close();
});

test('context budget bounds historical text without discarding registered boundaries', () => {
  const c={...person,id:'0001',name:'合成',streamer:{id:'0001',name:'合成主播',tone:'语'.repeat(1000),phrases:'话'.repeat(2000),emojis:'🙂',boundary:'主播边界'},
    claims:Array.from({length:8},(_,i)=>({id:String(i),kind:'FACT',content:'字'.repeat(1000),source:'源'.repeat(500)})),
    excluded_memories:Array.from({length:8},(_,i)=>({id:'x'+i,kind:'EXPIRED',content:'字'.repeat(1000),source:'源'.repeat(500)})),
    outcomes:Array.from({length:5},()=>({analysis_id:'a',note:'字'.repeat(1000),draft:'字'.repeat(1000)})),
    beliefs:Array.from({length:12},()=>({analysis_id:'b',proposition:'字'.repeat(12000),status:'DISPUTED',alternative:'字'.repeat(12000)}))};
  const pack=packContext(c,chat,'关心近况','listen');assert(pack.receipt.context_characters<=24000);
  assert.equal(pack.context.boundary,person.boundary);assert.equal(pack.context.streamer.boundary,'主播边界');assert(Object.keys(pack.receipt.omitted_for_budget).length);
});

test('Bayesian strategy feedback ignores UNKNOWN/MIXED and mismatched situations', () => {
  const records=['POSITIVE','NEGATIVE','UNKNOWN','MIXED'].map(status=>({goal:'关心近况',situation:'listen',strategy:'先倾听',status}));
  records.push({goal:'关心近况',situation:'boundary',strategy:'先倾听',status:'NEGATIVE'});
  const [s]=strategyLearning(records,'关心近况','listen');assert.equal(s.alpha,2);assert.equal(s.beta,2);assert.equal(s.samples,2);assert.equal(s.calibrated,false);
  assert.equal(expressionPlan(localAnalysis('诱导消费刷礼物',person,'自然接话'),person).recommended,'NO_REPLY');
});

test('GPT request receives bounded persona, corrected memory and feedback; Judge remains separate', async t => {
  const bodies=[];const response=value=>new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(value)}]}]}));
  const fetcher=async(url,init)=>{
    const b=JSON.parse(init.body);bodies.push(b);
    if(b.text.format.name==='independent_judge')return response({verdict:'PASS',reason:'模拟审核通过'});
    const {judge,...result}=localAnalysis(chat,person,'关心近况');return response(result);
  };
  const {request,store}=await start(t,{apiKey:'test-only',fetcher});
  const p=(await request('people','POST',person)).body;
  await request('streamers/0001','PUT',{name:'合成主播甲',tone:'少追问，简短自然',phrases:'你先忙',emojis:'🙂',boundary:'不承诺全天在线',input_layout:'NINE_KEY'});
  const claim=(await request('claims','POST',{person_id:p.id,kind:'SELF_DECLARED',content:'以前喜欢连续追问',source:'合成来源'})).body;
  await request(`claims/${claim.id}`,'PUT',{kind:'DISPUTED'});
  const a=await request('analyze','POST',{person_id:p.id,text:chat,goal:'关心近况',mode:'model'});
  assert.equal(a.status,201);assert.equal(bodies.length,2);
  const context=JSON.parse(bodies[0].input[0].content).person;
  assert.equal(context.streamer.tone,'少追问，简短自然');assert.equal(context.claims.length,0);assert.equal(context.excluded_memories[0].kind,'DISPUTED');
  assert.equal(a.body.result.expression.persona_applied,true);assert.equal(bodies[0].store,false);
  for(let n=0;n<25;n++)store.addClaim({id:randomUUID(),person_id:p.id,pair_id:store.pair(p.id).id,kind:'FACT',content:'字'.repeat(1000),source:'源'.repeat(500),created_at:now()});
  assert.equal(packContext(store.context(p.id),chat,'关心近况','listen').context.claims.length,8);
});

test('in-flight model results are discarded when context changes', async t => {
  let entered;const pending=new Promise(resolve=>entered=resolve);let release;
  const hold=new Promise(resolve=>release=resolve);
  let calls=0;
  const fetcher=async()=>{
    calls++;if(calls===1){entered();await hold;}
    const {judge,...r}=localAnalysis(chat,person,'关心近况');
    const result=calls===1?r:{verdict:'PASS',reason:'模拟终审'};
    return new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(result)}]}]}));
  };
  const {request,store}=await start(t,{apiKey:'test-only',fetcher});
  const p=(await request('people','POST',person)).body;
  const job=request('analyze','POST',{person_id:p.id,text:chat,goal:'关心近况',mode:'model'});
  await pending;
  await request(`people/${p.id}`,'PUT',{...person,boundary:'更新后的边界'});release();
  assert.equal((await job).status,409);assert.equal(store.all('SELECT * FROM analyses').length,0);
});
