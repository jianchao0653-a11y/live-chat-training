import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync,backup} from 'node:sqlite';
import {mkdtempSync,rmSync,readFileSync,writeFileSync,copyFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,dirname} from 'node:path';
import {randomUUID,randomBytes,createCipheriv} from 'node:crypto';
import {once} from 'node:events';
import {spawnSync} from 'node:child_process';
import {openStore} from '../store.mjs';
import {verifySnapshot,restoreToNewFile} from '../recovery.mjs';
import {createCloud} from '../cloud.mjs';
import {backupCloud,restoreCloud} from '../cloud-maintenance.mjs';
import {openCloudAuth} from '../cloud-auth.mjs';
import {setCloudCustomerSegment} from '../customer-classification.mjs';
import {localAnalysis} from '../engine.mjs';

function syntheticDirectory(t,beforeCleanup=async()=>{}){
  const parent=resolve(tmpdir()),prefix=join(parent,'lens-customer-synthetic-'),directory=mkdtempSync(prefix);
  t.after(async()=>{await beforeCleanup();if(dirname(directory)!==parent||!directory.startsWith(prefix))throw new Error('Unsafe synthetic cleanup target');rmSync(directory,{recursive:true,force:true});});
  return directory;
}
const chat='对方：今天加班很累，想安静休息。';
const budget={verified:true,inputPerMillion:1000000,outputPerMillion:1000000,dailyMicros:10000000,monthlyMicros:100000000,dailyCount:20,currency:'SYNTHETIC'};
function syntheticResponse(_url,options){
  const input=JSON.parse(options.body),isJudge=input.max_tokens===512;
  const {judge,...result}=localAnalysis(chat,{name:'合成人物',claims:[]},'关心近况');
  return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},choices:[{finish_reason:'stop',message:{content:JSON.stringify(isJudge?{verdict:'PASS',reason:'合成终审'}:result)}}]}));
}
async function fixture(t,fetcher=syntheticResponse){
  let app,base;
  const root=syntheticDirectory(t,async()=>{if(app)await app.close();}),directory=join(root,'live');
  const start=async()=>{app=createCloud({directory,apiKey:'synthetic-key',model:'qwen-plus',fetcher,budget});app.server.listen(0,'127.0.0.1');await once(app.server,'listening');base=`http://127.0.0.1:${app.server.address().port}`;};
  const stop=async()=>{if(app){const closing=app;app=null;await closing.close();}};
  await start();
  const request=async(path,body,token,method)=>{const response=await fetch(base+'/api/native/'+path,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});return {status:response.status,body:await response.json()};};
  const activate=async()=>{const invite=app.auth.invite();return (await request('auth/activate',{code:invite.invite,name:'synthetic',approved:true})).body;};
  const person=async(identity,extra={})=>(await request('library/people',{name:'合成人物',platform:'微信',...extra},identity.token)).body;
  return {root,directory,request,activate,person,start,stop,get app(){return app;}};
}
const payload=(person,extra={})=>({request_id:randomUUID(),person_id:person.id,pair_id:person.relationship.id,context:'synthetic-editor',host:'com.synthetic.chat',approved:true,text:chat,goal:'关心近况',mode:'model',...extra});
function seedHistory(store,id){
  const person=store.person(id),stamp=new Date().toISOString(),claimId=randomUUID();
  store.run('INSERT INTO claims(id,person_id,kind,content,source,created_at,pair_id) VALUES(?,?,?,?,?,?,?)',claimId,id,'FACT','喜欢散步','合成资料',stamp,person.relationship.id);
  const analysis=store.saveAnalysis(person,chat,'关心近况',randomUUID(),localAnalysis(chat,person,'关心近况'),'local',null);
  store.saveOutcome(analysis.id,{status:'POSITIVE',note:'合成后续',draft:'合成草稿'});
  return {claimId,analysisId:analysis.id};
}
const history=store=>Object.fromEntries(['analyses','outcomes','claims','context_events'].map(table=>[table,store.all(`SELECT * FROM ${table} ORDER BY rowid`)]));

