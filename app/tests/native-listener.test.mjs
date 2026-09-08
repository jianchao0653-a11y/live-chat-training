import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {createApplication} from '../server.mjs';

test('native listener isolates management even behind a headerless Host-rewriting proxy',async t=>{
  const app=createApplication({database:':memory:',apiKey:'',accessToken:''});
  t.after(()=>new Promise(r=>app.server.close(r)));
  assert(app.nativeServer,'separate native listener is required');
  t.after(()=>new Promise(r=>app.nativeServer.close(r)));
  for(const server of [app.server,app.nativeServer]){server.listen(0,'127.0.0.1');await once(server,'listening');}
  const proxy=http.createServer((req,res)=>{
    const upstream=http.request({hostname:'127.0.0.1',port:app.nativeServer.address().port,path:req.url,method:req.method,
      headers:{...req.headers,host:'localhost'}},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
    upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);
  });
  proxy.listen(0,'127.0.0.1');await once(proxy,'listening');t.after(()=>new Promise(r=>proxy.close(r)));
  const base=`http://127.0.0.1:${app.server.address().port}`,remote=`http://127.0.0.1:${proxy.address().port}`;
  const boot=await(await fetch(base+'/api/bootstrap')).json();
  const post=(url,body,headers={})=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});
  for(const path of ['/','/app.js','/api/bootstrap','/api/export','/api/devices','/api/settings','/api/native/../export','/api/native/%2e%2e/devices'])
    assert.equal((await fetch(remote+path)).status,403,path);
  assert.equal((await post(remote+'/api/devices/pairing',{streamer_id:'0001'},{'X-CSRF-Token':boot.csrf})).status,403);
  assert.equal((await fetch(remote+'/api/native/roster')).status,401);
  const code=await(await post(base+'/api/devices/pairing',{streamer_id:'0001'},{'X-CSRF-Token':boot.csrf})).json();
  const device=await(await post(remote+'/api/native/pair',{code:code.code,name:'合成代理手机'})).json();
  assert(device.token);
  assert.equal((await fetch(remote+'/api/native/roster',{headers:{Authorization:`Bearer ${device.token}`}})).status,200);
  await fetch(base+'/api/devices/'+device.id,{method:'DELETE',headers:{'X-CSRF-Token':boot.csrf}});
  assert.equal((await fetch(remote+'/api/native/roster',{headers:{Authorization:`Bearer ${device.token}`}})).status,401);
  const nextCode=await(await post(base+'/api/devices/pairing',{streamer_id:'0001'},{'X-CSRF-Token':boot.csrf})).json();
  const nextDevice=await(await post(remote+'/api/native/pair',{code:nextCode.code,name:'合成存活测试'})).json();
  // Closing either listener must not close the shared store while the other is live.
  await new Promise(r=>app.server.close(r));
  assert.equal((await fetch(remote+'/api/native/roster',{headers:{Authorization:`Bearer ${nextDevice.token}`}})).status,200);
});
