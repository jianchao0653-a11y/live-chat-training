// Explicit paths only: never discovers a running database, credential or key.
import {readFileSync,lstatSync} from 'node:fs';
import {exportCheckpoint,importCheckpoint} from '../../app/recovery-checkpoint.mjs';
const [action,source,target,keyFile,checksum,...extra]=process.argv.slice(2);
if(!['export','import'].includes(action)||!source||!target||!keyFile||extra.length||(action==='import'&&!checksum)||(action==='export'&&checksum)){
  console.error('Usage: node native/scripts/recovery_checkpoint.mjs export SOURCE_DIRECTORY NEW_FILE KEY_FILE\n       node native/scripts/recovery_checkpoint.mjs import BACKUP_FILE NEW_DIRECTORY KEY_FILE SHA256');process.exit(2);
}
try{
  const stat=lstatSync(keyFile);if(!stat.isFile()||stat.isSymbolicLink()||stat.size!==32)throw Error('Invalid key');
  const key=readFileSync(keyFile);
  try{console.log(JSON.stringify(action==='export'?await exportCheckpoint(source,target,key):await importCheckpoint(source,target,key,checksum)));}
  finally{key.fill(0);}
}catch{console.error('Recovery operation refused. Check explicit paths, stopped-service lock, key, checksum and supported schema. Any imported directory remains quarantined. No data or key is printed.');process.exitCode=1;}
