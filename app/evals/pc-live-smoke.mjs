// Authorized synthetic workflow through the running PC API and its real budget ledger.
import {openCloudAuth} from '../cloud-auth.mjs';
import {randomUUID} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
const auth=openCloudAuth('runtime/pc-server/data/identity.sqlite');
const invite=auth.invite();let token,person,session;
const requestId=randomUUID(),report={synthetic:true,humanReviewed:false,qualityAccepted:false,passed:false};
async function call(path,body){
  const r=await fetch('http://127.0.0.1:4318/api/native/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(100000)});
  if(!r.ok)throw new Error('API_HTTP_'+r.status);
  return r.json();
}
try{
  session=await call('auth/activate',{code:invite.invite,name:'synthetic-acceptance',approved:true});token=session.token;
  person=await call('library/people',{name:'合成验收人物',platform:'微信',notes:'双方都喜欢散步',boundary:'不编造去过的地点'});
  const result=await call('analyze',{request_id:requestId,person_id:person.id,pair_id:person.relationship.id,context:'synthetic-editor',host:'com.synthetic.chat',approved:true,text:'对方：今天终于把那个项目做完了，准备周末去公园走走，你有什么推荐吗？',goal:'自然接话',mode:'model'});
  report.passed=!!result.analysis_id;report.analysisId=result.analysis_id;
  report.result=result;
}catch(e){report.error=/^API_HTTP_\d+$/.test(e.message)?e.message:'WORKFLOW_FAILED';}
finally{
  if(person){try{await call('library/people/'+person.id+'/delete',{});report.syntheticPersonDeleted=true;}catch{report.syntheticPersonDeleted=false;}}
  if(session)auth.revoke(session.id);
  auth.run('UPDATE accounts SET disabled=1 WHERE id=?',invite.account_id);
  report.ledger=auth.get('SELECT state,calls,reserved,charged,usage FROM tasks WHERE id=?',requestId)||null;
  auth.close();
}
mkdirSync('output/evals',{recursive:true});
const path='output/evals/pc-live-'+requestId+'.json';writeFileSync(path,JSON.stringify(report,null,2));
console.log(JSON.stringify({passed:report.passed,error:report.error,calls:report.ledger?.calls,chargedMicros:report.ledger?.charged,syntheticPersonDeleted:report.syntheticPersonDeleted,report:path,humanReviewed:false}));
if(!report.passed)process.exitCode=1;
