import {DatabaseSync} from 'node:sqlite';
import {copyFileSync,constants,lstatSync,unlinkSync} from 'node:fs';
import {resolve} from 'node:path';
import {openStore} from './store.mjs';

const schemaOf = db => db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name != 'sqlite_sequence' ORDER BY type,name").all();
let expected;
function currentSchema() {
  if (!expected) {
    const store = openStore(':memory:');
    try { expected = {version:store.get('PRAGMA user_version').user_version, schema:JSON.stringify(schemaOf(store.db))}; }
    finally {store.close();}
  }
  return expected;
}

export function verifySnapshot(path) {
  if(!lstatSync(path).isFile()||lstatSync(path).isSymbolicLink())throw new Error('Snapshot must be a regular file');
  const db=new DatabaseSync(path,{readOnly:true});
  try {
    db.exec('PRAGMA trusted_schema=OFF');
    const expected=currentSchema(),schemaVersion=db.prepare('PRAGMA user_version').get().user_version;
    // Strict current-version restore: no migrations, added triggers or altered constraints.
    if(schemaVersion!==expected.version || JSON.stringify(schemaOf(db))!==expected.schema)throw new Error('Not a current Conversation Lens snapshot schema');
    const integrity=db.prepare('PRAGMA integrity_check').all();
    if(integrity.length!==1||integrity[0].integrity_check!=='ok')throw new Error('SQLite integrity check failed');
    if(db.prepare('PRAGMA foreign_key_check').all().length)throw new Error('SQLite foreign key check failed');
    return {integrity:'ok',schemaVersion};
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
