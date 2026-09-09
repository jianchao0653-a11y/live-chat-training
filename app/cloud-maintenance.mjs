import {DatabaseSync,backup} from 'node:sqlite';
import {openSync,closeSync,unlinkSync,mkdirSync,readFileSync,writeFileSync,readdirSync,statSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {randomBytes,randomUUID,createCipheriv,createDecipheriv} from 'node:crypto';
import {openCloudAuth,uuid} from './cloud-auth.mjs';
import {openStore} from './store.mjs';
import {verifySnapshot} from './recovery.mjs';

// The same exclusive lock is held by the service and offline maintenance.
export function lockDirectory(directory) {
  mkdirSync(directory,{recursive:true,mode:0o700});const path=join(directory,'.service.lock');
  const fd=openSync(path,'wx',0o600);writeFileSync(fd,String(process.pid));
  return ()=>{closeSync(fd);unlinkSync(path);};
}
const seal=(plain,key)=>{const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv),data=Buffer.concat([cipher.update(plain),cipher.final()]);return Buffer.concat([Buffer.from('LENSBK01'),iv,cipher.getAuthTag(),data]);};
const unseal=(data,key)=>{if(data.length<36||data.subarray(0,8).toString()!=='LENSBK01')throw new Error('Invalid encrypted backup');const d=createDecipheriv('aes-256-gcm',key,data.subarray(8,20));d.setAuthTag(data.subarray(20,36));return Buffer.concat([d.update(data.subarray(36)),d.final()]);};
function readBounded(file,max=100_000_000){if(statSync(file).size>max)throw new Error('Backup input exceeds bound');return readFileSync(file);}
export async function backupCloud(directory,backupDirectory,key,clock=Date.now) {
  if(key.length!==32)throw new Error('Backup key must contain 32 bytes');
  const root=resolve(directory),unlock=lockDirectory(root);let auth;
  try {
    if(!existsSync(join(root,'identity.sqlite')))throw new Error('Cloud identity does not exist');
    auth=openCloudAuth(join(root,'identity.sqlite'));const accounts=[];
    for(const row of auth.all('SELECT id FROM accounts WHERE disabled=0')) {
      if(!uuid(row.id))throw new Error('Invalid account ID');
      const file=join(root,'accounts',row.id+'.sqlite');
      if(existsSync(file))accounts.push({id:row.id,data:readBounded(file,20_000_000).toString('base64')});
    }
    const value={version:1,created:clock(),deletion_seq:auth.get('SELECT COALESCE(MAX(seq),0) n FROM deletions').n,accounts};
    const raw=Buffer.from(JSON.stringify(value));if(raw.length>90_000_000)throw new Error('Pilot backup size exceeded');
    const out=resolve(backupDirectory);mkdirSync(out,{recursive:true,mode:0o700});
    const destination=join(out,`cloud-${clock()}-${randomUUID()}.lensbackup`);writeFileSync(destination,seal(raw,key),{flag:'wx',mode:0o600});
    for(const name of readdirSync(out))if(/^cloud-\d+-[a-f0-9-]+\.lensbackup$/.test(name)&&statSync(join(out,name)).mtimeMs<clock()-7*86400000)unlinkSync(join(out,name));
    return {destination,accounts:accounts.length,encrypted:true,identityIncluded:false};
  }finally{auth?.close();unlock();}
}
export async function restoreCloud(backupFile,key,currentDirectory,destination) {
  // Never roll back identity, spend ledger or deletion journal to a historical snapshot.
  const current=resolve(currentDirectory),target=resolve(destination);
  if(existsSync(target))throw new Error('Restore target must be a new directory');
  if(!existsSync(join(current,'identity.sqlite')))throw new Error('Current identity/deletion journal is required; historical-only restore is forbidden');
  const unlock=lockDirectory(current);let auth;
  try {
    const data=JSON.parse(unseal(readBounded(backupFile),key).toString('utf8'));
    if(data.version!==1||!Array.isArray(data.accounts)||data.accounts.length>100||!Number.isSafeInteger(data.deletion_seq)||!Number.isSafeInteger(data.created))throw new Error('Invalid backup manifest');
    if(new Set(data.accounts.map(a=>a.id)).size!==data.accounts.length)throw new Error('Duplicate backup accounts');
    auth=openCloudAuth(join(current,'identity.sqlite'));
    const latest=auth.get('SELECT COALESCE(MAX(seq),0) n FROM deletions').n;
    if(latest<data.deletion_seq)throw new Error('Deletion journal is older than backup');
    for(const a of data.accounts)if(!uuid(a.id)||typeof a.data!=='string'||a.data.length>28_000_000||!/^[A-Za-z0-9+/=]+$/.test(a.data))throw new Error('Invalid account snapshot');
    mkdirSync(join(target,'accounts'),{recursive:true,mode:0o700});
    // Failed restores remain quarantined: service refuses a directory containing this marker.
    writeFileSync(join(target,'.restore-incomplete'),'Restore must finish before serving',{flag:'wx'});
    await backup(auth.db,join(target,'identity.sqlite'));
    const restored=openCloudAuth(join(target,'identity.sqlite'));let discarded=0;
    try {
      restored.run('UPDATE sessions SET revoked=1');restored.run('UPDATE invites SET used=1');
      for(const a of data.accounts) {
        if(!auth.get('SELECT id FROM accounts WHERE id=? AND disabled=0',a.id))continue;
        const file=join(target,'accounts',a.id+'.sqlite');writeFileSync(file,Buffer.from(a.data,'base64'),{flag:'wx',mode:0o600});
        verifySnapshot(file);
        const s=openStore(file);
        try {
          // Conservative replay: an edited/deleted person's old snapshot is wholly removed.
          for(const d of auth.all('SELECT DISTINCT person FROM deletions WHERE account=? AND seq>?',a.id,data.deletion_seq)){
            if(d.person==='@streamer'){
              s.run("UPDATE streamers SET name='待设置主播',tone='',phrases='',emojis='',boundary='',goal='',tags='',input_layout='SYSTEM',revision=revision+1");
              s.run('DELETE FROM analyses');
              s.run('DELETE FROM context_events');
            }else{s.deletePerson(d.person);discarded++;}
          }
          s.run('DELETE FROM analyses WHERE created_at<?',new Date(Date.now()-30*86400000).toISOString());
        }finally{s.close();}
      }
    }finally{restored.close();}
    unlinkSync(join(target,'.restore-incomplete'));
    return {destination:target,discarded_person_snapshots:discarded,sessionsRevoked:true,budgetRolledBack:false};
  }finally{auth?.close();unlock();}
}
