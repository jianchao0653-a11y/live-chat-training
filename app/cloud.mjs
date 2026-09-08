import http from 'node:http';
import {AsyncLocalStorage} from 'node:async_hooks';
import {mkdirSync,readFileSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {createApplication} from './server.mjs';
import {openCloudAuth,fail,digest,uuid} from './cloud-auth.mjs';
import {createBudget} from './cloud-budget.mjs';
import {platforms,stages} from './engine.mjs';
import {lockDirectory} from './cloud-maintenance.mjs';

const text=(v,max,required=false)=>{
  if(v===undefined&&!required)return '';
  if(typeof v!=='string'||v.length>max||(required&&!v.trim()))fail(400,`请填写有效内容，最长 ${max} 字符。`);
  return v.trim();
};
const pick=(v,options)=>{if(!options.includes(v))fail(400,'请选择有效选项。');return v;};
const send=(res,status,data)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data));};
async function bodyOf(req) {
  if(req.method==='GET')return {};
  if(req.headers['content-type']?.split(';')[0]!=='application/json')fail(415,'需要 JSON 请求。');
  let size=0;const parts=[];
  for await(const p of req){size+=p.length;if(size>100_000)fail(413,'提交内容过大。');parts.push(p);}
  try{const b=JSON.parse(Buffer.concat(parts).toString('utf8'));if(!b||Array.isArray(b)||typeof b!=='object')fail(400,'请求格式错误。');return b;}catch{fail(400,'请求格式错误。');}
}

