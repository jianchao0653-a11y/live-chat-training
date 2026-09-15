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
const legacy=new Map();
function legacySchema(version){
  if(!legacy.has(version)){const s=openStore(':memory:',{legacyVersion:version});try{legacy.set(version,JSON.stringify(schemaOf(s.db)));}finally{s.close();}}
  return legacy.get(version);
}

export function verifySnapshot(path,{allowLegacy=false}={}) {
  if(!lstatSync(path).isFile()||lstatSync(path).isSymbolicLink())throw new Error('Snapshot must be a regular file');
  const db=new DatabaseSync(path,{readOnly:true});
  try {
    db.exec('PRAGMA trusted_schema=OFF');
    const expected=currentSchema(),schemaVersion=db.prepare('PRAGMA user_version').get().user_version;
    // Strict current-version restore: no migrations, added triggers or altered constraints.
    const schema=JSON.stringify(schemaOf(db));
    if(!((schemaVersion===expected.version&&schema===expected.schema)||(allowLegacy&&[1,2].includes(schemaVersion)&&schema===legacySchema(schemaVersion))))throw new Error('Not a current or supported Conversation Lens snapshot schema');
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
  verifySnapshot(source,{allowLegacy:true});
  copyFileSync(source,destination,constants.COPYFILE_EXCL);
  try {const s=openStore(destination);s.close();return {...verifySnapshot(destination),destination,activated:false};}
  catch(error){unlinkSync(destination);throw error;}
}
