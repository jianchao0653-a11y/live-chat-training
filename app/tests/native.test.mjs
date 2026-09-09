import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createApplication} from '../server.mjs';
import {createNativeBridge} from '../native.mjs';
import {openStore} from '../store.mjs';
import {localAnalysis} from '../engine.mjs';

async function fixture(t,options={}) {
  const app=createApplication({database:':memory:',apiKey:'',...options});app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  t.after(()=>new Promise(r=>app.server.close(r)));
  const base=`http://127.0.0.1:${app.server.address().port}`;
  const boot=await(await fetch(base+'/api/bootstrap')).json();
  const request=async(path,method='GET',body,token)=>{
    const r=await fetch(base+'/api/'+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{'X-CSRF-Token':boot.csrf})},...(body?{body:JSON.stringify(body)}:{})});return {status:r.status,body:await r.json()};
  };
  const p=(await request('people','POST',{name:'合成关系',platform:'视频号',stage:'熟悉中',streamer_id:'0001'})).body;
  const pair=async(sid='0001')=>{
    const code=(await request('devices/pairing','POST',{streamer_id:sid})).body.code;
    return (await request('native/pair','POST',{code,name:'合成手机'})).body;
  };
  return {...app,request,p,pair};
}
const payload=p=>({person_id:p.id,pair_id:p.relationship.id,context:'editor-one',host:'com.synthetic.chat',approved:true,text:'对方：今天加班很累，想安静休息。',goal:'关心近况',mode:'local'});

test('native pairing is single-use; devices are scoped and require a token',async t=>{
  const {request,p,pair}=await fixture(t);
  assert.equal((await request('native/roster')).status,401);
  const d=await pair();const roster=(await request('native/roster','GET',null,d.token)).body;
  assert.equal(roster.people.length,1);assert(!JSON.stringify(roster).includes(d.token));
  assert.equal((await request('native/pair','POST',{code:'123456',name:'x'})).status,410);
  const other=await pair('0002');assert.equal((await request('native/roster','GET',null,other.token)).body.people.length,0);
  assert.equal((await request('native/analyze','POST',payload(p),other.token)).status,404);
  assert.equal((await request('native/analyze','POST',{...payload(p),approved:false},d.token)).status,400);
});

test('native candidates enforce host, relationship revision, cancellation and single-use insertion',async t=>{
  const {request,p,pair}=await fixture(t);const d=await pair();
  const analyze=()=>request('native/analyze','POST',payload(p),d.token);
  let a=(await analyze()).body;assert.equal(a.candidates.length,3);
  const consume=a=>({context:a.context,host:a.host,person_id:p.id,pair_id:p.relationship.id,confirmed:true,draft:a.candidates[0].text});
  const url=a=>`native/tickets/${a.ticket_id}/consume`;
  assert.equal((await request(url(a),'POST',{...consume(a),host:'com.wrong'},d.token)).status,409);
  assert.equal((await request(url(a),'POST',consume(a),d.token)).status,200);
  assert.equal((await request(url(a),'POST',consume(a),d.token)).status,410);
  a=(await analyze()).body;
  await request('claims','POST',{person_id:p.id,kind:'FACT',content:'明确的新边界',source:'合成确认'});
  assert.equal((await request(url(a),'POST',consume(a),d.token)).status,409);
  a=(await analyze()).body;await request('native/cancel','POST',{context:a.context},d.token);
  assert.equal((await request(url(a),'POST',consume(a),d.token)).status,410);
  assert.equal((await request(`devices/${d.id}`,'DELETE')).status,200);assert.equal((await analyze()).status,401);
});

