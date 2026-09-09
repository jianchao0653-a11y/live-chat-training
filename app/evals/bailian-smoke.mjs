// One synthetic two-call workflow, explicitly separate from human quality acceptance.
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {modelAnalysis} from '../engine.mjs';
const keyPath=process.argv[2];if(!keyPath)throw new Error('Supply the authorized server key file path.');
const keyText=readFileSync(keyPath,'utf8'),keys=keyText.match(/sk-[A-Za-z0-9_-]+/g);
if(!keys||keys.length!==1)throw new Error('Expected one server key; no contents are printed.');
const out=resolve('output/evals','bailian-smoke-'+randomUUID());mkdirSync(out,{recursive:true});
let calls=0;const usage=[],started=Date.now();let result=null,error=null;
const ordinary=process.argv[3]==='ordinary';
try{
  result=await modelAnalysis(ordinary?'对方：今天终于把那个项目做完了，准备周末去公园走走，你有什么推荐吗？':'对方：今天加班很累，想安静休息。',{name:'合成人物',stage:'熟悉中',claims:[],notes:'双方都喜欢散步',boundary:ordinary?'不编造去过的地点或对方喜好':'尊重休息，不催促回复'},ordinary?'自然接话':'关心近况',{
    key:keys[0],provider:'bailian',model:process.env.LENS_BAILIAN_MODEL||'qwen-plus',baseUrl:process.env.LENS_BAILIAN_BASE_URL,
    beforeCall:()=>{if(++calls>2)throw new Error('Synthetic smoke call cap exceeded');},onUsage:u=>usage.push(u),onResponse:b=>writeFileSync(resolve(out,`synthetic-response-${calls}.json`),JSON.stringify(b,null,2))
  });
}catch(e){error=/HTTP \d+/.exec(e.message)?.[0]||(['ENETUNREACH','ECONNREFUSED','ENOTFOUND','EPERM','UND_ERR_CONNECT_TIMEOUT'].includes(e.cause?.code)?e.cause.code:'Provider/schema validation failed');writeFileSync(resolve(out,'diagnostic.json'),JSON.stringify({error_type:e.name,message:e.message.replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]')}));}
const report={synthetic:true,scenario:ordinary?'ordinary':'rest-boundary',provider:'bailian',model:process.env.LENS_BAILIAN_MODEL||'qwen-plus',calls,usage,elapsed_ms:Date.now()-started,mechanicalPassed:!!result,route:result?.route,candidates:result?.candidates?.length||0,error,humanReviewed:false,qualityAccepted:false};
writeFileSync(resolve(out,'report.json'),JSON.stringify(report,null,2));
if(result)writeFileSync(resolve(out,'synthetic-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({...report,report_directory:out}));
if(error)process.exitCode=1;
