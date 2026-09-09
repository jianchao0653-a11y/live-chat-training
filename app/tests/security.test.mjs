import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createApplication} from '../server.mjs';
import {validateSchema,localAnalysis} from '../engine.mjs';

async function fixture(t, options={}) {
  const app=createApplication({database:':memory:',apiKey:'synthetic',accessToken:'',...options});
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  t.after(()=>new Promise(r=>app.server.close(r)));
  const base=`http://127.0.0.1:${app.server.address().port}`;
  const boot=await(await fetch(base+'/api/bootstrap')).json();
  const request=async(path,body,headers={})=>{
    const r=await fetch(base+'/api/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.csrf,...headers},...(body?{body:JSON.stringify(body)}:{})});
    return {status:r.status,body:await r.json()};
  };
  return {request};
}
const reply=()=>new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({text:'合成转写',warning:'合成测试'})}]}]}));
const picture={image:'data:image/png;base64,c3ludGhldGlj'};

test('web and native OCR share admission; excess work never reaches provider and failure releases slots',async t=>{
  const holds=[];let calls=0;
  const {request}=await fixture(t,{fetcher:()=>{calls++;return calls>2?Promise.resolve(reply()):new Promise((resolve,reject)=>holds.push({resolve,reject}));}});
  const code=(await request('devices/pairing',{streamer_id:'0001'})).body.code;
  const d=(await request('native/pair',{code,name:'合成设备'})).body;
  const p1=request('extract',picture);
  const until=async n=>{for(let i=0;i<200&&calls<n;i++)await new Promise(r=>setTimeout(r,5));assert.equal(calls,n);};
  await until(1);
  const p2=request('native/extract',{...picture,approved:true,context:'synthetic',host:'com.synthetic'},{Authorization:`Bearer ${d.token}`});
  await until(2);
  try {assert.equal((await request('extract',picture)).status,429);assert.equal(calls,2);}
  finally {holds[0].reject(new Error('synthetic failure'));holds[1].resolve(reply());}
  assert.equal((await p1).status,500);assert.equal((await p2).status,200);
  const p3=request('extract',picture);assert.equal((await p3).status,200);assert.equal(calls,3);
});

test('rolling model admission persists after failure and reopens only after window expiry',async t=>{
  let now=1000,calls=0;
  const {request}=await fixture(t,{clock:()=>now,fetcher:async()=>{calls++;throw new Error('synthetic provider failure');}});
  for(let i=0;i<30;i++)assert.equal((await request('extract',picture)).status,500);
  assert.equal((await request('extract',picture)).status,429);assert.equal(calls,30);
  now+=59999;assert.equal((await request('extract',picture)).status,429);
  now++;assert.equal((await request('extract',picture)).status,500);assert.equal(calls,31);
});

test('analysis reserves its independent judge, cached and local results need no paid budget',async t=>{
  let calls=0;
  const chat='对方：今天加班很累，想安静休息。';
  const {judge,...analysis}=localAnalysis(chat,{name:'合成关系',claims:[]},'关心近况');
  const {request}=await fixture(t,{clock:()=>1000,fetcher:async(url,init)=>{
    calls++;const name=JSON.parse(init.body).text.format.name;
    const result=name==='independent_judge'?{verdict:'PASS',reason:'合成终审'}:name==='chat_transcript'?{text:'合成',warning:''}:analysis;
    return new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(result)}]}]}));
  }});
  const p=(await request('people',{name:'合成关系',platform:'视频号',stage:'熟悉中'})).body;
  const input={person_id:p.id,text:chat,goal:'关心近况',mode:'model'};
  assert.equal((await request('analyze',input)).status,201);assert.equal(calls,2);
  for(let i=0;i<28;i++)assert.equal((await request('extract',picture)).status,200);
  assert.equal((await request('extract',picture)).status,429);
  assert.equal((await request('analyze',input)).body.cached,true);
  assert.equal((await request('analyze',{...input,text:chat+'合成补充'})).status,429);
  assert.equal((await request('analyze',{...input,mode:'local'})).status,201);
  assert.equal(calls,30);
});

test('forwarded requests cannot use loopback owner APIs',async t=>{
  const {request}=await fixture(t);
  for(const headers of [{'X-Forwarded-For':'203.0.113.1'},{Forwarded:'for=203.0.113.1'},{'X-Real-IP':'203.0.113.1'}]) {
    assert.equal((await request('bootstrap',null,headers)).status,403);
    assert.equal((await request('devices/pairing',{streamer_id:'0001'},headers)).status,403);
    assert.equal((await request('export',null,headers)).status,403);
  }
  assert.equal((await request('bootstrap')).status,200);
  assert.equal((await request('native/roster',null,{'X-Forwarded-For':'203.0.113.1'})).status,401);
});

test('schema rejects unknown keys inherited from Object.prototype',()=>{
  const schema={type:'object',properties:{text:{type:'string'}},required:['text'],additionalProperties:false};
  for(const key of ['toString','constructor','__proto__']) {
    assert.throws(()=>validateSchema(JSON.parse(`{"text":"synthetic","${key}":"unexpected"}`),schema),/未知字段/);
  }
});
