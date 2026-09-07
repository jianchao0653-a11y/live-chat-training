import {DatabaseSync} from 'node:sqlite';
import {copyFileSync,constants,lstatSync,unlinkSync} from 'node:fs';
import {resolve} from 'node:path';

export function verifySnapshot(path) {
  if(!lstatSync(path).isFile()||lstatSync(path).isSymbolicLink())throw new Error('Snapshot must be a regular file');
  const db=new DatabaseSync(path,{readOnly:true});
  try {
    const integrity=db.prepare('PRAGMA integrity_check').all();
    if(integrity.length!==1||integrity[0].integrity_check!=='ok')throw new Error('SQLite integrity check failed');
    if(db.prepare('PRAGMA foreign_key_check').all().length)throw new Error('SQLite foreign key check failed');
    for(const table of ['people','pairs','streamers','analyses','claims','outcomes','settings']) {
      if(!db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?").get(table))throw new Error('Not a current Conversation Lens snapshot');
    }
    return {integrity:'ok',schemaVersion:db.prepare('PRAGMA user_version').get().user_version};
  } finally {db.close();}
}

// Restores only to a new destination. Activation is an independent operator step.
export function restoreToNewFile(source,destination) {
  source=resolve(source);destination=resolve(destination);
  if(source===destination)throw new Error('Restore requires a new destination');
  verifySnapshot(source);
  copyFileSync(source,destination,constants.COPYFILE_EXCL);
  try {return {...verifySnapshot(destination),destination,activated:false};}
  catch(error){unlinkSync(destination);throw error;}
}
