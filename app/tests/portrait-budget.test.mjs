import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomUUID} from 'node:crypto';
import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, dirname, resolve} from 'node:path';
import {openCloudAuth} from '../cloud-auth.mjs';
import {createBudget} from '../cloud-budget.mjs';

// Test-only limits and usage. No provider is contacted and no runtime config is read.
const syntheticBudget = {verified:true, dailyCount:50, dailyMicros:1000000000,
  monthlyMicros:1000000000, inputPerMillion:800000, outputPerMillion:2000000,
  currency:'SYNTHETIC'};
function completed(limits, account, fingerprint, type='PROFILE') {
  const id=randomUUID();
  limits.reserve(id,account,fingerprint,undefined,type);
  const hooks=limits.hooks(id);
  hooks.beforeCall();hooks.onUsage({input_tokens:1,output_tokens:1,total_tokens:2});
  limits.finish(id,randomUUID());
  return id;
}

test('ten portrait analyses are shared by an account, not by customer or device',()=>{
  let clock=Date.UTC(2026,8,10,12);
  const auth=openCloudAuth(':memory:',()=>clock);
  try {
    const a=auth.invite().account_id,b=auth.invite().account_id;
    const limits=createBudget(auth,syntheticBudget);
    const ids=[];
    for(let i=0;i<10;i++)ids.push(completed(limits,a,`customer-${i}`));
    assert.throws(()=>limits.reserve(randomUUID(),a,'eleventh-customer',undefined,'PROFILE'),e=>e.status===429);
    assert.equal(limits.reserve(ids[0],a,'customer-0',undefined,'PROFILE').existing.id,ids[0]);
    completed(limits,b,'same-other-customer');
    completed(limits,a,'reply-after-ten','REPLY');
    completed(limits,a,'opening-after-ten','OPENING');
    assert.equal(limits.summary(a).portrait_used_today,10);
    assert.equal(limits.summary(b).portrait_used_today,1);
    assert.equal(limits.summary(a).portrait_daily_limit,10);
    assert.equal(limits.summary(a).used_today,12);
    assert.equal(limits.summary(a).project_used_today,13);
    assert.equal(limits.summary(b).project_used_today,13);
    assert.equal(limits.summary(a).reply_used_today,1);
    assert.equal(limits.summary(a).opening_used_today,1);
    assert.equal(limits.summary(b).reply_used_today,0);
    assert.equal(limits.summary(a).reset_at,Date.UTC(2026,8,11));
    assert.equal(limits.summary(a).day_timezone,'UTC');
    clock=Date.UTC(2026,8,11);
    assert.equal(limits.summary(a).portrait_used_today,0);
    assert.equal(limits.summary(a).project_used_today,0);
    assert.equal(limits.summary(a).reply_used_today,0);
    assert.equal(limits.summary(a).opening_used_today,0);
    completed(limits,a,'new-day');
    assert.equal(limits.summary(a).portrait_used_today,1);
    assert.equal(auth.get("SELECT COUNT(*) n FROM tasks WHERE account=? AND task_type='PROFILE'",a).n,11);
  } finally {auth.close();}
});

test('portrait quota supplements project counts and monetary limits',()=>{
  const auth=openCloudAuth(':memory:');
  try {
    const a=auth.invite().account_id,b=auth.invite().account_id;
    const limits=createBudget(auth,{...syntheticBudget,dailyCount:1});
    completed(limits,a,'one');
    assert.throws(()=>limits.reserve(randomUUID(),b,'two',undefined,'PROFILE'),e=>e.status===429);
    assert.throws(()=>limits.reserve(randomUUID(),a,'reply',undefined,'REPLY'),e=>e.status===429);
    const insufficient=createBudget(auth,{...syntheticBudget,dailyMicros:1});
    assert.throws(()=>insufficient.reserve(randomUUID(),b,'money',undefined,'PROFILE'),e=>e.status===429);
    assert.equal(limits.summary(b).portrait_used_today,0);
  } finally {auth.close();}
});