export function createCloud({directory,apiKey='',model='qwen-plus',provider='bailian',baseUrl,fetcher=fetch,clock=Date.now,budget:budgetConfig={},synthetic=false}={}) {
  if(!directory)throw new Error('云端必须明确指定独立数据目录。');
  const root=resolve(directory);if(existsSync(join(root,'.restore-incomplete')))throw new Error('恢复未完成，不得启动此数据目录。');
  const unlock=lockDirectory(root);mkdirSync(join(root,'accounts'),{recursive:true,mode:0o700});
  const auth=openCloudAuth(join(root,'identity.sqlite'),clock),budget=createBudget(auth,budgetConfig);
  const contexts=new Map(),work=new AsyncLocalStorage();let active=0;
  // A crashed/aborted paid operation is never silently retried after restart.
  auth.run("UPDATE tasks SET state='UNCERTAIN' WHERE state='RUNNING'");
  function application(account) {
    if(!uuid(account)||!auth.get('SELECT id FROM accounts WHERE id=? AND disabled=0',account))fail(401,'账号不可用。');
    if(!contexts.has(account)) {
      const app=createApplication({database:join(root,'accounts',account+'.sqlite'),apiKey,model,provider,baseUrl,fetcher,clock,
        authorize:token=>{const d=auth.authorize(token);if(d.account_id!==account)fail(403,'账号不一致。');return d;},
        modelHooks:{beforeCall:b=>work.getStore()?.beforeCall(b),onUsage:u=>work.getStore()?.onUsage(u)}});
      app.store.run("UPDATE streamers SET name='我的聊天' WHERE id='0001'");
      contexts.set(account,app);
    }
    return contexts.get(account);
  }
  function person(app,id) {
    if(!uuid(id))fail(404,'人物不存在。');
    const p=app.store.person(id,'0001');if(!p?.relationship)fail(404,'人物不存在。');return p;
  }
  function purgeDerived(store,p) {
    store.run('DELETE FROM analyses WHERE person_id=?',p.id);
    store.run('DELETE FROM context_events WHERE pair_id=?',p.relationship.id);
    store.run('UPDATE pairs SET revision=revision+1 WHERE id=?',p.relationship.id);
    store.run("UPDATE people SET stage='',notes='',boundary='' WHERE id=?",p.id);
  }
  function journal(account,p,entire=false) {
    auth.run('INSERT INTO deletions(account,person,entire,created) VALUES(?,?,?,?)',account,p.id,entire?1:0,clock());
  }
  function library(app,account,path,method,b) {
    const s=app.store;
    if(path==='/api/native/library/people') {
      if(method==='GET')return {people:s.people('0001').filter(p=>p.pair_id).slice(0,100),platforms,stages};
      if(method==='POST') {
        if(s.get('SELECT COUNT(*) n FROM people').n>=100)fail(409,'试用版最多保存 100 位人物。');
        const id=s.createPerson({name:text(b.name,60,true),platform:pick(b.platform||'微信',platforms),stage:pick(b.stage||'初识',stages),notes:text(b.notes,3000),boundary:text(b.boundary,1000),streamer_id:'0001'},randomUUID());
        return s.person(id);
      }
    }
    let m=path.match(/^\/api\/native\/library\/people\/([^/]+)(?:\/(save|delete|memories|history))?$/);
    if(m) {
      const p=person(app,m[1]),action=m[2];
      if(!action&&method==='GET')return p;
      if(action==='history'&&method==='GET')return {history:s.all('SELECT id,goal,created_at FROM analyses WHERE person_id=? ORDER BY created_at DESC LIMIT 30',p.id).map(x=>{const a=s.analysis(x.id);return {...x,summary:a.result.summary,outcome:a.outcome};})};
      if(method!=='POST')fail(405,'请求方法不支持。');
      if(app.isActive(p.id))fail(409,'正在分析此人物，请完成后再修改。');
      if(action==='save') {
        const values={name:text(b.name,60,true),platform:pick(b.platform,platforms),stage:pick(b.stage,stages),notes:text(b.notes,3000),boundary:text(b.boundary,1000)};
        journal(account,p);s.tx(()=>purgeDerived(s,p));s.updatePerson(p.id,'0001',values);return s.person(p.id);
      }
      if(action==='delete'){journal(account,p,true);return s.deletePerson(p.id);}
      if(action==='memories'){
        if(s.get('SELECT COUNT(*) n FROM claims WHERE person_id=?',p.id).n>=100)fail(409,'每位人物最多保存 100 条记忆。');
        const c={id:randomUUID(),person_id:p.id,pair_id:p.relationship.id,kind:'FACT',content:text(b.content,1000,true),source:text(b.source,500,true),created_at:new Date(clock()).toISOString()};
        s.addClaim(c);return c;
      }
    }
    m=path.match(/^\/api\/native\/library\/memories\/([^/]+)\/(save|delete)$/);
    if(m&&method==='POST') {
      const c=s.get('SELECT * FROM claims WHERE id=?',m[1]);if(!c)fail(404,'记忆不存在。');
      const p=person(app,c.person_id);if(app.isActive(p.id))fail(409,'正在分析，请稍后修改。');
      const content=m[2]==='save'?text(b.content,1000,true):'',source=m[2]==='save'?text(b.source,500,true):'';
      journal(account,p);
      s.tx(()=>{purgeDerived(s,p);if(m[2]==='delete')s.run('DELETE FROM claims WHERE id=?',c.id);else s.run("UPDATE claims SET content=?,source=?,kind='FACT',created_at=? WHERE id=?",content,source,new Date(clock()).toISOString(),c.id);});
      return {saved:true,history_cleared:true};
    }
    m=path.match(/^\/api\/native\/library\/feedback\/([^/]+)\/(save|delete)$/);
    if(m&&method==='POST') {
      const a=s.analysis(m[1]);if(!a)fail(404,'记录不存在。');const p=person(app,a.person_id);
      if(app.isActive(p.id))fail(409,'正在分析，请稍后修改。');
      if(m[2]==='save'){
        const status=pick(b.status,['POSITIVE','MIXED','NEGATIVE','UNKNOWN']);
        const o={status,note:text(b.note,2000,status!=='UNKNOWN'),draft:text(b.draft,12000)};
        // Delete derived histories which may quote the previous observation.
        if(a.outcome){journal(account,p);s.tx(()=>{s.run('DELETE FROM analyses WHERE person_id=? AND id<>?',p.id,a.id);s.run('DELETE FROM context_events WHERE pair_id=?',p.relationship.id);});}
        s.saveOutcome(a.id,o);
      }else{journal(account,p);s.tx(()=>purgeDerived(s,p));}
      return {saved:true};
    }
    fail(404,'资料接口不存在。');
  }
  const server=http.createServer(async(req,res)=>{
    try {
      if(req.headers.origin)fail(403,'此入口仅供原生应用使用。');
      if(!['GET','POST'].includes(req.method))fail(405,'请求方法不支持。');
      const u=new URL(req.url,'http://localhost'),path=u.pathname;
      if(u.search||!path.startsWith('/api/native/'))fail(403,'此入口仅供原生应用使用。');
      if(path==='/api/native/health'&&req.method==='GET')return send(res,200,{status:'ok',version:'0.16.0',quality_accepted:false});
      if(path==='/api/native/auth/activate'&&req.method==='POST'){
        const b=await bodyOf(req);if(b.approved!==true)fail(400,'请先同意必要的数据处理说明。');
        return send(res,200,auth.activate(b.code,b.name||'Android'));
      }
      const token=(req.headers.authorization||'').replace(/^Bearer /,''),identity=auth.authorize(token),account=identity.account_id;
      const b=await bodyOf(req);
      if(path==='/api/native/auth/logout'&&req.method==='POST'){auth.revoke(identity.id);return send(res,200,{revoked:true});}
      if(path==='/api/native/auth/me'&&req.method==='GET')return send(res,200,{...identity,budget:budget.summary(account)});
      const app=application(account);
      if(path.startsWith('/api/native/library/'))return send(res,200,library(app,account,path,req.method,b));
      if(path==='/api/native/roster'&&req.method==='GET'){
        const result=await app.native.handle(req,path,b);return send(res,200,{...result,cloud:true,budget:budget.summary(account)});
      }
      if(path==='/api/native/analyze'&&req.method==='POST') {
        if(b.approved!==true)fail(400,'请先批准片段。');
        const p=person(app,b.person_id);
        if(b.pair_id!==p.relationship.id)fail(404,'人物关系不一致。');
        text(b.text,4000,true);
        if(!['自然接话','关心近况','修复误会','表达边界'].includes(b.goal))fail(400,'目标无效。');
        if(b.mode!=='model'&&!(synthetic&&b.mode==='local'))fail(400,'此服务使用联网模型分析。');
        if(b.mode==='model'&&!apiKey)fail(503,'模型服务尚未配置。');
        // Bind paid work to semantic content, not a transient Android Activity/request ID.
        // Rotation, process restart and a changed editor must not repeat uncertain charges.
        const fingerprint=digest(JSON.stringify({account,person:p,text:b.text,goal:b.goal,mode:b.mode,model,provider}));
        if(active>=2)fail(429,'分析服务繁忙，请稍后重试。');
        const reservation=budget.reserve(b.request_id,account,fingerprint);
        if(reservation.existing) {
          const t=reservation.existing;
          if(t.state!=='DONE')fail(409,t.state==='RUNNING'?'正在处理原请求，请稍后重试。':'原请求未完成，可能已计费；请核对后重新发起。');
          if(!app.store.analysis(t.analysis))fail(410,'原建议已删除，请重新分析。');
          // Native bridge issues a new short-lived ticket from the cached analysis.
          return send(res,200,await work.run({beforeCall:()=>fail(409,'原结果不可复用，请重新分析。'),onUsage:()=>{}},()=>app.native.handle(req,path,b)));
        }
        active++;
        try{
          const result=await work.run(budget.hooks(b.request_id),()=>app.native.handle(req,path,b));
          budget.finish(b.request_id,result.analysis_id);send(res,200,result);
        }catch(e){budget.finish(b.request_id,null,true);throw e;}finally{active--;}
        return;
      }
      if((path==='/api/native/cancel'||/^\/api\/native\/tickets\/[a-f0-9-]+\/consume$/.test(path))&&req.method==='POST')return send(res,200,await app.native.handle(req,path,b));
      if(path==='/api/native/outcome'&&req.method==='POST')return send(res,200,library(app,account,`/api/native/library/feedback/${text(b.analysis_id,80,true)}/save`,'POST',b));
      fail(404,'接口不存在。');
    }catch(e){if(!res.headersSent)send(res,e.status||500,{error:e.status?e.message:'分析或保存未完成，请稍后重试；原付费请求不会自动重跑。'});}
  });
  server.requestTimeout=15000;server.headersTimeout=10000;
  const maintain=()=>{
    const cutoff=new Date(clock()-30*86400000).toISOString();
    for(const a of auth.all('SELECT id FROM accounts WHERE disabled=0')) {
      const app=application(a.id),s=app.store;
      if([...s.people()].some(p=>app.isActive(p.id)))continue;
      const old=s.all('SELECT DISTINCT person_id FROM analyses WHERE created_at<?',cutoff);
      for(const row of old){const p=s.person(row.person_id);journal(a.id,p);s.tx(()=>purgeDerived(s,p));}
    }
    auth.run('DELETE FROM invites WHERE expires<?',clock()-86400000);
    auth.run('DELETE FROM sessions WHERE absolute_expires<?',clock()-86400000);
  };
  return {server,auth,budget,application,maintain,directory:root,
    close:async()=>{if(server.listening)await new Promise(r=>server.close(r));for(const app of contexts.values())app.store.close();auth.close();unlock();}};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const directory=process.env.LENS_CLOUD_DATA;if(!directory)throw new Error('请配置 LENS_CLOUD_DATA 独立云端目录。');
  const configPath=process.env.LENS_CLOUD_CONFIG;if(!configPath)throw new Error('请配置云端设置文件路径。');
  const config=JSON.parse(readFileSync(configPath,'utf8'));
  const secret=process.env.DASHSCOPE_API_KEY||(process.env.LENS_MODEL_KEY_FILE?readFileSync(process.env.LENS_MODEL_KEY_FILE,'utf8').trim():'');
  if(!/^sk-[A-Za-z0-9_-]+$/.test(secret))throw new Error('请通过服务器密钥文件配置百炼密钥。');
  const app=createCloud({directory,...config,apiKey:secret});
  app.maintain();
  const timer=setInterval(()=>{try{app.maintain();}catch{console.error('Retention maintenance failed');}},3600000);timer.unref();
  app.server.listen(4318,'127.0.0.1',()=>console.log('Cloud native service listening on loopback:4318'));
  const stop=async()=>{clearInterval(timer);await app.close();};process.once('SIGINT',stop);process.once('SIGTERM',stop);
}
