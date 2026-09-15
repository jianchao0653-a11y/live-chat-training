import {fail,uuid} from './cloud-auth.mjs';
class BudgetBlockedError extends Error {
  constructor(status,message,block) {super(message);this.status=status;this.budgetBlock=block;}
}
// Only expose details constructed here, never arbitrary provider/error properties.
export const budgetErrorDetails=error=>error instanceof BudgetBlockedError?{budget_block:error.budgetBlock}:{};
const beijingTime=instant=>new Date(instant+8*3600000).toISOString().slice(0,16).replace('T',' ')+'（北京时间）';
// Amounts are integer micro-units of the configured currency, not a provider invoice.
export function createBudget(auth,config) {
  const c={dailyCount:20,dailyMicros:0,monthlyMicros:0,inputPerMillion:0,outputPerMillion:0,verified:false,...config};
  for(const key of ['dailyCount','dailyMicros','monthlyMicros','inputPerMillion','outputPerMillion'])
    if(!Number.isSafeInteger(c[key])||c[key]<0||c[key]>1_000_000_000)throw new Error('费用设置必须是有效非负整数。');
  const cost=(input,output)=>Math.ceil((input*c.inputPerMillion+output*c.outputPerMillion)/1_000_000);
  const reservation=cost(131072*2,6000*2);
  const periods=()=>{const now=auth.clock(),d=new Date(now),day=Math.floor(now/86400000)*86400000;return {
    now,day,month:Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),1),dayReset:day+86400000,monthReset:Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,1)};};
  const spent=since=>auth.get('SELECT COALESCE(SUM(MAX(reserved,charged)),0) n FROM tasks WHERE created>=?',since).n;
  const portraitDailyLimit=10;
  const portraitCount=(account,since)=>auth.get("SELECT COUNT(*) n FROM tasks WHERE account=? AND task_type='PROFILE' AND created>=? AND (state NOT IN ('FAILED','UNCERTAIN') OR calls>0 OR charged>0)",account,since).n;
  const configured=()=>c.verified===true&&reservation>0&&c.dailyMicros>0&&c.monthlyMicros>0;
  function checkNewTask(account,taskType,p) {
    const reasons=[],messages=[];let status=429,legacy;
    const add=(code,reset_at,message,error)=>{reasons.push({code,reset_at});messages.push(message);legacy??=error;};
    if(!configured()) {status=503;add('BUDGET_NOT_CONFIGURED',null,'模型预算尚未完成配置，需要开发端核对；等待额度重置不会自动恢复。','模型预算尚未配置或已暂停。');}
    if(auth.get("SELECT value FROM control WHERE key='budget_blocked'")?.value==='1') {status=503;add('BUDGET_PROTECTION_PAUSED',null,'模型用量触发保护，已暂停新分析，需要开发端核对费用；等待额度重置不会解除暂停。','模型预算尚未配置或已暂停。');}
    if(taskType==='PROFILE'&&portraitCount(account,p.day)>=portraitDailyLimit)
      add('PROFILE_DAILY_LIMIT',p.dayReset,'今天的新客画像次数已用完，每个主播账号每天最多 10 次。','今天的新客画像次数已用完，每个主播账号每天最多 10 次。');
    if(auth.get('SELECT COUNT(*) n FROM tasks WHERE account=? AND created>=?',account,p.day).n>=c.dailyCount)
      add('ACCOUNT_DAILY_COUNT',c.dailyCount>0?p.dayReset:null,'当前账号今天的分析次数已用完。','今天的分析次数已用完，明天再试。');
    if(auth.get('SELECT COUNT(*) n FROM tasks WHERE created>=?',p.day).n>=c.dailyCount)
      add('PROJECT_DAILY_COUNT',c.dailyCount>0?p.dayReset:null,'全项目今天的分析次数已用完。','项目今天的分析次数已用完，明天再试。');
    // Missing prices/amounts are a configuration problem, not an exhausted cycle.
    if(configured()) {
      if(spent(p.day)+reservation>c.dailyMicros)
        add('PROJECT_DAILY_AMOUNT',reservation<=c.dailyMicros?p.dayReset:null,'全项目今天的金额额度不足以预留本次分析。','项目分析预算已用完，请稍后再试。');
      if(spent(p.month)+reservation>c.monthlyMicros)
        add('PROJECT_MONTHLY_AMOUNT',reservation<=c.monthlyMicros?p.monthReset:null,'全项目本月的金额额度不足以预留本次分析。','项目分析预算已用完，请稍后再试。');
    }
    if(!reasons.length)return;
    const resets=[...new Set(reasons.map(r=>r.reset_at).filter(r=>r!==null))].sort((a,b)=>a-b);
    for(const reset of resets) {
      const monthly=reasons.some(r=>r.code==='PROJECT_MONTHLY_AMOUNT'&&r.reset_at===reset);
      const daily=reasons.some(r=>r.code!=='PROJECT_MONTHLY_AMOUNT'&&r.reset_at===reset);
      messages.push(`${daily&&monthly?'日、月':monthly?'月':'日'}额度周期在 ${beijingTime(reset)} 重置。`);
    }
    if(reasons.some(r=>r.reset_at===null&&!['BUDGET_NOT_CONFIGURED','BUDGET_PROTECTION_PAUSED'].includes(r.code)))
      messages.push('当前完整周期额度也不足以接纳本次分析，需要开发端核对配置，不能仅等待重置。');
    const reset_at=reasons.some(r=>r.reset_at===null)?null:Math.max(...resets);
    if(reset_at!==null)messages.push(`最早可在 ${beijingTime(reset_at)} 重新检查全部额度；重置不保证请求一定可用。`);
    throw new BudgetBlockedError(status,legacy,{message:messages.join('\n'),reasons,reset_at,day_timezone:'UTC'});
  }
  const reserve=(id,account,fingerprint,retryOf,taskType='REPLY')=>auth.tx(()=>{
    if(!['REPLY','OPENING','PROFILE'].includes(taskType))fail(400,'分析任务类型无效。');
    if(!uuid(id))fail(400,'缺少有效请求编号。');
    let old=auth.get('SELECT * FROM tasks WHERE id=?',id)||auth.get('SELECT * FROM tasks WHERE account=? AND fingerprint=? ORDER BY created DESC,rowid DESC LIMIT 1',account,fingerprint);
    if(old && old.account===account && old.fingerprint===fingerprint && old.task_type===taskType && ['FAILED','UNCERTAIN'].includes(old.state) && old.calls===0 && old.charged===0){auth.run('DELETE FROM tasks WHERE id=?',old.id);old=null;}
    // Explicitly acknowledged retry retains the original charge/reservation and consumes a new budget slot.
    if(retryOf && old?.id===retryOf && id!==old.id && old.account===account && old.fingerprint===fingerprint && old.task_type===taskType && ['FAILED','UNCERTAIN'].includes(old.state))old=null;
    if(old){if(old.account!==account||old.fingerprint!==fingerprint||old.task_type!==taskType)fail(409,'请求编号不能重复用于不同内容或任务。');return {existing:old};}
    const p=periods();checkNewTask(account,taskType,p);
    auth.run('INSERT INTO tasks(id,account,fingerprint,created,state,reserved,task_type) VALUES(?,?,?,?,?,?,?)',id,account,fingerprint,p.now,'RUNNING',reservation,taskType);
    return {existing:null};
  });
  function hooks(id) {
    return {
      beforeCall:()=>{
        const task=auth.get('SELECT * FROM tasks WHERE id=?',id);
        if(!task||task.state!=='RUNNING'||task.calls>=2)fail(429,'本次分析调用额度已用完。');
        auth.run('UPDATE tasks SET calls=calls+1 WHERE id=?',id);
      },
      onUsage:u=>{
        if(!Number.isSafeInteger(u.input_tokens)||!Number.isSafeInteger(u.output_tokens)||u.input_tokens<0||u.output_tokens<0||u.total_tokens!==u.input_tokens+u.output_tokens)throw new Error('模型用量缺失，本次保留预算预留。');
        const task=auth.get('SELECT * FROM tasks WHERE id=?',id),usage=JSON.parse(task.usage);
        usage.push(u);const charged=task.charged+cost(u.input_tokens,u.output_tokens);
        auth.run('UPDATE tasks SET usage=?,charged=? WHERE id=?',JSON.stringify(usage),charged,id);
        if(u.input_tokens>131072||u.output_tokens>6000||charged>task.reserved){auth.run("INSERT INTO control VALUES('budget_blocked','1') ON CONFLICT(key) DO UPDATE SET value='1'");throw new Error('模型用量超出预留范围，已暂停新分析。');}
      }
    };
  }
  const finish=(id,analysis,error=false)=>{
    const t=auth.get('SELECT * FROM tasks WHERE id=?',id);
    const known=JSON.parse(t.usage).length===t.calls;
    auth.run('UPDATE tasks SET state=?,analysis=?,reserved=? WHERE id=?',error?'FAILED':'DONE',analysis||null,known?t.charged:t.reserved,id);
  };
  return {reserve,hooks,finish,summary:account=>{const p=periods();return {daily_limit:c.dailyCount,used_today:auth.get('SELECT COUNT(*) n FROM tasks WHERE account=? AND created>=?',account,p.day).n,
    project_used_today:auth.get('SELECT COUNT(*) n FROM tasks WHERE created>=?',p.day).n,
    reply_used_today:auth.get("SELECT COUNT(*) n FROM tasks WHERE account=? AND task_type='REPLY' AND created>=?",account,p.day).n,
    opening_used_today:auth.get("SELECT COUNT(*) n FROM tasks WHERE account=? AND task_type='OPENING' AND created>=?",account,p.day).n,
    portrait_daily_limit:portraitDailyLimit,portrait_used_today:portraitCount(account,p.day),reset_at:p.dayReset,day_timezone:'UTC',
    currency:c.currency||'CNY',configured:configured()};}};
}
