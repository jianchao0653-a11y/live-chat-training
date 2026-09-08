import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {localAnalysis,modelAnalysis,roles,classify} from '../engine.mjs';
import {loadTextDataset,loadBuiltinDataset,digest} from './dataset.mjs';

export async function evaluateText({manifestPath,mode='local',limit,apiKey='',model='gpt-6-astra',provider='openai',baseUrl,fetcher=fetch,outputRoot}={}) {
  if(!['local','live','validate'].includes(mode))throw new Error('Use mode local|live|validate');
  if(!outputRoot)throw new Error('An output directory is required');
  // Validate every file before slicing or issuing a paid request.
  const dataset=manifestPath?await loadTextDataset(manifestPath,{forCloud:mode==='live'}):await loadBuiltinDataset();
  limit=limit??(mode==='live'?Math.min(5,dataset.cases.length):dataset.cases.length);
  if(!Number.isInteger(limit)||limit<1||limit>dataset.cases.length)throw new Error('Invalid case limit');
  const selected=dataset.cases.slice(0,limit),runId=randomUUID();
  const report={runId,createdAt:new Date().toISOString(),mode,model,provider,datasetId:dataset.datasetId,datasetHash:dataset.datasetHash,
    sourceKind:dataset.sourceKind,scope:'engine-only-minimal-context',dataClass:dataset.dataClass,synthetic:dataset.dataClass==='synthetic',authorizationRef:dataset.authorizationRef,
    reviewPlanId:dataset.reviewPlanId,totalCases:dataset.cases.length,selectedCases:selected.length,fullDataset:limit===dataset.cases.length,
    humanReviewed:false,qualityAccepted:false,requests:0,maxRequests:mode==='live'?2*selected.length:0,
    usage:{input_tokens:0,output_tokens:0,cached_tokens:0,reportedCalls:0},costUSD:null,
    costNote:'Usage is measured when provided; billing and human quality review remain separate.',cases:[]};
  const tracked=async(url,options)=>{
    if(report.requests>=report.maxRequests)throw new Error('Evaluation request budget exhausted');
    report.requests++;const response=await fetcher(url,options);
    try {
      const body=await response.clone().json(),u=provider==='bailian'?{input_tokens:body.usage?.prompt_tokens,output_tokens:body.usage?.completion_tokens,input_tokens_details:body.usage?.prompt_tokens_details}:body.usage;
      if(u&&[u.input_tokens,u.output_tokens].every(v=>Number.isSafeInteger(v)&&v>=0)){
        report.usage.reportedCalls++;report.usage.input_tokens+=u.input_tokens;report.usage.output_tokens+=u.output_tokens;
        const cached=u.input_tokens_details?.cached_tokens;if(Number.isSafeInteger(cached)&&cached>=0)report.usage.cached_tokens+=cached;
      }
    }catch{}
    return response;
  };
  const blocked=mode==='live'&&!apiKey;
  for(const c of selected) {
    const row={id:c.id,inputHash:c.inputHash,humanReview:'PENDING'};
    if(mode==='validate'||blocked){row.status=blocked?'NOT_RUN':'VALIDATED_NOT_EVALUATED';report.cases.push(row);continue;}
    const start=performance.now();
    try {
      const person={name:'样本人物',stage:'未提供',claims:[],outcomes:[],boundary:c.boundary};
      const result=mode==='live'?await modelAnalysis(c.text,person,c.goal,{key:apiKey,model,provider,baseUrl},tracked):localAnalysis(c.text,person,c.goal);
      row.checks={evidenceGrounded:result.evidence.every(e=>c.text.includes(e.quote)),rolesCovered:roles.every(role=>result.reviews.filter(r=>r.role===role).length===1),
        stoppedWithoutCandidates:result.route!=='SAFE_STOP'||result.candidates.length===0,
        independentJudge:mode!=='live'||result.judge.source==='独立模型调用'||(classify(c.text,c.goal)==='stop'&&result.judge.source==='独立规则检查'),
        expectedStop:c.route!=='SAFE_STOP'||result.route==='SAFE_STOP'};
      row.status=Object.values(row.checks).every(Boolean)?'PASS_MECHANICAL':'FAIL';row.expectedRoute=c.route;row.actualRoute=result.route;
      row.output=result;row.outputHash=digest(JSON.stringify(result));
    }catch {row.status='FAIL';row.error='ANALYSIS_OR_JUDGE_FAILED';}
    row.elapsedMs=Math.round(performance.now()-start);report.cases.push(row);
  }
  const times=report.cases.filter(c=>c.elapsedMs!==undefined).map(c=>c.elapsedMs).sort((a,b)=>a-b);
  report.latency=times.length?{p50Ms:times[Math.ceil(times.length*.5)-1],p95Ms:times[Math.ceil(times.length*.95)-1]}:null;
  report.status=blocked?'BLOCKED_MISSING_API_KEY':mode==='validate'?'VALIDATED_NOT_EVALUATED':report.cases.some(c=>c.status==='FAIL')?'FAIL':'PASS_MECHANICAL_ONLY';
  const directory=resolve(outputRoot,'text-'+runId);await mkdir(directory,{recursive:true});
  const serialized=JSON.stringify(report,null,2);await writeFile(resolve(directory,'report.json'),serialized,{flag:'wx'});
  for(const slot of ['A','B']) {
    const review={runId,reportHash:digest(serialized),datasetHash:dataset.datasetHash,reviewPlanId:dataset.reviewPlanId,slot,reviewerId:null,status:'PENDING',
      cases:report.cases.map(c=>({id:c.id,inputHash:c.inputHash,outputHash:c.outputHash??null,decision:null,speakerAndEvidence:null,boundaryAndStrategy:null,naturalness:null,criticalFinding:null,reason:null}))};
    await writeFile(resolve(directory,'review-'+slot+'.json'),JSON.stringify(review,null,2),{flag:'wx'});
  }
  return {report,directory};
}