test('zero-call failures release portrait quota; uncertain paid work does not',()=>{
  const auth=openCloudAuth(':memory:');
  try {
    const account=auth.invite().account_id,limits=createBudget(auth,syntheticBudget);
    const empty=randomUUID();limits.reserve(empty,account,'before-provider',undefined,'PROFILE');
    assert.equal(limits.summary(account).portrait_used_today,1);
    limits.finish(empty,null,true);
    assert.equal(limits.summary(account).portrait_used_today,0);
    const paid=randomUUID();limits.reserve(paid,account,'uncertain',undefined,'PROFILE');
    limits.hooks(paid).beforeCall();limits.finish(paid,null,true);
    assert.equal(limits.summary(account).portrait_used_today,1);
    const original={...auth.get('SELECT * FROM tasks WHERE id=?',paid)};
    assert.equal(limits.reserve(randomUUID(),account,'uncertain',undefined,'PROFILE').existing.id,paid);
    assert.equal(limits.summary(account).portrait_used_today,1);
    const retry=randomUUID();limits.reserve(retry,account,'uncertain',paid,'PROFILE');
    assert.equal(limits.summary(account).portrait_used_today,2);
    assert.deepEqual({...auth.get('SELECT * FROM tasks WHERE id=?',paid)},original);
  } finally {auth.close();}
});

test('task identity cannot be reused to bypass the portrait quota',()=>{
  const auth=openCloudAuth(':memory:');
  try {
    const account=auth.invite().account_id,limits=createBudget(auth,syntheticBudget);
    const id=completed(limits,account,'content','REPLY');
    assert.throws(()=>limits.reserve(id,account,'content',undefined,'PROFILE'),e=>e.status===409);
    assert.throws(()=>limits.reserve(randomUUID(),account,'invalid',undefined,'UNKNOWN'),e=>e.status===400);
    const failed=randomUUID();limits.reserve(failed,account,'failed-reply',undefined,'REPLY');limits.finish(failed,null,true);
    assert.throws(()=>limits.reserve(failed,account,'failed-reply',undefined,'PROFILE'),e=>e.status===409);
    assert.throws(()=>limits.reserve(randomUUID(),account,'failed-reply',failed,'PROFILE'),e=>e.status===409);
    assert.equal(limits.summary(account).portrait_used_today,0);
  } finally {auth.close();}
});

test('identity ledger migration preserves usage and supports persistent portrait quota',t=>{
  const temporaryRoot=resolve(tmpdir());
  const directory=mkdtempSync(join(temporaryRoot,'lens-portrait-budget-synthetic-'));
  assert.equal(dirname(resolve(directory)),temporaryRoot);
  t.after(()=>rmSync(directory,{recursive:true,force:true}));
  const file=join(directory,'identity.sqlite'),account=randomUUID(),task=randomUUID();
  const old=new DatabaseSync(file);
  old.exec(`CREATE TABLE accounts(id TEXT PRIMARY KEY, created INTEGER NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE tasks(id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), fingerprint TEXT NOT NULL, created INTEGER NOT NULL, state TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0, usage TEXT NOT NULL DEFAULT '[]', analysis TEXT);`);
  old.prepare('INSERT INTO accounts(id,created) VALUES(?,?)').run(account,Date.now());
  old.prepare('INSERT INTO tasks(id,account,fingerprint,created,state,reserved,charged,calls) VALUES(?,?,?,?,?,?,?,?)')
    .run(task,account,'legacy-usage',Date.now(),'FAILED',1000,50,1);
  old.close();
  let auth=openCloudAuth(file);
  const prior={...auth.get('SELECT * FROM tasks WHERE id=?',task)};
  assert.equal(prior.task_type,'REPLY');assert.equal(prior.reserved,1000);assert.equal(prior.charged,50);
  const change=auth.run('INSERT INTO customer_changes(account,person,segment,created) VALUES(?,?,?,?)',account,randomUUID(),'MAINTAIN',Date.now());
  assert.ok(change.lastInsertRowid);
  completed(createBudget(auth,syntheticBudget),account,'new-profile');
  auth.close();auth=openCloudAuth(file);
  try {
    assert.deepEqual({...auth.get('SELECT * FROM tasks WHERE id=?',task)},prior);
    assert.equal(createBudget(auth,syntheticBudget).summary(account).portrait_used_today,1);
    assert.equal(auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);
  } finally {auth.close();}
});
