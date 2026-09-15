import {randomUUID} from 'node:crypto';
import {digest,uuid,fail} from './cloud-auth.mjs';

// The operation receipt and customer share the account DB transaction. No names
// or notes are retained in the receipt; deletion must never make retry resurrect it.
export function createCustomer(store,value,operationId) {
  if(operationId!==undefined&&!uuid(operationId))fail(400,'新增操作编号无效。');
  return store.tx(()=>{
    const key=operationId && `customer-create:${operationId}`;
    const fingerprint=digest(JSON.stringify(value));
    const previous=key && store.get('SELECT value FROM settings WHERE key=?',key);
    if(previous){
      const receipt=JSON.parse(previous.value);
      if(receipt.fingerprint!==fingerprint)fail(409,'该新增操作已提交其他内容，请先刷新列表核对。');
      const person=store.person(receipt.id);
      if(!person)fail(409,'该操作对应的客户已删除，请刷新列表；不会重新创建。');
      return person;
    }
    if(store.get('SELECT COUNT(*) n FROM people').n>=100)fail(409,'试用版最多保存 100 位人物。');
    if(key && store.get("SELECT COUNT(*) n FROM settings WHERE key LIKE 'customer-create:%'").n>=10000)
      fail(409,'新增操作记录已达试用上限，请联系维护者。');
    const id=store.createPerson(value,randomUUID());
    if(key)store.run('INSERT INTO settings(key,value) VALUES(?,?)',key,JSON.stringify({id,fingerprint}));
    return store.person(id);
  });
}
