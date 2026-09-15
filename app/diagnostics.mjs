import {randomUUID} from 'node:crypto';
export const requestId=()=>randomUUID();
export function diagnose(event,id,stage,error,sink=console.error){
  const allowed=new Set(['SQLITE_BUSY','ERR_SQLITE_ERROR','ECONNRESET','ECONNREFUSED','ETIMEDOUT','ENOSPC','EACCES','EPERM']);
  const record={event,request_id:id,stage,status:Number.isInteger(error?.status)?error.status:500,code:allowed.has(error?.code)?error.code:'OPERATION_FAILED'};
  sink(JSON.stringify(record));return record;
}
