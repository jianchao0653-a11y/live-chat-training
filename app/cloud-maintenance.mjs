import {DatabaseSync,backup} from 'node:sqlite';
import {unlinkSync,mkdirSync,readFileSync,writeFileSync,readdirSync,statSync,lstatSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {randomBytes,randomUUID,createCipheriv,createDecipheriv} from 'node:crypto';
import {openCloudAuth,uuid} from './cloud-auth.mjs';
import {openStore,customerSegments} from './store.mjs';
import {verifySnapshot} from './recovery.mjs';
import {expireHistory} from './retention.mjs';

// The same exclusive lock is held by the service and offline maintenance.
export function lockDirectory(directory) {
  mkdirSync(directory,{recursive:true,mode:0o700});const path=join(directory,'.service.lock');
  const lock=new DatabaseSync(join(directory,'.service-lock.sqlite'),{timeout:0});
  try{
    lock.exec('PRAGMA journal_mode=DELETE; CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY); BEGIN EXCLUSIVE');
    // Compatibility with an older running server. PID reuse fails closed.
    if(existsSync(path)){
      const raw=readFileSync(path,'utf8').trim(),pid=Number(raw);
      if(!/^\d+$/.test(raw)||!Number.isSafeInteger(pid)||pid<=0)throw new Error('Legacy lock owner cannot be verified');
      try{process.kill(pid,0);throw new Error('Legacy service still running');}catch(e){if(e.code!=='ESRCH')throw e;}
      unlinkSync(path);
    }
    writeFileSync(path,String(process.pid),{flag:'wx',mode:0o600});
    let closed=false;return ()=>{if(!closed){closed=true;try{if(readFileSync(path,'utf8')===String(process.pid))unlinkSync(path);}finally{lock.exec('ROLLBACK');lock.close();}}};
  }catch(e){lock.close();throw e;}
}
export function pruneBackups(directory,clock=Date.now){
  if(!existsSync(directory))return {removed:0};if(lstatSync(directory).isSymbolicLink())throw new Error('Backup directory must not be a link');let removed=0;
  for(const name of readdirSync(directory)){
    const m=/^cloud-(\d+)-[a-f0-9-]+\.lensbackup$/.exec(name);if(!m)continue;
    const path=join(directory,name);
    try{const stat=lstatSync(path);if(!stat.isSymbolicLink()&&stat.isFile()&&Math.min(Number(m[1]),stat.mtimeMs)<clock()-7*86400000){unlinkSync(path);removed++;}}catch(e){if(e.code!=='ENOENT')throw e;}
  }
  return {removed};
}
export const seal=(plain,key)=>{const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv),data=Buffer.concat([cipher.update(plain),cipher.final()]);return Buffer.concat([Buffer.from('LENSBK01'),iv,cipher.getAuthTag(),data]);};
export const unseal=(data,key)=>{if(data.length<36||data.subarray(0,8).toString()!=='LENSBK01')throw new Error('Invalid encrypted backup');const d=createDecipheriv('aes-256-gcm',key,data.subarray(8,20));d.setAuthTag(data.subarray(20,36));return Buffer.concat([d.update(data.subarray(36)),d.final()]);};
function readBounded(file,max=100_000_000){if(statSync(file).size>max)throw new Error('Backup input exceeds bound');return readFileSync(file);}
export async function backupCloud(directory,backupDirectory,key,clock=Date.now) {
  pruneBackups(resolve(backupDirectory),clock);
  if(key.length!==32)throw new Error('Backup key must contain 32 bytes');
  const root=resolve(directory),unlock=lockDirectory(root);let auth;
  try {
    if(!existsSync(join(root,'identity.sqlite')))throw new Error('Cloud identity does not exist');
    auth=openCloudAuth(join(root,'identity.sqlite'));const accounts=[];
    for(const row of auth.all('SELECT id FROM accounts WHERE disabled=0')) {
      if(!uuid(row.id))throw new Error('Invalid account ID');
      const file=join(root,'accounts',row.id+'.sqlite');
      if(existsSync(file)){verifySnapshot(file,{allowLegacy:true});accounts.push({id:row.id,data:readBounded(file,20_000_000).toString('base64')});}
    }
    const value={version:1,created:clock(),deletion_seq:auth.get('SELECT COALESCE(MAX(seq),0) n FROM deletions').n,
      customer_change_seq:auth.get('SELECT COALESCE(MAX(seq),0) n FROM customer_changes').n,accounts};
    const raw=Buffer.from(JSON.stringify(value));if(raw.length>90_000_000)throw new Error('Pilot backup size exceeded');
    const out=resolve(backupDirectory);mkdirSync(out,{recursive:true,mode:0o700});
    const destination=join(out,`cloud-${clock()}-${randomUUID()}.lensbackup`);writeFileSync(destination,seal(raw,key),{flag:'wx',mode:0o600});
    pruneBackups(out,clock);
    return {destination,accounts:accounts.length,encrypted:true,identityIncluded:false};
  }finally{auth?.close();unlock();}
}
export async function restoreCloud(backupFile,key,currentDirectory,destination) {
  // Never roll back identity, spend ledger or deletion journal to a historical snapshot.
  const current=resolve(currentDirectory),target=resolve(destination);
  if(existsSync(join(current,'.restore-incomplete')))throw new Error('Quarantined identity is not an authoritative current ledger');
  if(existsSync(target))throw new Error('Restore target must be a new directory');
  if(!existsSync(join(current,'identity.sqlite')))throw new Error('Current identity/deletion journal is required; historical-only restore is forbidden');
  const unlock=lockDirectory(current);let auth;
  try {
    const data=JSON.parse(unseal(readBounded(backupFile),key).toString('utf8'));
    if(data.version!==1||!Array.isArray(data.accounts)||data.accounts.length>100||!Number.isSafeInteger(data.deletion_seq)||!Number.isSafeInteger(data.created))throw new Error('Invalid backup manifest');
    const customerChangeSeq=data.customer_change_seq??0;
    if(!Number.isSafeInteger(customerChangeSeq)||customerChangeSeq<0)throw new Error('Invalid customer change sequence');
    if(new Set(data.accounts.map(a=>a.id)).size!==data.accounts.length)throw new Error('Duplicate backup accounts');
    auth=openCloudAuth(join(current,'identity.sqlite'));
    const latest=auth.get('SELECT COALESCE(MAX(seq),0) n FROM deletions').n;
    if(latest<data.deletion_seq)throw new Error('Deletion journal is older than backup');
    if(auth.get('SELECT COALESCE(MAX(seq),0) n FROM customer_changes').n<customerChangeSeq)throw new Error('Customer change journal is older than backup');
    for(const a of data.accounts)if(!uuid(a.id)||typeof a.data!=='string'||a.data.length>28_000_000||!/^[A-Za-z0-9+/=]+$/.test(a.data))throw new Error('Invalid account snapshot');
    mkdirSync(join(target,'accounts'),{recursive:true,mode:0o700});
    // Failed restores remain quarantined: service refuses a directory containing this marker.
    writeFileSync(join(target,'.restore-incomplete'),'Restore must finish before serving',{flag:'wx'});
    await backup(auth.db,join(target,'identity.sqlite'));
    const restored=openCloudAuth(join(target,'identity.sqlite'));let discarded=0,replayedCustomerChanges=0;
    try {
      restored.run('UPDATE sessions SET revoked=1');restored.run('UPDATE invites SET used=1');
      for(const a of data.accounts) {
        if(!auth.get('SELECT id FROM accounts WHERE id=? AND disabled=0',a.id))continue;
        const file=join(target,'accounts',a.id+'.sqlite');writeFileSync(file,Buffer.from(a.data,'base64'),{flag:'wx',mode:0o600});
        verifySnapshot(file,{allowLegacy:true});
        const s=openStore(file);
        try {
          verifySnapshot(file);
          // Conservative replay: an edited/deleted person's old snapshot is wholly removed.
          for(const d of auth.all('SELECT DISTINCT person FROM deletions WHERE account=? AND seq>?',a.id,data.deletion_seq)){
            if(d.person==='@streamer'){
              s.run("UPDATE streamers SET name='待设置主播',tone='',phrases='',emojis='',boundary='',goal='',tags='',input_layout='SYSTEM',revision=revision+1");
              s.run('DELETE FROM analyses');
              s.run('DELETE FROM context_events');
            }else{s.deletePerson(d.person);discarded++;}
          }
          // Deletions win: classification replay never recreates a discarded customer.
          for(const change of auth.all('SELECT person,segment FROM customer_changes WHERE account=? AND seq>? ORDER BY seq',a.id,customerChangeSeq)){
            if(!uuid(change.person)||!customerSegments.includes(change.segment))throw new Error('Invalid customer change journal');
            if(s.pair(change.person,'0001') && s.setCustomerSegment(change.person,'0001',change.segment).changed)replayedCustomerChanges++;
          }
          expireHistory(s,new Date(Date.now()-30*86400000).toISOString());
        }finally{s.close();}
      }
    }finally{restored.close();}
    unlinkSync(join(target,'.restore-incomplete'));
    return {destination:target,discarded_person_snapshots:discarded,replayed_customer_changes:replayedCustomerChanges,sessionsRevoked:true,budgetRolledBack:false};
  }finally{auth?.close();unlock();}
}
