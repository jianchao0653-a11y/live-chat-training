// Managed Node hosting entry point. The self-hosted entry stays loopback-only.
import {readFileSync} from 'node:fs';
import {resolve,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createCloud} from './cloud.mjs';

export function hostingSettings(env=process.env) {
  const directory=env.LENS_CLOUD_DATA;
  if(!directory||!isAbsolute(directory))throw new Error('A persistent absolute LENS_CLOUD_DATA path is required');
  const rawPort=env.PORT||'10000';
  if(!/^\d+$/.test(rawPort)||Number(rawPort)<1||Number(rawPort)>65535)throw new Error('Invalid hosting port');
  const config=env.LENS_CLOUD_CONFIG_JSON?JSON.parse(env.LENS_CLOUD_CONFIG_JSON):JSON.parse(readFileSync(new URL('../native/deploy/cloud-config.example.json',import.meta.url),'utf8'));
  if(!config||Array.isArray(config)||typeof config!=='object')throw new Error('Invalid hosting configuration');
  // Never pass through constructor overrides such as synthetic/directory.
  const apiKey=env.DASHSCOPE_API_KEY||'';
  if(apiKey&&!/^sk-[A-Za-z0-9_-]+$/.test(apiKey))throw new Error('Invalid provider secret format');
  return {port:Number(rawPort),options:{directory,apiKey,provider:'bailian',model:config.model||'qwen-plus',baseUrl:config.baseUrl,budget:config.budget||{}}};
}

export async function startHosted(env=process.env) {
  const {port,options}=hostingSettings(env),app=createCloud(options);
  let timer;
  try {
    app.maintain();
    await new Promise((done,reject)=>{app.server.once('error',reject);app.server.listen(port,'0.0.0.0',done);});
    timer=setInterval(()=>{try{app.maintain();}catch{console.error('Retention maintenance failed');}},3600000);timer.unref();
  }catch(e){await app.close();throw e;}
  let stopping;
  return {app,close:()=>stopping??=(async()=>{clearInterval(timer);await app.close();})()};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    const service=await startHosted();
    console.log('Managed native API ready');
    const stop=()=>{service.close().catch(()=>{console.error('Managed shutdown failed');process.exitCode=1;});};
    process.once('SIGINT',stop);process.once('SIGTERM',stop);
  }catch{
    // Do not print parsing errors or environment that might contain credentials.
    console.error('Managed startup failed; check persistent disk, configuration and service lock');process.exitCode=1;
  }
}
