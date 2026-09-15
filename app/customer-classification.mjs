import {resolve,dirname,join} from 'node:path';
import {customerSegments} from './store.mjs';
import {fail,uuid} from './cloud-auth.mjs';

const rollbackModes=new Set(['delete','truncate','persist']);
const attached='customer_classification';
const mainFile=db=>db.prepare('PRAGMA database_list').all().find(row=>row.name==='main')?.file;
function durableRollback(db,schema) {
  const mode=db.prepare(`PRAGMA ${schema}.journal_mode`).get().journal_mode;
  const synchronous=db.prepare(`PRAGMA ${schema}.synchronous`).get().synchronous;
  if(!rollbackModes.has(mode)||synchronous<2)
    fail(503,'客户分类暂时无法可靠保存，请联系维护者检查数据库设置。');
}

// A single connection and rollback-journal transaction commit both database files.
// Reject WAL, memory-only and relaxed durability modes instead of claiming atomicity.
// SQLite lang_attach.html and atomiccommit.html sections 5.2/5.5, read 2026-09-10.
export function setCloudCustomerSegment(auth,store,account,personId,segment,clock=Date.now) {
  if(!uuid(account)||!uuid(personId))fail(404,'人物不存在。');
  if(!customerSegments.includes(segment))fail(400,'请选择有效选项。');
  const identity=mainFile(auth.db),customer=mainFile(store.db);
  if(!identity||!customer||resolve(customer)!==resolve(join(dirname(identity),'accounts',account+'.sqlite')))
    fail(503,'客户分类暂时无法可靠保存，请联系维护者检查数据库设置。');
  durableRollback(auth.db,'main');durableRollback(store.db,'main');
  auth.db.prepare(`ATTACH DATABASE ? AS ${attached}`).run(customer);
  try {
    durableRollback(auth.db,attached);
    const changed=auth.tx(()=>{
      const pair=auth.get(`SELECT id,segment FROM ${attached}.pairs WHERE person_id=? AND streamer_id='0001'`,personId);
      if(!pair)fail(404,'人物不存在。');
      if(pair.segment===segment)return false;
      auth.run(`UPDATE ${attached}.pairs SET segment=?,revision=revision+1 WHERE id=?`,segment,pair.id);
      auth.run('INSERT INTO customer_changes(account,person,segment,created) VALUES(?,?,?,?)',account,personId,segment,clock());
      return true;
    });
    return {changed,person:store.person(personId,'0001')};
  }finally{auth.db.exec(`DETACH DATABASE ${attached}`);}
}
