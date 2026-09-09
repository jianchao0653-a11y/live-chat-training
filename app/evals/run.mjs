import {fileURLToPath} from 'node:url';
import {evaluateText} from './text-evaluation.mjs';
import {readFileSync} from 'node:fs';

const args=process.argv.slice(2),options={};
try {
  const allowed=new Set(['--mode','--manifest','--limit']);
  for(let i=0;i<args.length;i+=2){if(!allowed.has(args[i])||!args[i+1]||args[i+1].startsWith('--')||Object.hasOwn(options,args[i]))throw new Error('Invalid arguments');options[args[i]]=args[i+1];}
  const provider=process.env.LENS_MODEL_PROVIDER||'openai';
  if(!['openai','bailian'].includes(provider))throw new Error('Invalid provider');
  const keyFile=process.env.LENS_MODEL_KEY_FILE;
  const apiKey=keyFile?(readFileSync(keyFile,'utf8').match(/sk-[A-Za-z0-9_-]+/g)||[])[0]||'':provider==='bailian'?process.env.DASHSCOPE_API_KEY||'':process.env.OPENAI_API_KEY||'';
  const {report,directory}=await evaluateText({mode:options['--mode']||'local',manifestPath:options['--manifest'],
    ...(options['--limit']!==undefined?{limit:Number(options['--limit'])}:{}),
    apiKey,provider,baseUrl:process.env.LENS_BAILIAN_BASE_URL,model:process.env.LENS_BAILIAN_MODEL||(provider==='bailian'?'qwen-plus':process.env.OPENAI_MODEL||'gpt-6-astra'),outputRoot:fileURLToPath(new URL('../../output/evals/',import.meta.url))});
  console.log(JSON.stringify({status:report.status,cases:report.cases.length,requests:report.requests,latency:report.latency,humanReview:'PENDING',qualityAccepted:false,directory}));
  if(report.status==='BLOCKED_MISSING_API_KEY')process.exitCode=2;
  else if(report.status==='FAIL')process.exitCode=1;
}catch {console.error('EVALUATION_INPUT_OR_IO_ERROR: 检查参数、清单授权、字段、大小与样本路径；未输出输入内容或密钥。');process.exitCode=1;}
