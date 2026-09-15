import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {once} from 'node:events';
import {openCloudAuth} from '../cloud-auth.mjs';
import {createBudget,budgetErrorDetails} from '../cloud-budget.mjs';
import {createCloud} from '../cloud.mjs';

// Synthetic ledger, prices, clock and loopback HTTP only. Never read runtime config.
const instant=Date.UTC(2026,8,10,12),nextDay=Date.UTC(2026,8,11),nextMonth=Date.UTC(2026,9,1);
const reservation=274144;
const config={verified:true,dailyCount:20,dailyMicros:10000000,monthlyMicros:100000000,
  inputPerMillion:1000000,outputPerMillion:1000000,currency:'SYNTHETIC'};
function fixture(t,overrides={},start=instant) {
  let now=start;const auth=openCloudAuth(':memory:',()=>now),account=auth.invite().account_id;
  t.after(()=>auth.close());
  return {auth,account,budget:createBudget(auth,{...config,...overrides}),setTime:value=>{now=value;}};
}
function seed(auth,account,{reserved=0,charged=0,calls=0,type='REPLY',created=instant,state='DONE',fingerprint=randomUUID()}={}) {
  const id=randomUUID();
  auth.run('INSERT INTO tasks(id,account,fingerprint,created,state,reserved,charged,calls,task_type) VALUES(?,?,?,?,?,?,?,?,?)',
    id,account,fingerprint,created,state,reserved,charged,calls,type);
  return id;
}
function blocked(f,type='REPLY',fingerprint=randomUUID(),retryOf) {
  let error;try{f.budget.reserve(randomUUID(),f.account,fingerprint,retryOf,type);}catch(e){error=e;}
  assert.ok(error,'a new reservation must be refused');
  const block=budgetErrorDetails(error).budget_block;assert.ok(block);assert.equal(block.day_timezone,'UTC');
  return {error,block,codes:block.reasons.map(r=>r.code)};
}
const ledger=auth=>auth.all('SELECT * FROM tasks ORDER BY rowid').map(row=>({...row}));

test('daily money uses the next UTC day and preserves unknown charges without adding a task',t=>{
  const f=fixture(t,{dailyMicros:reservation+100});
  seed(f.auth,f.account,{reserved:200,charged:30,calls:1,state:'UNCERTAIN'});const before=ledger(f.auth);
  const {error,block,codes}=blocked(f);
  assert.equal(error.status,429);assert.equal(error.message,'项目分析预算已用完，请稍后再试。');
  assert.deepEqual(codes,['PROJECT_DAILY_AMOUNT']);assert.equal(block.reset_at,nextDay);
  assert.match(block.message,/2026-09-11 08:00/);assert.deepEqual(ledger(f.auth),before);
  f.setTime(nextDay);assert.equal(f.budget.reserve(randomUUID(),f.account,'after-day').existing,null);
  assert.deepEqual(ledger(f.auth)[0],before[0]);
});

test('month-only spending does not claim the next daily reset will restore the budget',t=>{
  const f=fixture(t,{monthlyMicros:reservation+100});
  seed(f.auth,f.account,{charged:200,created:instant-86400000});
  const {block,codes}=blocked(f);
  assert.deepEqual(codes,['PROJECT_MONTHLY_AMOUNT']);assert.equal(block.reset_at,nextMonth);
  assert.match(block.message,/2026-10-01 08:00/);assert.doesNotMatch(block.message,/2026-09-11 08:00/);
  f.setTime(nextDay);assert.deepEqual(blocked(f).codes,['PROJECT_MONTHLY_AMOUNT']);
  f.setTime(nextMonth);assert.equal(f.budget.reserve(randomUUID(),f.account,'after-month').existing,null);
});

test('simultaneous daily and monthly exhaustion reports both and waits for the later cycle',t=>{
  const f=fixture(t,{dailyMicros:reservation+100,monthlyMicros:reservation+100});
  seed(f.auth,f.account,{reserved:200,calls:1,state:'FAILED'});const before=ledger(f.auth);
  const {block,codes}=blocked(f);
  assert.deepEqual(codes,['PROJECT_DAILY_AMOUNT','PROJECT_MONTHLY_AMOUNT']);assert.equal(block.reset_at,nextMonth);
  assert.deepEqual(block.reasons.map(r=>r.reset_at),[nextDay,nextMonth]);
  assert.match(block.message,/最早可在 2026-10-01 08:00/);assert.deepEqual(ledger(f.auth),before);
  f.setTime(nextDay);assert.deepEqual(blocked(f).codes,['PROJECT_MONTHLY_AMOUNT']);
});

