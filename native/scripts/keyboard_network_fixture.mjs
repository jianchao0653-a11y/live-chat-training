// Owned synthetic-only transport scenarios around the real cloud handler.
// Only an allowlisted synthetic analyze body is recorded; authorization headers,
// tokens, runtime databases and real accounts are never copied into evidence.
const BODY_KEYS=['person_id','pair_id','context','host','approved','mode','request_id','task_type','text','goal','retry_of','acknowledge_possible_charge'];

export function installNetworkScenario({app,accountId,receipt,save,scenario='keyboard-network'}){
  if(!['keyboard-network','keyboard-retry','keyboard-timeout'].includes(scenario))throw new Error('Unsupported network scenario');
  const handlers=app.server.listeners('request');
  if(handlers.length!==1)throw new Error('Expected one owned cloud handler');
  app.server.removeAllListeners('request');
  const network=receipt.network={scenario,responses:[],requests:[],analyzeRequests:0};
  let dropped=false;
  app.server.on('request',(req,res)=>{
    if(req.method==='POST'&&new URL(req.url,'http://127.0.0.1').pathname==='/api/native/analyze'){
      network.analyzeRequests++;
      if(network.analyzeRequests>4){
        network.fixtureError='TooManyAnalyzeRequests';save();res.destroy();return;
      }
      const ordinal=network.analyzeRequests,chunks=[];
      let bytes=0,requestRecorded=false;
      req.on('data',chunk=>{
        bytes+=chunk.length;
        if(bytes<=2000000)chunks.push(chunk);
      });
      req.on('end',()=>{
        if(requestRecorded)return;
        requestRecorded=true;
        try{
          if(bytes>2000000)throw new Error('Oversized synthetic request');
          const parsed=JSON.parse(Buffer.concat(chunks).toString('utf8'));
          const fields={};
          for(const key of BODY_KEYS)if(Object.hasOwn(parsed,key))fields[key]=parsed[key];
          const unknownKeys=Object.keys(parsed).filter(key=>!BODY_KEYS.includes(key));
          network.requests.push({ordinal,bytes,fields,unknownKeys,receivedAt:new Date().toISOString()});
          save();
        }catch(error){network.fixtureError=error.name;save();res.destroy();}
      });
      if(scenario==='keyboard-timeout'){
        const started=Date.now();
        const close=()=>{
          if(network.timeoutClosedAt)return;
          network.timeoutClosedAt=new Date().toISOString();
          network.timeoutClosedAfterMs=Date.now()-started;
          save();
        };
        res.once('close',close);
        req.once('aborted',close);
        network.timeoutHeld=true;
        network.timeoutReceivedAt=new Date(started).toISOString();
        save();
        return;
      }
      const end=res.end.bind(res);
      res.end=function(chunk,...rest){
        try{
          const raw=String(chunk??'');
          if(raw.length>2000000)throw new Error('Oversized synthetic response');
          const response=JSON.parse(raw);
          const ledger=app.auth.all('SELECT id,state,reserved,charged,calls,analysis FROM tasks WHERE account=? ORDER BY created,id',accountId);
          if(ledger.length>2)throw new Error('Unexpected synthetic ledger size');
          const row={ordinal:network.responses.length+1,status:res.statusCode,
            analysisId:response.analysis_id??null,context:response.context??null,
            budget:response.budget??null,ledger,providerCalls:receipt.calls.length,
            droppedAfterCommit:scenario==='keyboard-network'&&!dropped&&res.statusCode===200};
          network.responses.push(row);
          if(row.droppedAfterCommit){dropped=true;save();res.destroy();return res;}
          save();return end(chunk,...rest);
        }catch(error){network.fixtureError=error.name;save();res.destroy();return res;}
      };
      save();
    }
    void handlers[0].call(app.server,req,res);
  });
}
