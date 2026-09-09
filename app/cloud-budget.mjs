import {fail,uuid} from './cloud-auth.mjs';
// Amounts are integer micro-units of the configured currency, not a provider invoice.
export function createBudget(auth,config) {
  const c={dailyCount:20,dailyMicros:0,monthlyMicros:0,inputPerMillion:0,outputPerMillion:0,verified:false,...config};
  for(const key of ['dailyCount','dailyMicros','monthlyMicros','inputPerMillion','outputPerMillion'])
    if(!Number.isSafeInteger(c[key])||c[key]<0||c[key]>1_000_000_000)throw new Error('费用设置必须是有效非负整数。');
  const cost=(input,output)=>Math.ceil((input*c.inputPerMillion+output*c.outputPerMillion)/1_000_000);
  const reservation=cost(131072*2,6000*2);
  const day=()=>Math.floor(auth.clock()/86400000)*86400000;
  const month=()=>{const d=new Date(auth.clock());return Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),1);};
  const spent=since=>auth.get('SELECT COALESCE(SUM(MAX(reserved,charged)),0) n FROM tasks WHERE created>=?',since).n;
  const reserve=(id,account,fingerprint,retryOf)=>auth.tx(()=>{
    if(!uuid(id))fail(400,'缺少有效请求编号。');
    let old=auth.get('SELECT * FROM tasks WHERE id=?',id)||auth.get('SELECT * FROM tasks WHERE account=? AND fingerprint=? ORDER BY created DESC,rowid DESC LIMIT 1',account,fingerprint);
    if(old && old.account===account && old.fingerprint===fingerprint && ['FAILED','UNCERTAIN'].includes(old.state) && old.calls===0 && old.charged===0){auth.run('DELETE FROM tasks WHERE id=?',old.id);old=null;}
    // Explicitly acknowledged retry retains the original charge/reservation and consumes a new budget slot.
    if(retryOf && old?.id===retryOf && id!==old.id && old.account===account && old.fingerprint===fingerprint && ['FAILED','UNCERTAIN'].includes(old.state))old=null;
    if(old){if(old.account!==account||old.fingerprint!==fingerprint)fail(409,'请求编号不能重复用于不同内容。');return {existing:old};}
    if(c.verified!==true||!reservation||!c.dailyMicros||!c.monthlyMicros||auth.get("SELECT value FROM control WHERE key='budget_blocked'")?.value==='1')fail(503,'模型预算尚未配置或已暂停。');
    const n=auth.get('SELECT COUNT(*) n FROM tasks WHERE account=? AND created>=?',account,day()).n;
    if(n>=c.dailyCount)fail(429,'今天的分析次数已用完，明天再试。');
    if(auth.get('SELECT COUNT(*) n FROM tasks WHERE created>=?',day()).n>=c.dailyCount)fail(429,'项目今天的分析次数已用完，明天再试。');
    if(spent(day())+reservation>c.dailyMicros||spent(month())+reservation>c.monthlyMicros)fail(429,'项目分析预算已用完，请稍后再试。');
    auth.run('INSERT INTO tasks(id,account,fingerprint,created,state,reserved) VALUES(?,?,?,?,?,?)',id,account,fingerprint,auth.clock(),'RUNNING',reservation);
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
  return {reserve,hooks,finish,summary:account=>({daily_limit:c.dailyCount,used_today:auth.get('SELECT COUNT(*) n FROM tasks WHERE account=? AND created>=?',account,day()).n,currency:c.currency||'CNY',configured:c.verified===true&&reservation>0&&c.dailyMicros>0&&c.monthlyMicros>0})};
}