test('revoking device during model work prevents saving result',async t=>{
  let release,entered;const begun=new Promise(r=>entered=r);const hold=new Promise(r=>release=r);let calls=0;
  const fetcher=async()=>{calls++;if(calls===1){entered();await hold;}
    const {judge,...result}=localAnalysis('对方：今天加班很累，想安静休息。',{name:'合成关系',claims:[]},'关心近况');
    return new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(calls===1?result:{verdict:'PASS',reason:'合成终审'})}]}]}));};
  const {request,p,pair,store}=await fixture(t,{apiKey:'synthetic-key',fetcher});const d=await pair();
  const pending=request('native/analyze','POST',{...payload(p),mode:'model'},d.token);await begun;
  assert.equal((await request(`devices/${d.id}`,'DELETE')).status,200);release();assert.equal((await pending).status,401);
  assert.equal(store.get('SELECT COUNT(*) n FROM analyses').n,0);
});

test('pair code guessing limit and device expiry use the server clock',async()=>{
  let now=100;const store=openStore(':memory:');
  try {
    const native=createNativeBridge({store,clock:()=>now,config:()=>({}),analyze:()=>{},extract:()=>{},revision:()=>''});
    const req={method:'POST',headers:{}};
    const info=await native.manage('/api/devices/pairing','POST',{streamer_id:'0001'});
    for(let i=0;i<5;i++)await assert.rejects(()=>native.handle(req,'/api/native/pair',{code:info.code==='111111'?'222222':'111111',name:'x'}),e=>e.status===401);
    await assert.rejects(()=>native.handle(req,'/api/native/pair',{code:info.code,name:'x'}),e=>e.status===410);
    const good=await native.manage('/api/devices/pairing','POST',{streamer_id:'0001'});
    const d=await native.handle(req,'/api/native/pair',{code:good.code,name:'x'});now+=8*3600000;
    await assert.rejects(()=>native.handle({method:'GET',headers:{authorization:`Bearer ${d.token}`}},'/api/native/roster',{}),e=>e.status===401);
  }finally{store.close();}
});

test('feedback is pair scoped and invalidates outstanding candidates',async t=>{
  const {request,p,pair}=await fixture(t);const d=await pair(),other=await pair('0002');
  const a=(await request('native/analyze','POST',payload(p),d.token)).body;
  const feedback={analysis_id:a.analysis_id,status:'POSITIVE',note:'合成后续：对方明确表示感谢'};
  assert.equal((await request('native/outcome','POST',feedback,other.token)).status,404);
  assert.equal((await request('native/outcome','POST',{...feedback,note:''},d.token)).status,400);
  assert.equal((await request('native/outcome','POST',feedback,d.token)).status,200);
  assert.equal((await request(`native/tickets/${a.ticket_id}/consume`,'POST',{...payload(p),confirmed:true,draft:'合成草稿'},d.token)).status,409);
});

test('ticket expiry and SAFE_STOP cannot be bypassed with an edited draft',async()=>{
  let now=100;const store=openStore(':memory:');
  try{
    const p=store.createPerson({name:'合成人物',platform:'视频号',stage:'熟悉中',streamer_id:'0001',notes:'',boundary:''});
    const native=createNativeBridge({store:{...store,analysis:()=>({result:{route:'SAFE_STOP',candidates:[]}})},clock:()=>now,config:()=>({}),revision:()=>'',extract:()=>{},analyze:async()=>({id:'synthetic',mode:'local',result:{summary:'',route:'SAFE_STOP',judge:{},candidates:[]}})});
    const code=(await native.manage('/api/devices/pairing','POST',{streamer_id:'0001'})).code;
    const d=await native.handle({method:'POST',headers:{}},'/api/native/pair',{code,name:'x'});
    const req={method:'POST',headers:{authorization:`Bearer ${d.token}`}};
    const b=payload(store.person(p));let a=await native.handle(req,'/api/native/analyze',b);
    await assert.rejects(()=>native.handle(req,`/api/native/tickets/${a.ticket_id}/consume`,{...b,confirmed:true,draft:'绕过停止'}),e=>e.status===409);
    now+=120000;
    await assert.rejects(()=>native.handle(req,`/api/native/tickets/${a.ticket_id}/consume`,{...b,confirmed:true,draft:'过期草稿'}),e=>e.status===410);
  }finally{store.close();}
});