test('profile, account and project counts retain old priority and do not hide monthly blocking',t=>{
  const f=fixture(t,{monthlyMicros:reservation+100});
  for(let i=0;i<20;i++)seed(f.auth,f.account,{type:i<10?'PROFILE':'REPLY',charged:i===0?200:0});
  const {error,block,codes}=blocked(f,'PROFILE');
  assert.equal(error.message,'今天的新客画像次数已用完，每个主播账号每天最多 10 次。');
  assert.deepEqual(codes,['PROFILE_DAILY_LIMIT','ACCOUNT_DAILY_COUNT','PROJECT_DAILY_COUNT','PROJECT_MONTHLY_AMOUNT']);
  assert.equal(block.reset_at,nextMonth);
  assert.equal(blocked(f).error.message,'今天的分析次数已用完，明天再试。');
  const other=f.auth.invite().account_id;
  const result=blocked({...f,account:other},'OPENING');
  assert.deepEqual(result.codes,['PROJECT_DAILY_COUNT','PROJECT_MONTHLY_AMOUNT']);
  assert.equal(result.error.message,'项目今天的分析次数已用完，明天再试。');
  assert.equal(f.budget.summary(other).used_today,0);assert.equal(ledger(f.auth).length,20);
});

test('the tenth profile is accepted; the eleventh reports a daily quota and leaves replies available',t=>{
  const f=fixture(t);for(let i=0;i<9;i++)seed(f.auth,f.account,{type:'PROFILE'});
  const id=randomUUID();f.budget.reserve(id,f.account,'tenth',undefined,'PROFILE');f.budget.finish(id,'synthetic-analysis');
  const {block,codes}=blocked(f,'PROFILE');assert.deepEqual(codes,['PROFILE_DAILY_LIMIT']);assert.equal(block.reset_at,nextDay);
  assert.equal(f.budget.reserve(randomUUID(),f.account,'reply').existing,null);
  f.setTime(nextDay);assert.equal(f.budget.reserve(randomUUID(),f.account,'new-day',undefined,'PROFILE').existing,null);
});

test('missing configuration and protection pause are distinct and never promise automatic recovery',t=>{
  const f=fixture(t,{verified:false});let result=blocked(f);
  assert.equal(result.error.status,503);assert.equal(result.error.message,'模型预算尚未配置或已暂停。');
  assert.deepEqual(result.codes,['BUDGET_NOT_CONFIGURED']);assert.equal(result.block.reset_at,null);
  f.auth.run("INSERT INTO control VALUES('budget_blocked','1')");
  result=blocked(f);assert.deepEqual(result.codes,['BUDGET_NOT_CONFIGURED','BUDGET_PROTECTION_PAUSED']);assert.equal(result.block.reset_at,null);
  const configured=createBudget(f.auth,config);f.setTime(nextMonth);
  result=blocked({...f,budget:configured});assert.deepEqual(result.codes,['BUDGET_PROTECTION_PAUSED']);assert.equal(result.block.reset_at,null);
  assert.equal(f.auth.get("SELECT value FROM control WHERE key='budget_blocked'").value,'1');assert.equal(ledger(f.auth).length,0);
});

test('over-reservation protection reports a pause and keeps the charged ledger intact across reset',t=>{
  const f=fixture(t),id=randomUUID();f.budget.reserve(id,f.account,'provider-overage');
  const hooks=f.budget.hooks(id);hooks.beforeCall();
  assert.throws(()=>hooks.onUsage({input_tokens:131073,output_tokens:0,total_tokens:131073}),/已暂停新分析/);
  f.budget.finish(id,null,true);const before=ledger(f.auth);
  f.setTime(nextMonth);assert.deepEqual(blocked(f).codes,['BUDGET_PROTECTION_PAUSED']);assert.deepEqual(ledger(f.auth),before);
});

test('a single reservation exceeding the full configured amount cannot recover just by waiting',t=>{
  const f=fixture(t,{dailyMicros:reservation-1,monthlyMicros:reservation-1});
  const {block,codes}=blocked(f);assert.deepEqual(codes,['PROJECT_DAILY_AMOUNT','PROJECT_MONTHLY_AMOUNT']);
  assert.equal(block.reset_at,null);assert(block.reasons.every(r=>r.reset_at===null));assert.match(block.message,/不能仅等待重置/);
  f.setTime(nextMonth);assert.equal(blocked(f).block.reset_at,null);
  const zeroCount=createBudget(f.auth,{...config,dailyCount:0});
  assert.equal(blocked({...f,budget:zeroCount}).block.reset_at,null);
});

test('UTC month boundaries handle December rollover and leap February without changing old spend',t=>{
  for(const [now,reset] of [[Date.UTC(2026,11,31,23,59,59,999),Date.UTC(2027,0,1)],[Date.UTC(2028,1,28,23,59),Date.UTC(2028,2,1)]]) {
    const f=fixture(t,{dailyMicros:reservation+100,monthlyMicros:reservation+100},now);
    seed(f.auth,f.account,{reserved:200,created:now});const before=ledger(f.auth);
    assert.equal(blocked(f).block.reset_at,reset);
    f.setTime(reset);assert.equal(f.budget.reserve(randomUUID(),f.account,'new-period').existing,null);
    assert.deepEqual(ledger(f.auth)[0],before[0]);
  }
});

