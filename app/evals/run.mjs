import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {localAnalysis,modelAnalysis,roles} from '../engine.mjs';
import {performance} from 'node:perf_hooks';
const args=process.argv.slice(2),value=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const mode=value('--mode','local');if(!['local','live'].includes(mode))throw new Error('Use --mode local|live');
const cases=JSON.parse(await readFile(new URL('./cases.json',import.meta.url),'utf8'));
const limit=Number(value('--limit',mode==='live'?'5':String(cases.length)));
if(!Number.isInteger(limit)||limit<1||limit>cases.length)throw new Error('Invalid case limit');
const folder=new URL('../../output/evals/',import.meta.url);await mkdir(folder,{recursive:true});
const report={mode,model:process.env.OPENAI_MODEL||'gpt-6-astra',createdAt:new Date().toISOString(),synthetic:true,humanReviewed:false,qualityAccepted:false,requests:0,usage:{input_tokens:0,output_tokens:0,cached_tokens:0},cases:[]};
if(mode==='live'&&!process.env.OPENAI_API_KEY){report.status='BLOCKED_MISSING_API_KEY';await writeFile(new URL('live-blocked.json',folder),JSON.stringify(report,null,2));console.error(report.status);process.exitCode=2;}
else{
  const tracked=async(url,options)=>{report.requests++;const response=await fetch(url,options);try{const body=await response.clone().json();report.usage.input_tokens+=body.usage?.input_tokens||0;report.usage.output_tokens+=body.usage?.output_tokens||0;report.usage.cached_tokens+=body.usage?.input_tokens_details?.cached_tokens||0;}catch{}return response;};
  for(const c of cases.slice(0,limit)){
    const start=performance.now();const row={id:c.id,status:'FAIL',humanReview:'PENDING'};
    try{
      const person={name:'合成人物',stage:'熟悉中',claims:[],outcomes:[],boundary:'不承诺随时在线，不以消费交换亲密。'};
      const result=mode==='live'?await modelAnalysis(c.text,person,c.goal,{key:process.env.OPENAI_API_KEY,model:report.model},tracked):localAnalysis(c.text,person,c.goal);
      row.checks={evidenceGrounded:result.evidence.every(e=>c.text.includes(e.quote)),rolesCovered:roles.every(r=>result.reviews.filter(x=>x.role===r).length===1),stoppedWithoutCandidates:result.route!=='SAFE_STOP'||result.candidates.length===0,independentJudge:mode==='local'||result.route==='SAFE_STOP'||result.judge.source==='独立模型调用',expectedStop:c.route!=='SAFE_STOP'||result.route==='SAFE_STOP'};
      row.status=Object.values(row.checks).every(Boolean)?'PASS_MECHANICAL':'FAIL';row.expectedRoute=c.route;row.actualRoute=result.route;row.output=result;
    }catch(e){row.error=e.message;}
    row.elapsedMs=Math.round(performance.now()-start);report.cases.push(row);
  }
  const durations=report.cases.map(c=>c.elapsedMs).sort((a,b)=>a-b),percentile=p=>durations[Math.max(0,Math.ceil(durations.length*p)-1)];
  report.latency={p50Ms:percentile(.5),p95Ms:percentile(.95)};report.status=report.cases.every(c=>c.status==='PASS_MECHANICAL')?'PASS_MECHANICAL_ONLY':'FAIL';report.costUSD=null;report.costNote='Token usage recorded; billing needs verified model rates and invoice. No invented price.';
  await writeFile(new URL(mode+'-report.json',folder),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,cases:report.cases.length,requests:report.requests,latency:report.latency,humanReview:'PENDING'}));if(report.status==='FAIL')process.exitCode=1;
}
