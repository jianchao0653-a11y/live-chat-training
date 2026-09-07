// Isolated emulator fixture. Never opens runtime/lens.sqlite or calls a model.
import {createApplication} from '../../app/server.mjs';
import {writeFileSync} from 'node:fs';
import {once} from 'node:events';
const telemetry={routes:{},mockModelCalls:0};
const record=()=>writeFileSync(new URL('../../output/native/fixture-telemetry.json',import.meta.url),JSON.stringify(telemetry));
const app=createApplication({database:':memory:',apiKey:'synthetic-key',fetcher:async(url,options)=>{
  telemetry.mockModelCalls++;record();
  const body=JSON.parse(options.body);
  if(body.text?.format?.name!=='chat_transcript')throw new Error('Fixture only supports mocked OCR');
  return new Response(JSON.stringify({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({text:'对方：今天加班很累，想安静休息。',warning:'合成 OCR 固定夹具，不代表真实识别质量。'})}]}]}));
}});
app.server.on('request',req=>{const path=req.url.split('?')[0];telemetry.routes[path]=(telemetry.routes[path]||0)+1;record();});
app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
const base=`http://127.0.0.1:${app.server.address().port}`;
const boot=await(await fetch(base+'/api/bootstrap')).json();
const post=async(path,data)=>(await fetch(base+'/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.csrf},body:JSON.stringify(data)})).json();
const person=await post('people',{name:'合成测试人物',platform:'视频号',stage:'熟悉中',streamer_id:'0001'});
const pairing=await post('devices/pairing',{streamer_id:'0001'});
writeFileSync(new URL('../../output/native/fixture.json',import.meta.url),JSON.stringify({pid:process.pid,base,csrf:boot.csrf,person,pairing}));
console.log('Synthetic memory-only service ready');
process.on('SIGTERM',()=>app.server.close(()=>process.exit(0)));