for(const version of [1,2])test(`schema ${version} migrates to 3 without reclassifying customers or losing their history`,async t=>{
  const directory=syntheticDirectory(t),source=join(directory,`v${version}.sqlite`),target=join(directory,'restored.sqlite');
  const old=openStore(':memory:',version===1?{legacySchema:true}:{legacyVersion:2});
  const id=old.createPerson({name:'旧合成人物',platform:'微信',stage:'熟悉中'},randomUUID());
  const seeded=seedHistory(old,id);await backup(old.db,source);old.close();
  const original=readFileSync(source);assert.equal(verifySnapshot(source,{allowLegacy:true}).schemaVersion,version);
  assert.throws(()=>verifySnapshot(source),/schema/);
  assert.equal(restoreToNewFile(source,target).schemaVersion,3);assert.deepEqual(readFileSync(source),original);
  const current=openStore(target);
  try{assert.equal(current.person(id).segment,'UNCLASSIFIED');assert.equal(current.person(id).stage,'熟悉中');assert.equal(current.analysis(seeded.analysisId).outcome.note,'合成后续');assert.equal(current.person(id).claims[0].id,seeded.claimId);assert.equal(current.people()[0].segment,'UNCLASSIFIED');}
  finally{current.close();}
});

test('snapshot allowlist accepts schema 3 and rejects unknown columns or triggers in every supported version',async t=>{
  const directory=syntheticDirectory(t);
  for(const version of [1,2,3]){
    const source=join(directory,`v${version}.sqlite`),store=openStore(':memory:',version<3?{legacyVersion:version}:{});
    await backup(store.db,source);store.close();
    assert.equal(verifySnapshot(source,{allowLegacy:true}).schemaVersion,version);
    for(const [name,sql] of [['column','ALTER TABLE people ADD COLUMN unexpected TEXT'],['trigger','CREATE TRIGGER unexpected AFTER INSERT ON people BEGIN SELECT 1; END']]){
      const modified=join(directory,`v${version}-${name}.sqlite`);copyFileSync(source,modified);
      const database=new DatabaseSync(modified);database.exec(sql);database.close();
      assert.throws(()=>verifySnapshot(modified,{allowLegacy:true}),/schema/);
    }
  }
  assert.throws(()=>openStore(join(directory,'legacy.sqlite'),{legacyVersion:2}),/memory-only/);
});

test('customer segment change preserves history, invalidates tickets, is idempotent and isolated',async t=>{
  const f=await fixture(t),identity=await f.activate(),other=await f.activate(),person=await f.person(identity);
  assert.equal(person.segment,'NEW');
  assert.equal((await f.person(identity,{name:'未分类合成人物',segment:'UNCLASSIFIED'})).segment,'UNCLASSIFIED');
  const store=f.app.application(identity.account_id).store;
  seedHistory(store,person.id);
  const analyzed=await f.request('analyze',payload(person),identity.token);assert.equal(analyzed.status,200);
  const before=history(store),revision=store.pair(person.id).revision;
  const changed=await f.request(`library/people/${person.id}/segment`,{segment:'MAINTAIN'},identity.token);
  assert.equal(changed.status,200);assert.equal(changed.body.person.id,person.id);assert.equal(changed.body.person.segment,'MAINTAIN');assert.equal(changed.body.unchanged,false);
  assert.deepEqual(history(store),before);assert.equal(store.pair(person.id).revision,revision+1);
  assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM deletions').n,0);assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);
  const roster=await f.request('roster',null,identity.token);assert.equal(roster.body.people.find(p=>p.id===person.id).segment,'MAINTAIN');
  const list=await f.request('library/people',null,identity.token);assert.equal(list.body.people.find(p=>p.id===person.id).segment,'MAINTAIN');
  const same=await f.request(`library/people/${person.id}/segment`,{segment:'MAINTAIN'},identity.token);
  assert.equal(same.body.unchanged,true);assert.equal(store.pair(person.id).revision,revision+1);assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);
  assert.equal((await f.request(`library/people/${person.id}/segment`,{segment:'UNKNOWN'},identity.token)).status,400);
  assert.equal((await f.request(`library/people/${person.id}/segment`,{segment:'NEW'},other.token)).status,404);
  assert.equal((await f.request(`tickets/${analyzed.body.ticket_id}/consume`,{...payload(person),confirmed:true,draft:'合成草稿'},identity.token)).status,409);
  assert.deepEqual(history(store),before);
});

test('customer segment cannot change during analysis and rejected changes create no journal record',async t=>{
  let entered,release;const waiting=new Promise(resolve=>entered=resolve),hold=new Promise(resolve=>release=resolve);let calls=0;
  const f=await fixture(t,async(url,options)=>{if(++calls===1){entered();await hold;}return syntheticResponse(url,options);});
  const identity=await f.activate(),person=await f.person(identity),job=f.request('analyze',payload(person),identity.token);
  await waiting;
  try{assert.equal((await f.request(`library/people/${person.id}/segment`,{segment:'MAINTAIN'},identity.token)).status,409);assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,0);}
  finally{release();}
  assert.equal((await job).status,200);assert.equal(f.app.application(identity.account_id).store.person(person.id).segment,'NEW');
});

