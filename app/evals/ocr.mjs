// Runs the production OCR HTTP route on a separate memory-only application.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname,extname,relative,isAbsolute} from 'node:path';
import {once} from 'node:events';
import {createApplication} from '../server.mjs';
import {ocrMetrics} from './ocr-metrics.mjs';
const args=process.argv.slice(2),index=args.indexOf('--manifest');
const folder=new URL('../../output/evals/',import.meta.url);await mkdir(folder,{recursive:true});
const report={createdAt:new Date().toISOString(),status:'BLOCKED',model:process.env.OPENAI_MODEL||'gpt-6-astra',qualityAccepted:false,humanReviewed:false,requests:0,usage:{input_tokens:0,output_tokens:0,cached_tokens:0},costUSD:null,cases:[]};
if(!process.env.OPENAI_API_KEY) {
  report.status='BLOCKED_MISSING_API_KEY';await writeFile(new URL('ocr-blocked.json',folder),JSON.stringify(report,null,2));console.error(report.status);process.exitCode=2;
} else {
  if(index<0||!args[index+1])throw new Error('Provide --manifest with explicitly approved image samples');
  const manifestPath=resolve(args[index+1]);
  const manifest=JSON.parse(await readFile(manifestPath,'utf8'));
  if(manifest.approvedForCloud!==true||!['synthetic','deidentified'].includes(manifest.dataClass)||!Array.isArray(manifest.cases)||manifest.cases.length<1||manifest.cases.length>50)throw new Error('Manifest requires explicit cloud approval, data class, and 1–50 cases');
  report.dataClass=manifest.dataClass;
  // Validate every input before issuing a paid request.
  const samples=[];
  for(const c of manifest.cases) {
    if(typeof c.id!=='string'||typeof c.expected!=='string'||!c.expected.trim()||c.expected.length>20000)throw new Error('Invalid gold text');
    const path=resolve(dirname(manifestPath),c.image),rel=relative(dirname(manifestPath),path);
    if(isAbsolute(rel)||rel==='..'||rel.startsWith('..'+(process.platform==='win32'?'\\':'/')))throw new Error('Image must stay within the manifest directory');
    const mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[extname(path).toLowerCase()];
    const bytes=await readFile(path);if(!mime||bytes.length>4_400_000)throw new Error('Unsupported or oversized image');
    samples.push({...c,image:'data:'+mime+';base64,'+bytes.toString('base64')});
  }
  const tracked=async(url,options)=>{
    report.requests++;const response=await fetch(url,options);
    try{const b=await response.clone().json();report.usage.input_tokens+=b.usage?.input_tokens||0;report.usage.output_tokens+=b.usage?.output_tokens||0;report.usage.cached_tokens+=b.usage?.input_tokens_details?.cached_tokens||0;}catch{}
    return response;
  };
  const app=createApplication({database:':memory:',fetcher:tracked});
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  try {
    const base='http://127.0.0.1:'+app.server.address().port;
    const boot=await(await fetch(base+'/api/bootstrap')).json();
    for(const c of samples) {
      const start=performance.now(),row={id:c.id,humanReview:'PENDING'};
      try {
        const response=await fetch(base+'/api/extract',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.csrf},body:JSON.stringify({image:c.image})});
        const result=await response.json();if(!response.ok)throw new Error(result.error||'OCR failed');
        row.metrics=ocrMetrics(c.expected,result.text);row.transcript=result.text;row.warning=result.warning;row.status='MEASURED_NOT_ACCEPTED';
      }catch(e){row.status='FAIL';row.error=e.message;}
      row.elapsedMs=Math.round(performance.now()-start);report.cases.push(row);
    }
    const times=report.cases.map(c=>c.elapsedMs).sort((a,b)=>a-b);
    report.latency={p50Ms:times[Math.ceil(times.length*.5)-1],p95Ms:times[Math.ceil(times.length*.95)-1]};
    report.status=report.cases.some(c=>c.status==='FAIL')?'FAIL':'MEASURED_NOT_ACCEPTED';
    await writeFile(new URL('ocr-report.json',folder),JSON.stringify(report,null,2));
    console.log(JSON.stringify({status:report.status,cases:report.cases.length,requests:report.requests}));if(report.status==='FAIL')process.exitCode=1;
  } finally {app.server.closeAllConnections();await new Promise(done=>app.server.close(done));}
}
