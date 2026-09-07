import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {openStore} from '../store.mjs';
import {verifySnapshot,restoreToNewFile} from '../recovery.mjs';
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
