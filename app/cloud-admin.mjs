import {readFileSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {openCloudAuth,uuid} from './cloud-auth.mjs';
import {backupCloud,restoreCloud} from './cloud-maintenance.mjs';
const [action,directory,...args]=process.argv.slice(2);
if(!directory||!['invite','revoke','backup','restore'].includes(action))throw new Error('Usage: cloud-admin.mjs invite|revoke|backup|restore CLOUD_DATA [arguments]');
const root=resolve(directory);
if(action==='invite'||action==='revoke') {
  const auth=openCloudAuth(join(root,'identity.sqlite'));
  try{
    if(action==='invite') {if(args[0]&&!uuid(args[0]))throw new Error('Invalid account ID');console.log(JSON.stringify(auth.invite(args[0])));}
    else{if(!uuid(args[0]))throw new Error('Invalid session ID');auth.revoke(args[0]);console.log('Device revoked');}
  }finally{auth.close();}
}else{
  const file=process.env.LENS_BACKUP_KEY_FILE;if(!file)throw new Error('LENS_BACKUP_KEY_FILE is required');
  const hex=readFileSync(file,'utf8').trim();if(!/^[a-f0-9]{64}$/i.test(hex))throw new Error('Invalid backup key file');const key=Buffer.from(hex,'hex');
  if(action==='backup'){if(!args[0])throw new Error('Backup directory required');console.log(JSON.stringify(await backupCloud(root,resolve(args[0]),key)));}
  else {if(!args[0]||!args[1])throw new Error('Encrypted backup and NEW destination required');console.log(JSON.stringify(await restoreCloud(resolve(args[0]),key,root,resolve(args[1]))));}
}
