import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {openStore} from '../store.mjs';
import {verifySnapshot,restoreToNewFile} from '../recovery.mjs';
import {DatabaseSync} from 'node:sqlite';

test('known v1 snapshots migrate only the destination; extra legacy triggers stay rejected',()=>{
 const dir=mkdtempSync(join(tmpdir(),'lens-recovery-v1-'));try{
 const source=join(dir,'v1.sqlite'),s=openStore(':memory:',{legacySchema:true});
 s.db.exec(`VACUUM INTO '${source.replaceAll("'","''")}'`);s.close();
 const original=readFileSync(source);assert.equal(verifySnapshot(source,{allowLegacy:true}).schemaVersion,1);
 assert.equal(restoreToNewFile(source,join(dir,'v2.sqlite')).schemaVersion,3);assert.deepEqual(readFileSync(source),original);
 const db=new DatabaseSync(source);db.exec('CREATE TRIGGER injected AFTER INSERT ON people BEGIN DELETE FROM claims; END');db.close();
 assert.throws(()=>restoreToNewFile(source,join(dir,'malicious-copy.sqlite')),/schema/i);
 assert.equal(readFileSync(join(dir,'v2.sqlite')).length>0,true);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('recovery rejects table-name impostors, incompatible versions and modified schema without copying',()=>{
  const dir=mkdtempSync(join(tmpdir(),'lens-recovery-schema-'));
  try {
    const fake=join(dir,'fake.sqlite'),db=new DatabaseSync(fake);
    for(const table of ['people','pairs','streamers','analyses','claims','outcomes','settings'])db.exec(`CREATE TABLE ${table}(fake TEXT)`);
    db.close();assert.throws(()=>verifySnapshot(fake),/snapshot|schema/i);
    for(const [name,change] of [
      ['version','PRAGMA user_version=999'],
      ['column','ALTER TABLE people ADD COLUMN unexpected TEXT'],
      ['trigger',"CREATE TRIGGER injected AFTER INSERT ON people BEGIN DELETE FROM claims; END"],
      ['missing','DROP TABLE beliefs'],
    ]) {
      const path=join(dir,name+'.sqlite');const store=openStore(path);store.db.exec(change);store.close();
      assert.throws(()=>restoreToNewFile(path,join(dir,name+'-copy.sqlite')),/snapshot|schema/i);
    }
  } finally {rmSync(dir,{recursive:true,force:true});}
});
test('recovery validates an isolated snapshot and refuses overwrite or invalid input',()=>{
  const dir=mkdtempSync(join(tmpdir(),'lens-recovery-'));
  try {
    const source=join(dir,'synthetic.sqlite'),destination=join(dir,'restored.sqlite');
    const store=openStore(source);const id=store.createPerson({name:'合成恢复人物',platform:'视频号',stage:'初识',streamer_id:'0001',notes:'',boundary:''});store.close();
    const original=readFileSync(source);
    assert.equal(verifySnapshot(source).integrity,'ok');
    assert.equal(restoreToNewFile(source,destination).activated,false);
    const restored=openStore(destination);assert.equal(restored.person(id).name,'合成恢复人物');restored.close();
    assert.throws(()=>restoreToNewFile(source,destination));
    assert.throws(()=>restoreToNewFile(source,source));
    const bad=join(dir,'bad.sqlite');writeFileSync(bad,'not sqlite');assert.throws(()=>verifySnapshot(bad));
    assert.deepEqual(readFileSync(source),original);
  } finally {rmSync(dir,{recursive:true,force:true});}
});
