// Explicit, temporary budget-UI fixture. No default fixture or runtime data is changed.
import {createCloud} from '../../app/cloud.mjs';
import {createBudget,budgetErrorDetails} from '../../app/cloud-budget.mjs';
import {mkdtempSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join,resolve,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';
import {createHash,randomUUID} from 'node:crypto';

if(process.env.LENS_SYNTHETIC_SCENARIO!=='keyboard-budget')throw new Error('This fixture requires the explicit keyboard-budget synthetic scenario');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),args=process.argv.slice(2);
if(args.length!==2||args[0]!=='--out')throw new Error('Usage: keyboard_budget_fixture.mjs --out <existing project output directory>');
const output=realpathSync(resolve(args[1])),allowed=realpathSync(join(root,'output')),within=relative(allowed,output);
if(!within||isAbsolute(within)||within==='..'||within.startsWith('..'+sep))throw new Error('Fixture output must be inside project output');
const scenarios=['daily','monthly','both','paused','missing'];
const instant=Date.UTC(2026,8,10,12),reservation=274144;
const config={verified:true,dailyCount:20,dailyMicros:10000000,monthlyMicros:100000000,
  inputPerMillion:1000000,outputPerMillion:1000000,currency:'SYNTHETIC'};
const tempParent=realpathSync(tmpdir()),directory=mkdtempSync(join(tempParent,'lens-keyboard-budget-'));
const receipt={synthetic:true,scenario:'keyboard-budget',realProviderCalls:0,status:'STARTING',calls:[],attempts:[],
  plannedScenarios:scenarios,clockUtc:new Date(instant).toISOString(),startedAt:new Date().toISOString()};
const save=()=>writeFileSync(join(output,'fixture-receipt.json'),JSON.stringify(receipt,null,2),'utf8');
const app=createCloud({directory,apiKey:'synthetic',model:'qwen-plus',provider:'bailian',clock:()=>instant,budget:config,
  fetcher:async()=>{receipt.calls.push({ordinal:receipt.calls.length+1,unexpected:true});save();throw new Error('Budget UI rejection must not call any model');}});
const ledgerHash=()=>createHash('sha256').update(JSON.stringify(app.auth.all('SELECT * FROM tasks ORDER BY rowid'))).digest('hex');
let originalLedger,ownedAccount,stopping=false;
// Each actual UI submission advances one explicit scenario. The errors are
// produced by the real budget implementation, not canned HTTP responses.
app.budget.reserve=(id,account,fingerprint,retryOf,taskType)=>{
  const scenario=scenarios[receipt.attempts.length];
  if(!scenario||account!==ownedAccount||taskType!=='OPENING'||retryOf||ledgerHash()!==originalLedger)
    throw new Error('Unexpected budget UI scenario submission or ledger change');
  const overrides={};
  if(scenario==='daily'||scenario==='both')overrides.dailyMicros=reservation+100;
  if(scenario==='monthly'||scenario==='both')overrides.monthlyMicros=reservation+100;
  if(scenario==='missing')overrides.verified=false;
  app.auth.run("INSERT INTO control VALUES('budget_blocked',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",scenario==='paused'?'1':'0');
  const limits=createBudget(app.auth,{...config,...overrides});
  const attempt={ordinal:receipt.attempts.length+1,scenario,taskType,ledgerBeforeSha256:ledgerHash(),providerCallsBefore:receipt.calls.length};
  receipt.attempts.push(attempt);
  try{limits.reserve(id,account,fingerprint,retryOf,taskType);throw new Error('Expected synthetic budget rejection did not happen');}
  catch(error){
    const block=budgetErrorDetails(error).budget_block;
    Object.assign(attempt,{status:error.status||500,budgetBlock:block||null,legacyError:block?error.message:null,
      ledgerAfterSha256:ledgerHash(),providerCallsAfter:receipt.calls.length});save();throw error;
  }
};
async function stop(){
  if(stopping)return;stopping=true;
  try{
    receipt.finalLedgerSha256=ledgerHash();receipt.allAttemptsPreservedLedger=receipt.attempts.every(a=>a.ledgerBeforeSha256===originalLedger&&a.ledgerAfterSha256===originalLedger);
    await app.close();
    const tail=relative(tempParent,realpathSync(directory));
    if(isAbsolute(tail)||tail.includes(sep)||!tail.startsWith('lens-keyboard-budget-'))throw new Error('Unexpected synthetic cleanup path');
    rmSync(directory,{recursive:true,force:true});receipt.status='STOPPED';receipt.temporaryDataRemoved=true;
  }catch(error){receipt.status='CLEANUP_FAILED';receipt.errorType=error.name;process.exitCode=1;}
  finally{receipt.finishedAt=new Date().toISOString();save();process.stdin.pause();}
}
try{
  const invite=app.auth.invite();ownedAccount=invite.account_id;
  // One deliberately uncertain, synthetic charge remains untouched in all five cases.
  app.auth.run('INSERT INTO tasks(id,account,fingerprint,created,state,reserved,charged,calls,task_type) VALUES(?,?,?,?,?,?,?,?,?)',
    randomUUID(),ownedAccount,'synthetic-prior-uncertain-budget',instant,'UNCERTAIN',200,30,1,'REPLY');
  originalLedger=ledgerHash();receipt.initialLedgerSha256=originalLedger;
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');receipt.status='READY';save();
  writeFileSync(join(output,'fixture.json'),JSON.stringify({synthetic:true,scenario:'keyboard-budget',pid:process.pid,
    base:`http://127.0.0.1:${app.server.address().port}`,invite:invite.invite}),'utf8');
  process.stdin.setEncoding('utf8');let buffer='';
  process.stdin.on('data',chunk=>{buffer+=chunk;if(buffer.length>1000){buffer='';void stop();return;}
    if(buffer.includes('\n')){const command=buffer.trim();buffer='';if(command==='stop')void stop();}});
  process.stdin.on('end',()=>void stop());process.once('SIGINT',()=>void stop());process.once('SIGTERM',()=>void stop());
  console.log('Synthetic budget fixture ready on an owned random loopback port.');
}catch(error){await stop();throw error;}
