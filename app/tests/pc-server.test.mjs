import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,writeFileSync,readFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {startPc} from '../pc-server.mjs';

test('PC service is loopback-only, ignores stale stop requests, drains and preserves accounts',async t=>{
  const directory=mkdtempSync(join(tmpdir(),'lens-pc-synthetic-'));let service;
  t.after(async()=>{await service?.close();rmSync(directory,{recursive:true,force:true});});
  service=await startPc({directory,port:0});
  assert.equal(service.app.server.address().address,'127.0.0.1');
  const account=service.app.auth.invite().account_id;
  const state=JSON.parse(readFileSync(join(directory,'service.json'),'utf8'));
  assert.equal(state.status,'running');
  writeFileSync(join(directory,'stop.json'),JSON.stringify({instance:'previous-instance'}));await delay(650);
  assert(service.app.server.listening);
  writeFileSync(join(directory,'stop.json'),JSON.stringify({instance:service.instance}));
  for(let i=0;i<30&&JSON.parse(readFileSync(join(directory,'service.json'),'utf8')).status!=='stopped';i++)await delay(100);
  assert.equal(JSON.parse(readFileSync(join(directory,'service.json'),'utf8')).status,'stopped');
  assert(!existsSync(join(directory,'data','.service.lock')));
  service=await startPc({directory,port:0});assert.equal(service.app.auth.get('SELECT id FROM accounts WHERE id=?',account).id,account);
  await Promise.all([service.close(),service.close()]);
});
