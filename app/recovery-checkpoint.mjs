// Portable encrypted FULL snapshot. Import stays quarantined until an operator
// establishes an authoritative current ledger; a checksum never proves freshness.
import {DatabaseSync,backup} from 'node:sqlite';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,lstatSync,existsSync,unlinkSync,rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {lockDirectory,seal,unseal} from './cloud-maintenance.mjs';
import {openCloudAuth,uuid} from './cloud-auth.mjs';
import {verifySnapshot} from './recovery.mjs';
import {openStore} from './store.mjs';
import {expireHistory} from './retention.mjs';

const hash=data=>createHash('sha256').update(data).digest('hex');
const schema=db=>JSON.stringify(db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name!='sqlite_sequence' ORDER BY type,name").all());
function bounded(path,max){const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.size>max)throw Error('Checkpoint requires bounded regular files');return readFileSync(path);}
function checkIdentity(file){
  const expected=openCloudAuth(':memory:'),db=new DatabaseSync(file,{readOnly:true});
  try{
    db.exec('PRAGMA trusted_schema=OFF');
    if(schema(db)!==schema(expected.db))throw Error('Unsupported identity schema');
    const integrity=db.prepare('PRAGMA integrity_check').all();
    if(integrity.length!==1||integrity[0].integrity_check!=='ok'||db.prepare('PRAGMA foreign_key_check').all().length)throw Error('Identity integrity failed');
  }finally{db.close();expected.close();}
}
async function snapshot(file){
  const temporary=mkdtempSync(join(tmpdir(),'lens-checkpoint-')),out=join(temporary,'snapshot.sqlite');
  const db=new DatabaseSync(file,{readOnly:true});
  try{await backup(db,out);return bounded(out,30_000_000);}
  finally{db.close();if(existsSync(out))unlinkSync(out);rmdirSync(temporary);}
}
export async function exportCheckpoint(directory,destination,key,clock=Date.now){
  if(!Buffer.isBuffer(key)||key.length!==32)throw Error('A separately escrowed 32-byte recovery key is required');
  const root=resolve(directory),out=resolve(destination);
  if(existsSync(out))throw Error('Checkpoint destination already exists');
  if(existsSync(join(root,'.restore-incomplete')))throw Error('Cannot export a quarantined directory');
  const unlock=lockDirectory(root);let auth;
  try{
    const identity=join(root,'identity.sqlite');bounded(identity,30_000_000);checkIdentity(identity);
    auth=openCloudAuth(identity);const accounts=[];
    for(const row of auth.all('SELECT id FROM accounts WHERE disabled=0')){
      if(!uuid(row.id))throw Error('Invalid account identity');
      const file=join(root,'accounts',row.id+'.sqlite');
      if(existsSync(file)){verifySnapshot(file,{allowLegacy:true});accounts.push({id:row.id,data:(await snapshot(file)).toString('base64')});}
    }
    if(accounts.length>100)throw Error('Pilot checkpoint account limit exceeded');
    const manifest={format:'lens-full-checkpoint-v1',id:randomUUID(),created:clock(),identity:(await snapshot(identity)).toString('base64'),accounts};
    const plain=Buffer.from(JSON.stringify(manifest));if(plain.length>90_000_000)throw Error('Pilot checkpoint size exceeded');
    const encrypted=seal(plain,key);writeFileSync(out,encrypted,{flag:'wx',mode:0o600});
    return {destination:out,checkpoint_id:manifest.id,sha256:hash(encrypted),created:manifest.created,accounts:accounts.length,identityIncluded:true,encrypted:true,freshnessProven:false};
  }finally{auth?.close();unlock();}
}
export async function importCheckpoint(file,destination,key,expectedSha256){
  if(!Buffer.isBuffer(key)||key.length!==32||!/^[a-f0-9]{64}$/.test(expectedSha256||''))throw Error('Recovery key and independently retained checksum required');
  const target=resolve(destination);if(existsSync(target))throw Error('Recovery target must be a new directory');
  const encrypted=bounded(file,100_000_000);if(hash(encrypted)!==expectedSha256)throw Error('Checkpoint checksum mismatch');
  const data=JSON.parse(unseal(encrypted,key).toString('utf8'));
  if(data.format!=='lens-full-checkpoint-v1'||!uuid(data.id)||!Number.isSafeInteger(data.created)||!Array.isArray(data.accounts)||data.accounts.length>100)throw Error('Invalid full checkpoint manifest');
  const decode=value=>{if(typeof value!=='string'||value.length>40_000_000||!/^[A-Za-z0-9+/]+={0,2}$/.test(value))throw Error('Invalid snapshot encoding');return Buffer.from(value,'base64');};
  const identity=decode(data.identity);const ids=new Set();
  for(const a of data.accounts){if(!uuid(a.id)||ids.has(a.id))throw Error('Invalid or duplicate account');ids.add(a.id);decode(a.data);}
  mkdirSync(target,{recursive:true,mode:0o700});
  writeFileSync(join(target,'.restore-incomplete'),'FULL CHECKPOINT: latest ledger and source fencing require independent verification. Do not serve.',{flag:'wx',mode:0o600});
  writeFileSync(join(target,'identity.sqlite'),identity,{flag:'wx',mode:0o600});checkIdentity(join(target,'identity.sqlite'));
  const auth=openCloudAuth(join(target,'identity.sqlite'));
  try{
    auth.run('UPDATE sessions SET revoked=1');auth.run('UPDATE invites SET used=1');
    mkdirSync(join(target,'accounts'),{mode:0o700});
    for(const a of data.accounts){
      if(!auth.get('SELECT id FROM accounts WHERE id=? AND disabled=0',a.id))throw Error('Account snapshot is not active in checkpoint identity');
      const path=join(target,'accounts',a.id+'.sqlite');writeFileSync(path,decode(a.data),{flag:'wx',mode:0o600});verifySnapshot(path,{allowLegacy:true});
      const store=openStore(path);try{verifySnapshot(path);expireHistory(store,new Date(Date.now()-30*86400000).toISOString());}finally{store.close();}
    }
  }finally{auth.close();}
  return {destination:target,checkpoint_id:data.id,sha256:expectedSha256,identityIncluded:true,sessionsRevoked:true,quarantined:true,activationAllowed:false,freshnessProven:false};
}