test('image extraction requires approval and cancels in-flight output',async()=>{
  const store=openStore(':memory:');let release,entered;
  const begun=new Promise(r=>entered=r),hold=new Promise(r=>release=r);let calls=0;
  try{
    const native=createNativeBridge({store,config:()=>({}),revision:()=>'',analyze:()=>{},extract:async()=>{calls++;entered();await hold;return {text:'synthetic'};}});
    const code=(await native.manage('/api/devices/pairing','POST',{streamer_id:'0001'})).code;
    const d=await native.handle({method:'POST',headers:{}},'/api/native/pair',{code,name:'x'});
    const req={method:'POST',headers:{authorization:`Bearer ${d.token}`}},body={context:'image',host:'com.synthetic',image:'synthetic'};
    await assert.rejects(()=>native.handle(req,'/api/native/extract',body),e=>e.status===400);assert.equal(calls,0);
    const pending=native.handle(req,'/api/native/extract',{...body,approved:true});await begun;
    await native.handle(req,'/api/native/cancel',{context:'image'});release();await assert.rejects(()=>pending,e=>e.status===409);
  }finally{store.close();}
});

test('iOS short lease exposes no device token, redeems one immutable draft and remains revocable',async t=>{
  const {request,p,pair}=await fixture(t);const d=await pair();
  const stage=async()=>{
    const a=(await request('native/analyze','POST',payload(p),d.token)).body;
    return (await request(`native/tickets/${a.ticket_id}/lease`,'POST',{...payload(p),approved:true,draft:'人工批准的唯一草稿'},d.token)).body;
  };
  const l=await stage();assert.equal(l.draft,'人工批准的唯一草稿');assert(!JSON.stringify(l).includes(d.token));
  assert.equal((await request('native/roster','GET',null,l.secret)).status,401);
  assert.equal((await request('native/redeem','POST',{lease_id:l.lease_id,secret:'wrong',confirmed:true})).status,410);
  assert.equal((await request('native/redeem','POST',{lease_id:l.lease_id,secret:l.secret})).status,400);
  const r=await request('native/redeem','POST',{lease_id:l.lease_id,secret:l.secret,confirmed:true,draft:'伪造新文本'});
  assert.equal(r.status,200);assert.equal(r.body.draft,'人工批准的唯一草稿');
  assert.equal((await request('native/redeem','POST',{lease_id:l.lease_id,secret:l.secret,confirmed:true})).status,410);
  const next=await stage();assert.equal((await request(`devices/${d.id}`,'DELETE')).status,200);
  assert.equal((await request('native/redeem','POST',{lease_id:next.lease_id,secret:next.secret,confirmed:true})).status,410);
});

test('iOS lease expires in 30 seconds using server time',async()=>{
  let now=100;const store=openStore(':memory:');
  try{
    const id=store.createPerson({name:'合成人物',platform:'视频号',stage:'熟悉中',notes:'',boundary:''});
    const native=createNativeBridge({store:{...store,analysis:()=>({result:{route:'FAST',candidates:[{text:'x'}]}})},clock:()=>now,config:()=>({}),revision:()=>'',extract:()=>{},analyze:async()=>({id:'synthetic',mode:'local',result:{summary:'',route:'FAST',judge:{},candidates:[{text:'x'}]}})});
    const code=(await native.manage('/api/devices/pairing','POST',{streamer_id:'0001'})).code;
    const d=await native.handle({method:'POST',headers:{}},'/api/native/pair',{code,name:'x'}),req={method:'POST',headers:{authorization:`Bearer ${d.token}`}};
    const b=payload(store.person(id)),a=await native.handle(req,'/api/native/analyze',b);
    const l=await native.handle(req,`/api/native/tickets/${a.ticket_id}/lease`,{...b,draft:'x'});
    assert.equal(l.expires_at-now,30000);now+=30000;
    await assert.rejects(()=>native.handle({method:'POST',headers:{}},'/api/native/redeem',{...l,confirmed:true}),e=>e.status===410);
  }finally{store.close();}
});
