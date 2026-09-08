// Project emulator only; no private database or real provider access.
import {createCloud} from '../../app/cloud.mjs';
import {localAnalysis} from '../../app/engine.mjs';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
const directory=mkdtempSync(join(tmpdir(),'lens-cloud-emulator-'));
let calls=0;
const app=createCloud({directory,apiKey:'synthetic-key',budget:{verified:true,currency:'SYNTHETIC',inputPerMillion:1000000,outputPerMillion:1000000,dailyMicros:100000000,monthlyMicros:100000000,dailyCount:20},fetcher:async(_u,o)=>{
  calls++;const b=JSON.parse(o.body);const {judge,...r}=localAnalysis('对方：今天加班很累，想安静休息。',{name:'合成测试人物',claims:[]},'关心近况');
  const result=b.max_tokens===512?{verdict:'PASS',reason:'合成独立终审'}:r;
  return new Response(JSON.stringify({model:'qwen-plus',usage:{prompt_tokens:100,completion_tokens:100,total_tokens:200},choices:[{finish_reason:'stop',message:{content:JSON.stringify(result)}}]}));
}});
const invite=app.auth.invite();app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
writeFileSync(new URL('../../output/native/cloud-fixture.json',import.meta.url),JSON.stringify({pid:process.pid,base:`http://127.0.0.1:${app.server.address().port}`,invite:invite.invite,account:invite.account_id}));
console.log('Synthetic cloud fixture ready');
const stop=async()=>{await app.close();rmSync(directory,{recursive:true,force:true});console.log(JSON.stringify({synthetic:true,modelCalls:calls}));};
process.once('SIGINT',stop);process.once('SIGTERM',stop);