test('cached and uncertain original work remain queryable while new work is blocked',t=>{
  const f=fixture(t),done=seed(f.auth,f.account,{fingerprint:'done'}),pending=seed(f.auth,f.account,{fingerprint:'uncertain',reserved:400,calls:1,state:'UNCERTAIN'});
  f.auth.run("INSERT INTO control VALUES('budget_blocked','1')");const before=ledger(f.auth);
  assert.equal(f.budget.reserve(randomUUID(),f.account,'done').existing.id,done);
  assert.equal(f.budget.reserve(randomUUID(),f.account,'uncertain').existing.id,pending);
  const retry=blocked(f,'REPLY','uncertain',pending);assert.deepEqual(retry.codes,['BUDGET_PROTECTION_PAUSED']);
  assert.deepEqual(ledger(f.auth),before);
});

test('generic exceptions cannot inject budget details into HTTP responses',()=>{
  assert.deepEqual(budgetErrorDetails(Object.assign(new Error('synthetic'),{status:503,budgetBlock:{message:'untrusted'}})),{});
  assert.deepEqual(budgetErrorDetails(new Error('synthetic')),{});
});

async function httpFixture(t,overrides={}) {
  const parent=resolve(tmpdir()),prefix=join(parent,'lens-budget-block-http-synthetic-'),directory=mkdtempSync(prefix);
  let calls=0;const app=createCloud({directory,apiKey:'synthetic',clock:()=>instant,budget:{...config,...overrides},
    fetcher:async()=>{calls++;throw new Error('Provider must not be called for rejected work');}});
  t.after(async()=>{await app.close();if(dirname(resolve(directory))!==parent||!directory.startsWith(prefix))throw new Error('Unsafe synthetic cleanup');rmSync(directory,{recursive:true,force:true});});
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  const base=`http://127.0.0.1:${app.server.address().port}/api/native/`;
  const invited=app.auth.invite(),identity=app.auth.activate(invited.invite,'synthetic');
  const request=async(path,body)=>{const r=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+identity.token},body:JSON.stringify(body)});return {status:r.status,body:await r.json()};};
  const created=await request('library/people',{name:'合成预算测试人物',platform:'微信'});assert.equal(created.status,200);
  const person=created.body;
  const payload={request_id:randomUUID(),person_id:person.id,pair_id:person.relationship.id,context:'synthetic-editor',host:'com.synthetic.chat',
    approved:true,mode:'model',task_type:'REPLY',text:'对方：今天想好好休息。',goal:'关心近况'};
  return {app,identity,request,payload,get calls(){return calls;}};
}

test('HTTP budget rejection serializes every cause and performs zero model calls',async t=>{
  const cases=[
    {name:'daily',config:{dailyMicros:reservation+100},seed:{reserved:200},codes:['PROJECT_DAILY_AMOUNT'],reset:nextDay,status:429},
    {name:'monthly',config:{monthlyMicros:reservation+100},seed:{reserved:200,created:instant-86400000},codes:['PROJECT_MONTHLY_AMOUNT'],reset:nextMonth,status:429},
    {name:'both',config:{dailyMicros:reservation+100,monthlyMicros:reservation+100},seed:{reserved:200},codes:['PROJECT_DAILY_AMOUNT','PROJECT_MONTHLY_AMOUNT'],reset:nextMonth,status:429},
    {name:'missing',config:{verified:false},codes:['BUDGET_NOT_CONFIGURED'],reset:null,status:503},
    {name:'paused',pause:true,codes:['BUDGET_PROTECTION_PAUSED'],reset:null,status:503},
    {name:'profile',count:10,type:'PROFILE',codes:['PROFILE_DAILY_LIMIT'],reset:nextDay,status:429},
    {name:'account and project',count:20,codes:['ACCOUNT_DAILY_COUNT','PROJECT_DAILY_COUNT'],reset:nextDay,status:429},
    {name:'project only',count:20,other:true,codes:['PROJECT_DAILY_COUNT'],reset:nextDay,status:429}
  ];
  for(const scenario of cases)await t.test(scenario.name,async st=>{
    const f=await httpFixture(st,scenario.config),account=f.identity.account_id;
    if(scenario.seed)seed(f.app.auth,account,scenario.seed);
    if(scenario.pause)f.app.auth.run("INSERT INTO control VALUES('budget_blocked','1')");
    const seedAccount=scenario.other?f.app.auth.invite().account_id:account;
    for(let i=0;i<(scenario.count||0);i++)seed(f.app.auth,seedAccount,{type:scenario.type||'REPLY'});
    const body=scenario.type==='PROFILE'?{...f.payload,task_type:'PROFILE',text:'',goal:undefined,materials:[{id:'M1',kind:'USER_NOTE',text:'合成资料：喜欢散步。',source:'合成测试',observed_at:'2026-09-10'}]}:f.payload;
    const before=ledger(f.app.auth),result=await f.request('analyze',body);
    assert.equal(result.status,scenario.status);assert.equal(typeof result.body.error,'string');assert.equal(typeof result.body.request_id,'string');
    assert.deepEqual(result.body.budget_block.reasons.map(r=>r.code),scenario.codes);assert.equal(result.body.budget_block.reset_at,scenario.reset);
    assert.equal(result.body.budget_block.day_timezone,'UTC');assert.equal(typeof result.body.budget_block.message,'string');
    assert.equal(f.calls,0);assert.deepEqual(ledger(f.app.auth),before);
  });
});
