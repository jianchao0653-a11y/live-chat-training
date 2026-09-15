// Explicit keyboard-details fixture extension. Only called for a fresh synthetic
// account in the base fixture's owned temporary directory. No runtime data reads.
import {randomUUID} from 'node:crypto';
import {existsSync,readFileSync,statSync} from 'node:fs';
import {join} from 'node:path';
import {localAnalysis} from '../../app/engine.mjs';

export function installDetailsScenario({app,accountId,output,receipt,save,isStopping}){
  const application=app.application(accountId),store=application.store;
  const people={};
  const seeds=[{key:'qahistory',name:'qahistory',notes:''},{key:'qafeedback',name:'qafeedback',notes:''},
    {key:'samewalk',name:'qasame',notes:'合成区分甲：喜欢徒步'},
    {key:'samebake',name:'qasame',notes:'合成区分乙：喜欢烘焙'},
    {key:'qastale',name:'qastale',notes:'合成并发版本核对'}];
  for(const {key,name,notes} of seeds){
    const id=store.createPerson({name,platform:'微信',stage:'初识',segment:'NEW',notes,boundary:'',streamer_id:'0001'},randomUUID());
    people[key]={id,analysisIds:[]};
    if(key.startsWith('same')){
      const person=store.person(id);
      store.addClaim({id:randomUUID(),person_id:id,pair_id:person.relationship.id,kind:'SELF_DECLARED',
        review_state:'CONFIRMED',category:'MEMORY',content:key,source:'合成同名客户隔离验收',created_at:'2026-09-08T10:00:00.000Z'});
    }
  }
  const feedbackPerson=store.person(people.qafeedback.id);
  store.addClaim({id:randomUUID(),person_id:feedbackPerson.id,pair_id:feedbackPerson.relationship.id,
    kind:'SELF_DECLARED',review_state:'CONFIRMED',category:'MEMORY',content:'feedbackkeep',
    source:'合成资料；用于核对反馈删除不会删除记忆',created_at:'2026-09-08T10:00:00.000Z'});
  const materials=[
    {id:'M1',kind:'PROFILE_TEXT',text:'喜欢散步',source:'合成来源甲',observed_at:'2026-09-09'},
    {id:'M2',kind:'MOMENTS_TEXT',text:'喜欢散步',source:'合成来源乙',observed_at:'2026-09-10'}
  ];
  const profile={summary:'合成历史画像：相同原文必须按资料编号追溯。',strategy:'核对每条观察的实际来源。',
    reason:'相同原文不代表相同资料。',risk:'资料自述未作独立核实；推测仍保持待确认。',route:'FAST',
    task_type:'PROFILE',materials,evidence:[
      {id:'E1',source_id:'M1',quote:'喜欢散步',kind:'SELF_DECLARED'},
      {id:'E2',source_id:'M2',quote:'喜欢散步',kind:'SELF_DECLARED'}
    ],profile:{observations:[
      {id:'O1',kind:'SELF_DECLARED',content:'资料自述喜欢散步。',evidence_refs:['E1'],uncertainty:'资料自述尚未独立核实。'},
      {id:'O2',kind:'SELF_DECLARED',content:'资料自述喜欢散步。',evidence_refs:['E2'],uncertainty:'资料自述尚未独立核实。'},
      {id:'OI',kind:'INFERRED',content:'散步可能是可询问的话题。',evidence_refs:['E2'],uncertainty:'不知道对方现在是否仍感兴趣。'}
    ],unknowns:['对方现在是否愿意聊天未知。']},candidates:[],reviews:[],
    chief:{goal:'核对资料',conclusion:'按资料编号核对来源。',conflict:'未知不补写。'},judge:{verdict:'PASS',reason:'合成独立审核。'}};
  function seedAnalysis(name,result,ordinal){
    const person=store.person(people[name].id);
    const analysis=store.saveAnalysis(person,'对方：合成历史片段'+ordinal,'核对合成历史',randomUUID(),
      {...result,customer_revision:application.revision(person)},'CLOUD',null);
    store.run('UPDATE analyses SET created_at=? WHERE id=?',`2026-09-10T10:00:0${ordinal}.000Z`,analysis.id);
    people[name].analysisIds.push(analysis.id);
    return analysis.id;
  }
  const profileId=seedAnalysis('qahistory',profile,1);
  const staleProfileId=seedAnalysis('qastale',profile,1);
  const reply={...localAnalysis('对方：你好',{name:'qafeedback',claims:[]},'自然接话'),task_type:'REPLY'};
  seedAnalysis('qafeedback',{...reply,summary:'合成独立记录乙'},1);
  const feedbackId=seedAnalysis('qafeedback',{...reply,summary:'合成反馈记录甲'},2);
  const details=receipt.details={scenario:'keyboard-details',synthetic:true,people:{},requests:[],faults:[],controlId:0};
  const knownMemories=new Set();
  function snapshot(){
    if(isStopping())return;
    for(const [name,seed] of Object.entries(people)){
      const person=store.person(seed.id),context=store.context(seed.id);
      const claims=person.claims.map(({id,kind,review_state,category,content,source})=>({id,kind,review_state,category,content,source}));
      if(claims.length>10)throw new Error('Synthetic details claim bound exceeded');
      for(const claim of claims)knownMemories.add(claim.id);
      details.people[name]={id:seed.id,name:person.name,notes:person.notes,revision:application.revision(person),claims,
        effectiveClaimIds:context.claims.map(claim=>claim.id),
        analyses:seed.analysisIds.map(id=>store.analysis(id)).filter(Boolean).map(analysis=>({id:analysis.id,
          taskType:analysis.result.task_type,summary:analysis.result.summary,
          stale:analysis.result.customer_revision!==application.revision(person),outcome:analysis.outcome})),
        outcomeEvents:store.get("SELECT COUNT(*) n FROM context_events WHERE pair_id=? AND type='OUTCOME_RECORDED'",person.relationship.id).n};
    }
  }
  snapshot();
  const handlers=app.server.listeners('request');
  if(handlers.length!==1)throw new Error('Details fixture expects exactly one owned cloud handler');
  app.server.removeAllListeners('request');
  let armed=null,failHistory=false;
  const controlPath=join(output,'fixture-control.json');
  function control(){
    if(!existsSync(controlPath))return;
    if(statSync(controlPath).size>1000)throw new Error('Synthetic control exceeds its bound');
    const command=JSON.parse(readFileSync(controlPath,'utf8'));
    if(command.id===details.controlId)return;
    const expected=['profile-drop-response','feedback-refresh-failure','profile-concurrent-revision'][details.controlId];
    if(armed||failHistory||command.id!==details.controlId+1||command.id>3||command.action!==expected)
      throw new Error('Unexpected synthetic details control sequence');
    details.controlId=command.id;armed=command.action;
  }
  function route(path){
    if(path===`/api/native/library/analyses/${profileId}/memories`)return 'profile-adopt';
    if(path===`/api/native/library/analyses/${staleProfileId}/memories`)return 'stale-profile-adopt';
    if(path===`/api/native/library/feedback/${feedbackId}/save`)return 'feedback-save';
    if(path===`/api/native/library/feedback/${feedbackId}/delete`)return 'feedback-delete';
    for(const [name,seed] of Object.entries(people)){
      if(path===`/api/native/library/people/${seed.id}`)return name+'-person';
      if(path===`/api/native/library/people/${seed.id}/history`)return name+'-history';
      for(const id of seed.analysisIds){
        if(path===`/api/native/library/analyses/${id}`)return name+'-analysis';
        if(path===`/api/native/library/analyses/${id}/delete`)return name+'-analysis-delete';
      }
    }
    for(const id of knownMemories)if(path===`/api/native/library/memories/${id}/delete`)return 'memory-delete';
    return null;
  }
  app.server.on('request',(req,res)=>{
    try{
      control();
      const label=route(new URL(req.url,'http://127.0.0.1').pathname);
      let entry=null;
      if(label){
        if(details.requests.length>=160)throw new Error('Synthetic request bound exceeded');
        entry={ordinal:details.requests.length+1,method:req.method,route:label,status:null};
        details.requests.push(entry);
      }
      if(armed==='profile-concurrent-revision'&&req.method==='POST'&&label==='stale-profile-adopt'){
        // Simulate a second authorized client adding ordinary sourced memory
        // after Android rendered its current snapshot. The original cloud
        // handler below must itself compute stale and return the real409.
        armed=null;
        const person=store.person(people.qastale.id),beforeRevision=application.revision(person);
        store.addClaim({id:randomUUID(),person_id:person.id,pair_id:person.relationship.id,
          kind:'SELF_DECLARED',review_state:'CONFIRMED',category:'MEMORY',content:'concurrentreview',
          source:'合成另一端主动提供并保存的资料',created_at:'2026-09-10T11:00:00.000Z'});
        const afterRevision=application.revision(store.person(person.id));
        if(beforeRevision===afterRevision)throw new Error('Synthetic concurrent memory did not advance the customer revision');
        entry.fault='concurrent-memory-before-cloud-validation';
        details.faults.push({action:'profile-concurrent-revision',request:entry.ordinal,applied:true,
          beforeRevision,afterRevision,responseSynthesized:false});
        snapshot();save();
      }
      const end=res.end.bind(res);
      res.end=function(...args){
        if(entry)entry.status=res.statusCode;
        // The real owned cloud handler has already completed its database write.
        // Destroy only this request's socket; never repeat or roll back its POST.
        if(armed==='profile-drop-response'&&req.method==='POST'&&label==='profile-adopt'&&res.statusCode===200){
          armed=null;entry.fault='response-dropped-after-write';
          details.faults.push({action:'profile-drop-response',request:entry.ordinal,applied:true});
          snapshot();save();res.destroy();return res;
        }
        if(armed==='feedback-refresh-failure'&&req.method==='POST'&&label==='feedback-save'&&res.statusCode===200){
          armed=null;failHistory=true;
          details.faults.push({action:'feedback-refresh-failure',request:entry.ordinal,postStatus:200,applied:false});
        }
        snapshot();save();return end(...args);
      };
      if(failHistory&&req.method==='GET'&&label==='qafeedback-history'){
        failHistory=false;entry.fault='post-success-followup-get-503';
        Object.assign(details.faults.at(-1),{applied:true,failedGet:entry.ordinal});
        res.writeHead(503,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
        res.end(JSON.stringify({error:'合成验收：保存后首次历史读取失败。'}));return;
      }
      // No request bodies, headers, tokens or invitations enter the receipt.
      void handlers[0].call(app.server,req,res);
    }catch(error){
      details.fixtureError=error.name;save();
      res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'Synthetic fixture control failed'}));
    }
  });
}
