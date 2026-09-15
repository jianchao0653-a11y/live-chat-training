import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,mkdirSync,readFileSync,writeFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {openCloudAuth} from '../cloud-auth.mjs';
import {openStore} from '../store.mjs';
import {exportCheckpoint,importCheckpoint} from '../recovery-checkpoint.mjs';
import {createCloud} from '../cloud.mjs';
import {restoreCloud,lockDirectory} from '../cloud-maintenance.mjs';

test('machine-loss full checkpoint retains ledger, encrypts data, revokes sessions and refuses unverified activation',async()=>{
 const root=mkdtempSync(join(tmpdir(),'lens-checkpoint-test-'));try{
  const source=join(root,'source');mkdirSync(source);mkdirSync(join(source,'accounts'));
  const auth=openCloudAuth(join(source,'identity.sqlite')),invite=auth.invite(),account=auth.activate(invite.invite,'synthetic'),id=randomUUID();
  auth.run('INSERT INTO deletions(account,person,entire,created) VALUES(?,?,1,?)',account.account_id,'deleted-synthetic',Date.now());
  auth.run("INSERT INTO control VALUES('synthetic-budget-total','1234')");auth.close();
  const store=openStore(join(source,'accounts',account.account_id+'.sqlite'));
  store.createPerson({name:'CHECKPOINT_SYNTHETIC_PRIVATE_TEXT',platform:'微信',stage:'初识'},id);store.close();
  const key=Buffer.alloc(32,17),file=join(root,'full.lensbackup');
  const unlock=lockDirectory(source);await assert.rejects(exportCheckpoint(source,file,key));unlock();
  const receipt=await exportCheckpoint(source,file,key);assert.equal(receipt.identityIncluded,true);assert.equal(receipt.freshnessProven,false);
  assert.ok(!readFileSync(file).includes(Buffer.from('CHECKPOINT_SYNTHETIC_PRIVATE_TEXT')));
  await assert.rejects(exportCheckpoint(source,file,key),/exists/);
  await assert.rejects(importCheckpoint(file,join(root,'bad-key'),Buffer.alloc(32,18),receipt.sha256));
  await assert.rejects(importCheckpoint(file,join(root,'bad-hash'),key,'0'.repeat(64)),/checksum/);
  // Remove only this test-owned synthetic source to model total original-disk loss.
  rmSync(source,{recursive:true,force:true});
  const target=join(root,'recovered'),result=await importCheckpoint(file,target,key,receipt.sha256);
  assert.equal(result.quarantined,true);assert.equal(result.activationAllowed,false);
  const recovered=openCloudAuth(join(target,'identity.sqlite'));
  assert.equal(recovered.get("SELECT value FROM control WHERE key='synthetic-budget-total'").value,'1234');
  assert.equal(recovered.get('SELECT COUNT(*) n FROM deletions').n,1);
  assert.throws(()=>recovered.authorize(account.token),e=>e.status===401);recovered.close();
  const restored=openStore(join(target,'accounts',account.account_id+'.sqlite'));assert.equal(restored.person(id).name,'CHECKPOINT_SYNTHETIC_PRIVATE_TEXT');restored.close();
  assert.ok(existsSync(join(target,'.restore-incomplete')));
  assert.throws(()=>createCloud({directory:target,apiKey:''}),/恢复/);
  await assert.rejects(restoreCloud(file,key,target,join(root,'laundered')),/Quarantined/);
  const tampered=Buffer.from(readFileSync(file));tampered[tampered.length-1]^=1;writeFileSync(join(root,'tampered'),tampered);
  await assert.rejects(importCheckpoint(join(root,'tampered'),join(root,'invalid'),key,receipt.sha256),/checksum/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
