// Personal-computer pilot. Expose only this loopback API via the MADR-041 HTTPS gateway.
import {readFileSync,writeFileSync,existsSync,mkdirSync,unlinkSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {createCloud} from './cloud.mjs';
import {diagnose,requestId} from './diagnostics.mjs';

export async function startPc({directory,apiKey='',model='qwen-plus',baseUrl,budget={},port=4318}={}) {
  const root=resolve(directory),app=createCloud({directory:join(root,'data'),backupDirectory:join(root,'..','pc-backups'),apiKey,model,baseUrl,budget,provider:'bailian'});
  const stateFile=join(root,'service.json'),stopFile=join(root,'stop.json');
  const instance=randomUUID();let poll,maintenance,closing;
  const maintain=()=>app.maintain();
  const state=status=>writeFileSync(stateFile,JSON.stringify({instance,pid:process.pid,port:app.server.address()?.port||port,status},null,2),{mode:0o600});
  const close=()=>closing??=(async()=>{clearInterval(poll);clearInterval(maintenance);await app.close();state('stopped');})();
  try {
    maintain();
    await new Promise((done,reject)=>{app.server.once('error',reject);app.server.listen(port,'127.0.0.1',done);});
    state('running');
    poll=setInterval(()=>{
      try {
        if(existsSync(stopFile)&&JSON.parse(readFileSync(stopFile,'utf8')).instance===instance){
          unlinkSync(stopFile);close().catch(e=>{diagnose('service_failed',requestId(),'shutdown',e);process.exitCode=1;});
        }
      }catch(e){diagnose('service_failed',requestId(),'stop-request',e);}
    },500);poll.unref();
    maintenance=setInterval(()=>{try{maintain();}catch(e){diagnose('maintenance_failed',requestId(),'retention',e);}},3600000);maintenance.unref();
    return {app,close,instance};
  }catch(e){clearInterval(poll);clearInterval(maintenance);await app.close();throw e;}
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    const workspace=fileURLToPath(new URL('../',import.meta.url)),directory=join(workspace,'runtime','pc-server');
    mkdirSync(directory,{recursive:true,mode:0o700});
    const configFile=join(directory,'cloud-config.json');
    const config=JSON.parse(readFileSync(existsSync(configFile)?configFile:join(workspace,'native','deploy','cloud-config.example.json'),'utf8'));
    const keyFile=join(workspace,'百炼.txt');let apiKey='';
    if(existsSync(keyFile)){
      const keys=readFileSync(keyFile,'utf8').match(/sk-[A-Za-z0-9_-]+/g);
      if(keys?.length!==1)throw new Error('Invalid key file');apiKey=keys[0];
    }
    const service=await startPc({directory,apiKey,model:config.model,baseUrl:config.baseUrl,budget:config.budget});
    console.log('PC native API ready on loopback:4318; public HTTPS gateway acceptance is required for phone access');
    const stop=()=>service.close().catch(e=>{diagnose('service_failed',requestId(),'shutdown',e);process.exitCode=1;});
    process.once('SIGINT',stop);process.once('SIGTERM',stop);
  }catch(e){diagnose('service_failed',requestId(),'startup',e);process.exitCode=1;}
}
