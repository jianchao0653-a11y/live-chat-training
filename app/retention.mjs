import {randomUUID} from 'node:crypto';

// Preserve independent recent records; invalidate only results that consumed removed observations.
export function invalidateDerived(store, ids) {
  const affected=new Set(ids);let changed=true,count=0;
  const rows=store.all('SELECT id,pair_id,result FROM analyses');
  while(changed){changed=false;for(const row of rows){
    if(affected.has(row.id))continue;
    const result=JSON.parse(row.result),receipt=result.context_receipt;
    const dependencies=[...(receipt?.outcome_ids||[]),...(receipt?.reviewed_belief_ids||[]),...(receipt?.strategy_outcome_ids||[])];
    // Old receipts omitted aggregate contributors; fail closed within the same pair.
    const legacyAggregate=receipt && !receipt.invalidated && !Array.isArray(receipt.strategy_outcome_ids)
      && rows.some(source=>affected.has(source.id)&&source.pair_id===row.pair_id);
    if(!legacyAggregate&&!dependencies.some(id=>affected.has(id)))continue;
    affected.add(row.id);changed=true;count++;
    store.run('UPDATE analyses SET result=?,fingerprint=? WHERE id=?',JSON.stringify({task_type:result.task_type||'REPLY',
      ...(result.task_type&&result.task_type!=='REPLY'?{materials:[],profile:{observations:[],unknowns:[]}}:{}),
      summary:'引用的历史资料已删除或到期，请重新分析。',route:'SAFE_STOP',strategy:'重新分析',risk:'旧建议已失效',reason:'历史资料变更',evidence:[],candidates:[],judge:{verdict:'BLOCK',source:'资料生命周期校验'},context_receipt:{invalidated:true}}),randomUUID(),row.id);
    store.run('DELETE FROM beliefs WHERE analysis_id=?',row.id);
    store.run("DELETE FROM context_events WHERE subject_id=? AND type='BELIEF_STATUS'",row.id);
    store.run('UPDATE pairs SET revision=revision+1 WHERE id=?',row.pair_id);
  }}
  return count;
}
export function expireHistory(store,cutoff){
  return store.tx(()=>{
    const old=store.all('SELECT id,pair_id FROM analyses WHERE created_at<?',cutoff);
    const expiredOutcomes=store.all('SELECT o.analysis_id id,a.pair_id FROM outcomes o JOIN analyses a ON a.id=o.analysis_id WHERE o.created_at<?',cutoff);
    const ids=[...new Set([...old,...expiredOutcomes].map(x=>x.id))];
    const invalidated=invalidateDerived(store,ids);
    for(const row of old){store.run('DELETE FROM analyses WHERE id=?',row.id);store.run('UPDATE pairs SET revision=revision+1 WHERE id=?',row.pair_id);}
    for(const row of expiredOutcomes){store.run("DELETE FROM context_events WHERE subject_id=? AND type='OUTCOME_RECORDED'",row.id);store.run('UPDATE pairs SET revision=revision+1 WHERE id=?',row.pair_id);}
    store.run('DELETE FROM outcomes WHERE created_at<?',cutoff);
    // Remove legacy orphan/expired events even after analyses have already been deleted.
    store.run("DELETE FROM context_events WHERE type IN ('OUTCOME_RECORDED','BELIEF_STATUS') AND (created_at<? OR subject_id NOT IN (SELECT id FROM analyses))",cutoff);
    // Audit ordering needs subject/status, never a second copy of private prose.
    store.run("UPDATE context_events SET payload='{}' WHERE type='OUTCOME_RECORDED'");
    return {expired:old.length,invalidated};
  });
}
