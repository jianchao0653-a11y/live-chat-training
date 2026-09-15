import { randomBytes, randomInt, randomUUID, timingSafeEqual } from 'node:crypto';

const fail = (status, message) => { throw Object.assign(new Error(message), { status }); };
const text = (value, max) => { if (typeof value !== 'string' || !value.trim() || value.length > max) fail(400,'原生请求字段缺失或过长。'); return value.trim(); };
const equal = (a,b) => { const x=Buffer.from(a || ''), y=Buffer.from(b || ''); return x.length===y.length && timingSafeEqual(x,y); };

// Device authority is deliberately memory-only and scoped to one streamer.
// Server restart, expiry or local revocation invalidates every related ticket.
export function createNativeBridge({store, analyze, extract, revision, config, clock=Date.now, authorize,preflight=()=>{}}) {
  const devices=new Map(), tickets=new Map(), leases=new Map();
  let pairing=null;
  const sweep=()=>{
    for(const [id,d] of devices) if(d.expires_at<=clock()) devices.delete(id);
    for(const [id,t] of tickets) if(t.expires_at<=clock() || !devices.has(t.device_id)) tickets.delete(id);
    for(const [id,l] of leases) if(l.expires_at<=clock() || !tickets.has(l.ticket_id)) leases.delete(id);
  };
  const publicDevice=d=>({id:d.id,name:d.name,streamer_id:d.streamer_id,expires_at:d.expires_at});
  const pairInfo=d=>store.person(d.person_id,d.streamer_id);
  function authenticate(req) {
    sweep(); const token=(req.headers.authorization || '').replace(/^Bearer /,'');
    if(authorize) {
      const identity=authorize(token);
      let current=devices.get(identity.id);
      if(!current){current={...identity,token};devices.set(identity.id,current);}
      current.expires_at=identity.expires_at;
      return current;
    }
    const device=[...devices.values()].find(d=>equal(d.token,token));
    if(!device) fail(401,'设备连接已失效，请在电脑上重新配对。');
    return device;
  }
  const assertDevice=d=>{ if(authorize)authorize(d.token); if(devices.get(d.id)!==d || d.expires_at<=clock()) fail(401,'设备授权已撤销或过期。'); };
  function start(d,b) {
    assertDevice(d);
    const context=text(b.context,80), host=text(b.host,200);
    if(!/^[a-zA-Z0-9_.]+$/.test(host)) fail(400,'宿主标识无效。');
    const generation=randomUUID(); d.context={context,host,generation};
    for(const [id,t] of tickets) if(t.device_id===d.id) tickets.delete(id);
    return { context,host, assert:()=>{assertDevice(d);if(d.context?.generation!==generation)fail(409,'输入现场已变化，请重新确认片段。');} };
  }
  function checkTicket(d,id,b) {
    const t=tickets.get(id);
    if(!t || t.device_id!==d.id || t.expires_at<=clock()) fail(410,'候选已过期或已使用，请重新分析。');
    if(t.host!==b.host || t.context!==b.context || d.context?.context!==t.context || d.context?.host!==t.host) fail(409,'候选不属于当前输入现场。');
    const person=pairInfo(t);
    if(!person?.relationship || revision(person)!==t.revision) {tickets.delete(id);fail(409,'关系档案或反馈已更新，请重新分析。');}
    return t;
  }
  function consume(d,id,b){
    assertDevice(d);
    if(b.confirmed!==true)fail(400,'请确认当前聊天人物后插入。');
    const t=checkTicket(d,id,b),draft=text(b.draft,12000);
    if(b.person_id!==t.person_id || b.pair_id!==t.pair_id)fail(409,'人物或关系不一致。');
    const a=store.analysis(t.analysis_id);
    if(!a || a.result.route==='SAFE_STOP' || !a.result.candidates.length)fail(409,'本次分析没有可插入候选。');
    tickets.delete(t.id);sweep();
    return {draft,analysis_id:t.analysis_id,person_id:t.person_id,pair_id:t.pair_id,context:t.context,host:t.host};
  }
  return {
    async manage(path,method,b) {
      sweep();
      if(path==='/api/devices' && method==='GET') return {devices:[...devices.values()].map(publicDevice)};
      if(path==='/api/devices/pairing' && method==='POST') {
        const sid=text(b.streamer_id,4);
        if(!store.streamers().some(s=>s.id===sid))fail(404,'主播不存在。');
        pairing={code:String(randomInt(100000,1000000)),streamer_id:sid,expires_at:clock()+120000,attempts:0};
        return {code:pairing.code,streamer_id:sid,expires_at:pairing.expires_at};
      }
      const match=path.match(/^\/api\/devices\/([a-f0-9-]+)$/);
      if(match && method==='DELETE') {
        devices.delete(match[1]);sweep();return {revoked:true};
      }
      fail(404,'设备接口不存在。');
    },
    async handle(req,path,b) {
      if(path==='/api/native/redeem' && req.method==='POST'){
        sweep();const l=leases.get(b.lease_id);
        if(!l || !equal(l.secret,text(b.secret,100)))fail(410,'短期插入授权已失效，请回主 App 重新生成。');
        if(b.confirmed!==true)fail(400,'请先确认当前聊天人物。');
        leases.delete(l.id);const d=devices.get(l.device_id);
        if(!d)fail(401,'设备授权已撤销。');
        return consume(d,l.ticket_id,{...l.payload,confirmed:true});
      }
      if(path==='/api/native/pair' && req.method==='POST') {
        sweep();
        if(!pairing || pairing.expires_at<=clock() || pairing.attempts>=5)fail(410,'配对码已失效，请在电脑重新生成。');
        pairing.attempts++;
        if(!equal(text(b.code,6),pairing.code))fail(401,'配对码错误。');
        if(devices.size>=6)fail(429,'最多连接六台设备，请先撤销不用的设备。');
        const d={id:randomUUID(),token:randomBytes(32).toString('base64url'),name:text(b.name,60),streamer_id:pairing.streamer_id,expires_at:clock()+8*3600000};
        pairing=null;devices.set(d.id,d);
        return {...publicDevice(d),token:d.token};
      }
      const d=authenticate(req);
      if(path==='/api/native/roster' && req.method==='GET')return {
        device:publicDevice(d),streamer:store.streamers().find(s=>s.id===d.streamer_id),
        people:store.people(d.streamer_id).filter(p=>p.pair_id).map(p=>({id:p.id,name:p.name,platform:p.platform,pair_id:p.pair_id,segment:p.segment})),
        configured:config().configured,
      };
      if(path==='/api/native/cancel' && req.method==='POST') {
        if(d.context?.context===b.context) {d.context=null;for(const [id,t] of tickets)if(t.device_id===d.id)tickets.delete(id);}
        return {cancelled:true};
      }
      if(path==='/api/native/extract' && req.method==='POST') {
        if(b.approved!==true)fail(400,'请先预览并确认图片。');
        const session=start(d,b);const result=await extract(b);session.assert();return result;
      }
      if(path==='/api/native/analyze' && req.method==='POST') {
        if(b.approved!==true)fail(400,'请先核对聊天片段与人物。');
        const p=store.person(text(b.person_id,80),d.streamer_id);
        if(!p?.relationship || b.pair_id!==p.relationship.id)fail(404,'人物不属于设备授权的这段关系。');
        preflight(b);
        const session=start(d,b);
        const result=await analyze({...b,streamer_id:d.streamer_id},session.assert);session.assert();
        const current=store.person(p.id,d.streamer_id);
        const ticket={id:randomUUID(),device_id:d.id,streamer_id:d.streamer_id,person_id:p.id,pair_id:p.relationship.id,
          context:session.context,host:session.host,revision:revision(current),analysis_id:result.id,expires_at:clock()+120000};
        const task_type=result.result.task_type||'REPLY';
        // Preserve the legacy reply contract: a SAFE_STOP ticket is still rejected by consume.
        // Portraits are review records and never receive insertion authority.
        const issuesTicket=task_type==='REPLY'||(task_type==='OPENING'&&result.result.route!=='SAFE_STOP'&&result.result.candidates.length>0);
        if(issuesTicket)tickets.set(ticket.id,ticket);
        return {ticket_id:issuesTicket?ticket.id:null,expires_at:ticket.expires_at,analysis_id:result.id,person:{id:p.id,name:p.name,pair_id:p.relationship.id,segment:current.segment},
          task_type,...(task_type==='REPLY'?{}:{materials:result.result.materials,profile:result.result.profile}),
          mode:result.mode,summary:result.result.summary,route:result.result.route,judge:result.result.judge,
          strategy:result.result.strategy,reason:result.result.reason,risk:result.result.risk,evidence:result.result.evidence,
          candidates:result.result.candidates,context:session.context,host:session.host};
      }
      const match=path.match(/^\/api\/native\/tickets\/([a-f0-9-]+)\/consume$/);
      if(match && req.method==='POST') {
        return consume(d,match[1],b);
      }
      const leaseMatch=path.match(/^\/api\/native\/tickets\/([a-f0-9-]+)\/lease$/);
      if(leaseMatch && req.method==='POST'){
        if(b.approved!==true)fail(400,'请批准要交给键盘的草稿。');
        const t=checkTicket(d,leaseMatch[1],b),draft=text(b.draft,12000);
        if(b.person_id!==t.person_id || b.pair_id!==t.pair_id)fail(409,'人物或关系不一致。');
        for(const [id,l] of leases)if(l.ticket_id===t.id)leases.delete(id);
        const l={id:randomUUID(),secret:randomBytes(32).toString('base64url'),device_id:d.id,ticket_id:t.id,expires_at:Math.min(t.expires_at,clock()+30000),payload:{context:t.context,host:t.host,person_id:t.person_id,pair_id:t.pair_id,draft}};
        leases.set(l.id,l);return {lease_id:l.id,secret:l.secret,expires_at:l.expires_at,draft,person_name:store.person(t.person_id,d.streamer_id).name};
      }
      if(path==='/api/native/outcome' && req.method==='POST') {
        const a=store.analysis(text(b.analysis_id,80));
        if(!a || !store.pair(a.person_id,d.streamer_id) || a.pair_id!==store.pair(a.person_id,d.streamer_id).id)fail(404,'分析不属于此设备授权范围。');
        if(!['POSITIVE','MIXED','NEGATIVE','UNKNOWN'].includes(b.status))fail(400,'反馈状态无效。');
        const note=b.status==='UNKNOWN' && !b.note?'':text(b.note,2000);
        store.saveOutcome(a.id,{status:b.status,note,draft:typeof b.draft==='string'?b.draft.slice(0,12000):''});return {saved:true};
      }
      fail(404,'原生接口不存在。');
    },
  };
}
