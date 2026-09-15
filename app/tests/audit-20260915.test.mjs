import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {openStore} from '../store.mjs';
import {packContext} from '../context.mjs';
import {expireHistory,invalidateDerived} from '../retention.mjs';
import {localAnalysis,modelAnalysis} from '../engine.mjs';
import {createCustomer} from '../customer-create.mjs';

const value={name:'synthetic',platform:'微信',stage:'初识',notes:'',boundary:'',streamer_id:'0001'};
const chat='对方：今天加班很累。',goal='关心近况',situation='listen';
for(const change of ['correct','delete','expire'])test(`aggregate contributor outside direct five is invalidated on ${change}`,()=>{
  const s=openStore(':memory:');try{
    const id=s.createPerson(value,randomUUID()),p=s.context(id),sources=[];
    for(let i=0;i<6;i++){
      const r={...localAnalysis(chat,p,goal),situation};
      const a=s.saveAnalysis(p,`${chat} ${i}`,goal,`input-${i}`,r,'local',null);
      s.saveOutcome(a.id,{status:'POSITIVE',note:'synthetic',draft:'synthetic'});sources.push(a.id);
    }
    const packed=packContext(s.context(id),chat,goal,situation);
    assert.equal(packed.context.strategy_learning[0].positive,6);
    assert.ok(!packed.receipt.outcome_ids.includes(sources[0]));
    assert.ok(packed.receipt.strategy_outcome_ids.includes(sources[0]));
    const a=s.saveAnalysis(p,'derived',goal,'derived',{...localAnalysis(chat,p,goal),context_receipt:packed.receipt},'local',null);
    if(change==='expire'){
      s.run('UPDATE outcomes SET created_at=? WHERE analysis_id=?','2000-01-01T00:00:00.000Z',sources[0]);expireHistory(s,'2020-01-01T00:00:00.000Z');
    }else s.tx(()=>{invalidateDerived(s,[sources[0]]);if(change==='delete')s.run('DELETE FROM analyses WHERE id=?',sources[0]);else s.saveOutcome(sources[0],{status:'NEGATIVE',note:'correction',draft:'synthetic'});});
    assert.equal(s.analysis(a.id).result.route,'SAFE_STOP');
    const next=packContext(s.context(id),chat,goal,situation);
    assert.equal(next.context.strategy_learning[0].positive,5);
    assert.equal(next.context.strategy_learning[0].negative,change==='correct'?1:0);
  }finally{s.close();}
});

test('omitted aggregate groups do not claim dependencies; legacy receipts fail closed within pair',()=>{
  const s=openStore(':memory:');try{
    const id=s.createPerson(value,randomUUID()),other=s.createPerson(value,randomUUID()),p=s.context(id);
    p.strategy_observations=Array.from({length:9},(_,i)=>({analysis_id:`s${i}`,goal,situation,strategy:`strategy${i}`,status:'POSITIVE'}));
    const packed=packContext(p,chat,goal,situation);assert.equal(packed.receipt.strategy_outcome_ids.length,8);assert.ok(!packed.receipt.strategy_outcome_ids.includes('s8'));
    const save=(person,key,receipt)=>s.saveAnalysis(person,key,goal,key,{...localAnalysis(chat,person,goal),context_receipt:receipt},'local',null);
    const a=save(p,'source',{}),old=save(p,'legacy',{version:'pair-context-v1',outcome_ids:[]}),outside=save(s.context(other),'outside',{version:'pair-context-v1'});
    invalidateDerived(s,[a.id]);assert.equal(s.analysis(old.id).result.route,'SAFE_STOP');assert.notEqual(s.analysis(outside.id).result.route,'SAFE_STOP');
  }finally{s.close();}
});

const reply=value=>new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(value)}]}]}));
for(const candidates of [[],[{label:'x',text:' '}],[{label:' ',text:'hello'}],[{label:'x',text:'hello!'},{label:'y',text:'hello。'}],Array.from({length:4},(_,i)=>({label:'x',text:`reply${i}`}))])
test(`invalid reply candidates are refused before judge: ${JSON.stringify(candidates)}`,async()=>{
  const {judge,...r}=localAnalysis(chat,value,goal);r.candidates=candidates;let calls=0;
  await assert.rejects(modelAnalysis(chat,value,goal,{key:'synthetic',model:'synthetic'},async()=>{calls++;return reply(r);}),/候选/);
  assert.equal(calls,1);
});
test('rejected model prose cannot remain in display fields or judge reason',async()=>{
  const {judge,...r}=localAnalysis(chat,value,goal),marker='REJECTED_MODEL_PROSE';
  for(const key of ['summary','strategy','reason','risk','alternative'])r[key]=marker;
  r.reviews.forEach(review=>review.conclusion=marker);r.chief.conclusion=marker;let calls=0;
  const result=await modelAnalysis(chat,value,goal,{key:'synthetic',model:'synthetic'},async()=>reply(++calls===1?r:{verdict:'REJECT',reason:marker}));
  assert.equal(result.route,'SAFE_STOP');assert.equal(result.judge.verdict,'REJECT');assert.ok(!JSON.stringify(result).includes(marker));assert.equal(calls,2);
});

test('customer creation replay is atomic, isolated, payload-bound and cannot resurrect deletion',()=>{
  const s=openStore(':memory:'),other=openStore(':memory:');try{
    const operation=randomUUID();const first=createCustomer(s,value,operation);
    assert.equal(createCustomer(s,value,operation).id,first.id);
    assert.throws(()=>createCustomer(s,{...value,name:'different'},operation),e=>e.status===409);
    assert.notEqual(createCustomer(other,value,operation).id,first.id);
    assert.notEqual(createCustomer(s,value,randomUUID()).id,first.id);
    s.deletePerson(first.id);assert.throws(()=>createCustomer(s,value,operation),e=>e.status===409);
    const rollback=randomUUID();assert.throws(()=>s.tx(()=>{createCustomer(s,value,rollback);throw Error('rollback');}));
    assert.equal(s.get('SELECT value FROM settings WHERE key=?',`customer-create:${rollback}`),undefined);
    assert.equal(s.get('SELECT COUNT(*) n FROM people').n,1);
  }finally{s.close();other.close();}
});
