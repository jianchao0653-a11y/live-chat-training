import {DatabaseSync} from 'node:sqlite';
import {randomBytes,randomUUID,createHash} from 'node:crypto';
import {mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
export const fail=(status,message)=>{throw Object.assign(new Error(message),{status});};
export const digest=x=>createHash('sha256').update(x).digest('hex');
export const uuid=x=>typeof x==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(x);
export function openCloudAuth(file,clock=Date.now) {
  if(file!==':memory:')mkdirSync(dirname(file),{recursive:true,mode:0o700});
  const db=new DatabaseSync(file);
  db.exec(`PRAGMA foreign_keys=ON; PRAGMA secure_delete=ON; PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, created INTEGER NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL, account TEXT NOT NULL REFERENCES accounts(id), name TEXT NOT NULL, expires INTEGER NOT NULL, absolute_expires INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS attempts(bucket INTEGER PRIMARY KEY, count INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), fingerprint TEXT NOT NULL, created INTEGER NOT NULL, state TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0, usage TEXT NOT NULL DEFAULT '[]', analysis TEXT);
    CREATE INDEX IF NOT EXISTS task_account_date ON tasks(account,created);
    CREATE TABLE IF NOT EXISTS control(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS deletions(seq INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, person TEXT NOT NULL, entire INTEGER NOT NULL, created INTEGER NOT NULL);`);
  const get=(sql,...p)=>db.prepare(sql).get(...p),all=(sql,...p)=>db.prepare(sql).all(...p),run=(sql,...p)=>db.prepare(sql).run(...p);
  const tx=fn=>{db.exec('BEGIN IMMEDIATE');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}};
  const invite=(account)=>tx(()=>{
    const id=account||randomUUID();
    if(account&&!get('SELECT id FROM accounts WHERE id=? AND disabled=0',id))fail(404,'账号不存在或已停用。');
    if(!account)run('INSERT INTO accounts(id,created) VALUES(?,?)',id,clock());
    run('UPDATE invites SET used=1 WHERE account=?',id);
    const code=randomBytes(24).toString('base64url');
    run('INSERT INTO invites(hash,account,expires) VALUES(?,?,?)',digest(code),id,clock()+86400000);
    return {account_id:id,invite:code,expires_at:clock()+86400000};
  });
  const activate=(code,name)=>{
    // Persistent global rate limit; does not trust user-controlled proxy/IP headers.
    const bucket=Math.floor(clock()/60000);
    const count=tx(()=>{run('DELETE FROM attempts WHERE bucket<?',bucket-2);run('INSERT INTO attempts VALUES(?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1',bucket);return get('SELECT count FROM attempts WHERE bucket=?',bucket).count;});
    if(count>20)fail(429,'激活请求过多，请稍后再试。');
    if(typeof code!=='string'||!/^[A-Za-z0-9_-]{32}$/.test(code)||typeof name!=='string'||name.length>60)fail(400,'请输入有效邀请码。');
    return tx(()=>{
      const row=get('SELECT i.* FROM invites i JOIN accounts a ON a.id=i.account WHERE i.hash=? AND i.used=0 AND i.expires>? AND a.disabled=0',digest(code),clock());
      if(!row)fail(401,'邀请码无效或已使用，请联系发放者。');
      run('UPDATE invites SET used=1 WHERE hash=?',row.hash);
      run('UPDATE sessions SET revoked=1 WHERE account=?',row.account);
      const token=randomBytes(32).toString('base64url'),id=randomUUID(),expires=clock()+30*86400000;
      run('INSERT INTO sessions VALUES(?,?,?,?,?,?,0)',id,digest(token),row.account,name,expires,clock()+180*86400000);
      return {id,account_id:row.account,token,expires_at:expires};
    });
  };
  const authorize=token=>{
    if(typeof token!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(token))fail(401,'请先登录。');
    const d=get('SELECT s.* FROM sessions s JOIN accounts a ON a.id=s.account WHERE s.hash=? AND s.revoked=0 AND a.disabled=0 AND s.expires>? AND s.absolute_expires>?',digest(token),clock(),clock());
    if(!d)fail(401,'登录已失效，请重新激活登录。');
    const expires=Math.min(clock()+30*86400000,d.absolute_expires);
    if(expires-d.expires>3600000)run('UPDATE sessions SET expires=? WHERE id=?',expires,d.id);
    return {id:d.id,account_id:d.account,name:d.name,streamer_id:'0001',expires_at:expires};
  };
  return {db,get,all,run,tx,invite,activate,authorize,clock,
    revoke:id=>run('UPDATE sessions SET revoked=1 WHERE id=?',id),close:()=>db.close()};
}
