// Owned, temporary synthetic cloud for keyboard_first_qa.py. Never reads runtime data.
import {createCloud} from '../../app/cloud.mjs';
import {localAnalysis,roles} from '../../app/engine.mjs';
import {mkdtempSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join,resolve,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const args=process.argv.slice(2);
if(args.length!==2||args[0]!=='--out')throw new Error('Usage: keyboard_first_fixture.mjs --out <existing project output directory>');
const output=realpathSync(resolve(args[1])),allowed=realpathSync(join(root,'output'));
const within=relative(allowed,output);
if(!within||isAbsolute(within)||within==='..'||within.startsWith('..'+sep))throw new Error('Fixture output must be inside project output');
const scenario=process.env.LENS_SYNTHETIC_SCENARIO||'default';
if(!['default','keyboard-details','keyboard-network','keyboard-retry','keyboard-timeout','keyboard-lifecycle'].includes(scenario))throw new Error('Unknown synthetic keyboard fixture scenario');
const tempParent=realpathSync(tmpdir()),directory=mkdtempSync(join(tempParent,'lens-keyboard-first-'));
const receipt={synthetic:true,realProviderCalls:0,status:'STARTING',calls:[],startedAt:new Date().toISOString()};
const replyDelay=Number(process.env.LENS_SYNTHETIC_REPLY_DELAY_MS||0);
if(!Number.isInteger(replyDelay)||replyDelay<0||replyDelay>30000)throw new Error('Synthetic reply delay must be within 0..30000 ms');
let delayedReply=false;
const save=()=>writeFileSync(join(output,'fixture-receipt.json'),JSON.stringify(receipt,null,2),'utf8');
function modelResult(input){
  if(!['PROFILE','OPENING'].includes(input.task_type)){
    const {judge,...result}=localAnalysis(input.chat,{name:'合成客户',claims:[]},input.goal);
    return result;
  }
  const evidence=input.materials.map((material,index)=>({id:`E${index+1}`,source_id:material.id,quote:material.text,kind:'SELF_DECLARED'}));
  const refs=evidence.map(item=>item.id);
  return {summary:'只整理主动提供的合成资料，缺少的信息保持未知。',strategy:'核对来源后再选择轻松话题。',
    reason:'资料无法证明未提供的经历或偏好。',risk:'资料内容仍需人工核对。',route:'FAST',alternative:'可以先问候并给对方拒绝空间。',evidence,
    reviews:roles.map(role=>({role,conclusion:'仅使用本次资料，保留未知。',evidence_refs:[...refs]})),
    chief:{goal:input.goal,conclusion:'先核对来源再使用。',conflict:'未知信息不作推断。'},
    candidates:input.task_type==='PROFILE'?[]:[{label:'问候',text:'你好呀，今天过得怎么样？'},{label:'征询话题',text:'有空的话，想聊点什么？'}],
    profile:{observations:evidence.length?[
      {id:'O1',kind:'SELF_DECLARED',content:'本次资料内容：'+input.materials[0].text,evidence_refs:['E1'],uncertainty:'这是合成转录，未作独立核实。'},
      {id:'OI',kind:'INFERRED',content:'这份资料可能是可询问的话题。',evidence_refs:['E1'],uncertainty:'不知道对方现在是否愿意聊。'}
    ]:[],unknowns:['对方现在是否愿意聊天尚不清楚。']}};
}
const app=createCloud({directory,apiKey:'synthetic-key-never-sent',model:'qwen-plus',provider:'bailian',
  budget:{verified:true,dailyCount:20,dailyMicros:1000000000,monthlyMicros:1000000000,inputPerMillion:1000000,outputPerMillion:1000000,currency:'SYNTHETIC'},
  fetcher:async(_url,options)=>{
    const body=JSON.parse(options.body),judge=body.max_tokens===512;
    const input=JSON.parse(body.messages.at(-1).content);
    const task=judge?input.input:input;
    receipt.calls.push({ordinal:receipt.calls.length+1,judge,taskType:task.task_type||'REPLY',
      chat:task.chat||'',goal:task.goal||'',
      materials:(task.materials||[]).map(({id,kind,text,source,observed_at})=>({id,kind,text,source,observed_at}))});
    save();
    if(scenario==='keyboard-retry'&&!judge&&receipt.calls.length===1)throw new Error('synthetic provider transport failure after charge admission');
    if(!judge&&(task.task_type||'REPLY')==='REPLY'&&replyDelay&&(scenario==='keyboard-lifecycle'||!delayedReply)){
      delayedReply=true;await new Promise(resolve=>setTimeout(resolve,replyDelay));
    }
    const result=judge?{verdict:'PASS',reason:'合成独立终审结果。'}:modelResult(input);
    return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:200,completion_tokens:100,total_tokens:300},
      choices:[{finish_reason:'stop',message:{content:JSON.stringify(result)}}]}));
  }});
let stopping=false;
async function stop(){
  if(stopping)return;stopping=true;
  try{
    await app.close();
    // Delete only the mkdtemp directory owned by this process, using one API.
    const tail=relative(tempParent,realpathSync(directory));
    if(isAbsolute(tail)||tail.includes(sep)||!tail.startsWith('lens-keyboard-first-'))throw new Error('Unexpected synthetic cleanup path');
    rmSync(directory,{recursive:true,force:true});
    receipt.status='STOPPED';receipt.temporaryDataRemoved=true;
  }catch(error){receipt.status='CLEANUP_FAILED';receipt.errorType=error.name;process.exitCode=1;}
  finally{receipt.finishedAt=new Date().toISOString();save();process.stdin.pause();}
}
try{
  const invite=app.auth.invite();
  if(scenario==='keyboard-details'){
    const {installDetailsScenario}=await import('./keyboard_details_fixture.mjs');
    installDetailsScenario({app,accountId:invite.account_id,output,receipt,save,isStopping:()=>stopping});
  }
  if(['keyboard-network','keyboard-retry','keyboard-timeout'].includes(scenario)){
    const {installNetworkScenario}=await import('./keyboard_network_fixture.mjs');
    installNetworkScenario({app,accountId:invite.account_id,receipt,save,scenario});
  }
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  receipt.status='READY';save();
  // The sole credential here is a new synthetic invite; no token/private path is persisted.
  writeFileSync(join(output,'fixture.json'),JSON.stringify({synthetic:true,pid:process.pid,base:`http://127.0.0.1:${app.server.address().port}`,invite:invite.invite}),'utf8');
  process.stdin.setEncoding('utf8');
  let buffer='';
  process.stdin.on('data',chunk=>{buffer+=chunk;if(buffer.length>1000){buffer='';void stop();return;}if(buffer.includes('\n')){const command=buffer.trim();buffer='';if(command==='stop')void stop();}});
  process.stdin.on('end',()=>void stop());
  process.once('SIGINT',()=>void stop());process.once('SIGTERM',()=>void stop());
  console.log('Synthetic keyboard fixture ready on an owned random loopback port.');
}catch(error){await stop();throw error;}