test('cloud restore replays classifications without dropping history and deletion wins over classification',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),removed=await f.person(identity,{name:'合成待删除人物'}),key=Buffer.alloc(32,7);
  const store=f.app.application(identity.account_id).store;seedHistory(store,person.id);const before=history(store);
  await f.stop();const snap=await backupCloud(f.directory,join(f.root,'backups'),key);
  await f.start();
  assert.equal((await f.request(`library/people/${person.id}/segment`,{segment:'MAINTAIN'},identity.token)).status,200);
  await f.request(`library/people/${removed.id}/segment`,{segment:'MAINTAIN'},identity.token);
  await f.request(`library/people/${removed.id}/delete`,{},identity.token);
  const taskId=randomUUID();f.app.budget.reserve(taskId,identity.account_id,'synthetic-preserved-budget');
  await f.stop();const target=join(f.root,'restored'),result=await restoreCloud(snap.destination,key,f.directory,target);
  assert.equal(result.replayed_customer_changes,1);assert.equal(result.discarded_person_snapshots,1);assert.equal(result.budgetRolledBack,false);
  const restored=openStore(join(target,'accounts',identity.account_id+'.sqlite'));
  try{assert.equal(restored.person(person.id).segment,'MAINTAIN');assert.equal(restored.person(removed.id),null);for(const table of ['analyses','outcomes','claims'])assert.deepEqual(history(restored)[table],before[table]);}
  finally{restored.close();}
  const auth=openCloudAuth(join(target,'identity.sqlite'));
  try{assert.equal(auth.get('SELECT COUNT(*) n FROM customer_changes').n,2);assert(auth.get('SELECT reserved FROM tasks WHERE id=?',taskId).reserved>0);assert.throws(()=>auth.authorize(identity.token),e=>e.status===401);}
  finally{auth.close();}
});

function writeSyntheticBackup(file,value,key){
  const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv),encrypted=Buffer.concat([cipher.update(Buffer.from(JSON.stringify(value))),cipher.final()]);
  writeFileSync(file,Buffer.concat([Buffer.from('LENSBK01'),iv,cipher.getAuthTag(),encrypted]),{flag:'wx'});
}
test('legacy backups without classification sequence replay from zero and reject a newer missing ledger',async t=>{
  const f=await fixture(t),identity=await f.activate(),old=openStore(':memory:',{legacyVersion:2}),key=Buffer.alloc(32,9);
  const id=old.createPerson({name:'旧备份合成人物',platform:'微信',stage:'初识'},randomUUID());seedHistory(old,id);
  const oldFile=join(f.root,'legacy-account.sqlite');await backup(old.db,oldFile);old.close();
  f.app.auth.run('INSERT INTO customer_changes(account,person,segment,created) VALUES(?,?,?,?)',identity.account_id,id,'MAINTAIN',Date.now());
  await f.stop();
  const value={version:1,created:Date.now(),deletion_seq:0,accounts:[{id:identity.account_id,data:readFileSync(oldFile).toString('base64')}]};
  const source=join(f.root,'legacy.lensbackup');writeSyntheticBackup(source,value,key);
  const target=join(f.root,'legacy-restored');assert.equal((await restoreCloud(source,key,f.directory,target)).replayed_customer_changes,1);
  const restored=openStore(join(target,'accounts',identity.account_id+'.sqlite'));
  try{assert.equal(restored.person(id).segment,'MAINTAIN');assert.equal(restored.all('SELECT * FROM outcomes').length,1);assert.equal(restored.get('PRAGMA user_version').user_version,3);}
  finally{restored.close();}
  const future=join(f.root,'future.lensbackup');writeSyntheticBackup(future,{...value,customer_change_seq:2},key);
  await assert.rejects(()=>restoreCloud(future,key,f.directory,join(f.root,'rejected')),/Customer change journal is older/);
});

