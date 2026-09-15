import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,writeFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {openStore} from '../store.mjs';
import {localAnalysis} from '../engine.mjs';
import {expireHistory} from '../retention.mjs';
import {lockDirectory,backupCloud,pruneBackups} from '../cloud-maintenance.mjs';
import {openCloudAuth} from '../cloud-auth.mjs';
import {createBudget} from '../cloud-budget.mjs';
import {diagnose} from '../diagnostics.mjs';

test('retention preserves recent observations, invalidates consumed results, scrubs legacy orphan prose',()=>{
 const s=openStore(':memory:');try{
 const id=s.createPerson({name:'synthetic',platform:'微信',stage:'初识'},randomUUID()),p=s.context(id);
 const result=localAnalysis('对方：今天很累，需要休息。',p,'关心近况');
 const save=(key,r=result)=>s.saveAnalysis(p,'synthetic '+key,'关心近况',key,r,'local',null);
 const old=save('old'),independent=save('independent'),dependent=save('dependent',{...result,context_receipt:{outcome_ids:[old.id]}});
 for(const a of [old,independent,dependent])s.saveOutcome(a.id,{status:'POSITIVE',note:'synthetic observation',draft:'synthetic draft'});
 s.run('UPDATE analyses SET created_at=? WHERE id=?','2000-01-01T00:00:00.000Z',old.id);
 s.run("UPDATE context_events SET payload=? WHERE type='OUTCOME_RECORDED'",JSON.stringify({note:'legacy private prose'}));
 const before=s.person(id).relationship.revision;
 expireHistory(s,'2020-01-01T00:00:00.000Z');
 assert.equal(s.analysis(old.id),null);assert.deepEqual(s.analysis(independent.id).result,result);
 assert.equal(s.analysis(dependent.id).result.route,'SAFE_STOP');assert.equal(s.analysis(dependent.id).outcome.draft,'synthetic draft');
 assert.ok(s.person(id).relationship.revision>before);
 assert.ok(s.all("SELECT payload FROM context_events WHERE type='OUTCOME_RECORDED'").every(x=>x.payload==='{}'));
 const revision=s.person(id).relationship.revision;
 s.saveOutcome(independent.id,{status:'POSITIVE',note:'synthetic observation',draft:'synthetic draft'});
 assert.equal(s.person(id).relationship.revision,revision);
 s.run('UPDATE outcomes SET created_at=? WHERE analysis_id=?','2000-01-01T00:00:00.000Z',independent.id);
 expireHistory(s,'2020-01-01T00:00:00.000Z');
 assert.ok(s.analysis(independent.id));assert.equal(s.analysis(independent.id).outcome,null);
 assert.ok(s.person(id).relationship.revision>revision);
 }finally{s.close();}
});
test('nested outcome save rolls back with the enclosing correction',()=>{
 const s=openStore(':memory:');try{const id=s.createPerson({name:'synthetic',platform:'微信',stage:'初识'},randomUUID()),p=s.context(id),a=s.saveAnalysis(p,'synthetic','关心近况','x',localAnalysis('synthetic',p,'关心近况'),'local',null);
 const revision=s.person(id).relationship.revision;
 assert.throws(()=>s.tx(()=>{s.saveOutcome(a.id,{status:'POSITIVE',note:'synthetic',draft:'synthetic'});throw Error('synthetic rollback');}));
 assert.equal(s.analysis(a.id).outcome,null);assert.equal(s.person(id).relationship.revision,revision);
 }finally{s.close();}
});
test('live service is exclusive; abrupt process exit releases the lock; malformed legacy owner fails closed',()=>{
 const dir=mkdtempSync(join(tmpdir(),'lens-audit-lock-'));try{
 const release=lockDirectory(dir);assert.throws(()=>lockDirectory(dir));release();
 const child=spawnSync(process.execPath,['--input-type=module','-e',`import {lockDirectory} from ${JSON.stringify(new URL('../cloud-maintenance.mjs',import.meta.url).href)};lockDirectory(process.argv[1]);process.exit(0);`,dir]);assert.equal(child.status,0);
 lockDirectory(dir)();writeFileSync(join(dir,'.service.lock'),'unverifiable');assert.throws(()=>lockDirectory(dir),/verified/);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('expired backups are removed without a new backup and even if the next backup fails',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'lens-audit-prune-'));try{
 const now=Date.now(),old=join(dir,`cloud-${now-8*86400000}-${randomUUID()}.lensbackup`),fresh=join(dir,`cloud-${now}-${randomUUID()}.lensbackup`);
 writeFileSync(old,'synthetic');writeFileSync(fresh,'synthetic');assert.equal(pruneBackups(dir).removed,1);assert.ok(existsSync(fresh));
 writeFileSync(old,'synthetic');await assert.rejects(backupCloud(join(dir,'missing'),dir,Buffer.alloc(0)));assert.equal(existsSync(old),false);assert.ok(existsSync(fresh));
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('zero-call failures retry safely; paid failures need explicit acknowledgement and keep charges; DONE remains deduplicated',()=>{
 const auth=openCloudAuth(':memory:');try{
 const account=auth.invite().account_id,b=createBudget(auth,{verified:true,dailyCount:20,dailyMicros:10000000,monthlyMicros:100000000,inputPerMillion:1000000,outputPerMillion:1000000});
 const zero=randomUUID();b.reserve(zero,account,'zero');b.finish(zero,null,true);assert.equal(b.reserve(randomUUID(),account,'zero').existing,null);
 const paid=randomUUID();b.reserve(paid,account,'paid');b.hooks(paid).beforeCall();b.finish(paid,null,true);
 const original=auth.get('SELECT * FROM tasks WHERE id=?',paid);assert.equal(b.reserve(randomUUID(),account,'paid').existing.id,paid);
 const retry=randomUUID();assert.equal(b.reserve(retry,account,'paid',paid).existing,null);assert.deepEqual(auth.get('SELECT * FROM tasks WHERE id=?',paid),original);
 b.finish(retry,'synthetic-result');assert.equal(b.reserve(randomUUID(),account,'paid').existing.id,retry);
 }finally{auth.close();}
});
test('diagnostic records correlate failures without copying exception prose, credentials or stack',()=>{
 const lines=[];diagnose('request_failed','synthetic-id','analysis',Object.assign(Error('private text token API key'),{code:'ENOSPC'}),x=>lines.push(x));
 const result=JSON.parse(lines[0]);assert.equal(result.request_id,'synthetic-id');assert.equal(result.code,'ENOSPC');assert.ok(!/private|token|stack|API/.test(lines[0]));
});