test('classification and its recovery journal roll back together when either database rejects the write',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),store=f.app.application(identity.account_id).store;
  seedHistory(store,person.id);const before=history(store),revision=store.pair(person.id).revision;
  for(const [database,sql] of [
    [store,"CREATE TRIGGER synthetic_reject BEFORE UPDATE OF segment ON pairs BEGIN SELECT RAISE(ABORT,'synthetic account write failure'); END"],
    [f.app.auth,"CREATE TRIGGER synthetic_reject AFTER INSERT ON customer_changes BEGIN SELECT RAISE(ABORT,'synthetic journal write failure'); END"]
  ]){
    database.run(sql);
    try{
      assert.throws(()=>setCloudCustomerSegment(f.app.auth,store,identity.account_id,person.id,'MAINTAIN'),/synthetic .* write failure/);
      assert.equal(store.person(person.id).segment,'NEW');assert.equal(store.pair(person.id).revision,revision);
      assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,0);assert.deepEqual(history(store),before);
      assert.equal(f.app.auth.all('PRAGMA database_list').some(row=>row.name==='customer_classification'),false);
    }finally{database.run('DROP TRIGGER synthetic_reject');}
  }
  const changed=setCloudCustomerSegment(f.app.auth,store,identity.account_id,person.id,'MAINTAIN');
  assert.equal(changed.changed,true);assert.equal(changed.person.segment,'MAINTAIN');
  assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);
  assert.equal(setCloudCustomerSegment(f.app.auth,store,identity.account_id,person.id,'MAINTAIN').changed,false);
  assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);assert.deepEqual(history(store),before);
});

test('classification refuses non-durable modes and mismatched account files before changing either database',async t=>{
  const f=await fixture(t),identity=await f.activate(),other=await f.activate(),person=await f.person(identity),store=f.app.application(identity.account_id).store;
  const update=()=>setCloudCustomerSegment(f.app.auth,store,identity.account_id,person.id,'MAINTAIN');
  for(const database of [f.app.auth,store]){
    database.run('PRAGMA synchronous=OFF');
    try{assert.throws(update,error=>error.status===503);}finally{database.run('PRAGMA synchronous=FULL');}
    database.run('PRAGMA journal_mode=WAL');
    try{assert.throws(update,error=>error.status===503);}finally{database.run('PRAGMA journal_mode=DELETE');}
  }
  assert.throws(()=>setCloudCustomerSegment(f.app.auth,store,other.account_id,person.id,'MAINTAIN'),error=>error.status===503);
  assert.equal(store.person(person.id).segment,'NEW');assert.equal(f.app.auth.get('SELECT COUNT(*) n FROM customer_changes').n,0);
  assert.equal(update().person.segment,'MAINTAIN');
});

test('a process exit before commit cannot leave a classification without its journal or an unapplied journal command',async t=>{
  const f=await fixture(t),identity=await f.activate(),person=await f.person(identity),revision=f.app.application(identity.account_id).store.pair(person.id).revision;
  await f.stop();
  const identityFile=join(f.directory,'identity.sqlite'),accountFile=join(f.directory,'accounts',identity.account_id+'.sqlite');
  const script=`
    import {openStore} from ${JSON.stringify(new URL('../store.mjs',import.meta.url).href)};
    import {openCloudAuth} from ${JSON.stringify(new URL('../cloud-auth.mjs',import.meta.url).href)};
    import {setCloudCustomerSegment} from ${JSON.stringify(new URL('../customer-classification.mjs',import.meta.url).href)};
    const [identityFile,accountFile,account,personId,phase]=process.argv.slice(1);
    const auth=openCloudAuth(identityFile),store=openStore(accountFile),run=auth.run;
    auth.run=(sql,...args)=>{
      const journal=sql.startsWith('INSERT INTO customer_changes');
      if(journal&&phase==='before')process.exit(93);
      const result=run(sql,...args);
      if(journal&&phase==='after')process.exit(94);
      return result;
    };
    setCloudCustomerSegment(auth,store,account,personId,'MAINTAIN');
    process.exit(95);
  `;
  for(const phase of ['before','after']){
    const child=spawnSync(process.execPath,['--disable-warning=ExperimentalWarning','--input-type=module','-e',script,identityFile,accountFile,identity.account_id,person.id,phase],{encoding:'utf8',timeout:10000});
    assert.ifError(child.error);assert.equal(child.status,phase==='before'?93:94,child.stderr);
    const auth=openCloudAuth(identityFile),store=openStore(accountFile);
    try{
      assert.equal(store.person(person.id).segment,'NEW');assert.equal(store.pair(person.id).revision,revision);
      assert.equal(auth.get('SELECT COUNT(*) n FROM customer_changes').n,0);
    }finally{store.close();auth.close();}
  }
  const auth=openCloudAuth(identityFile),store=openStore(accountFile);
  try{assert.equal(setCloudCustomerSegment(auth,store,identity.account_id,person.id,'MAINTAIN').person.segment,'MAINTAIN');assert.equal(auth.get('SELECT COUNT(*) n FROM customer_changes').n,1);}
  finally{store.close();auth.close();}
});
