import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {loadTextDataset,readContainedFile,digest} from '../evals/dataset.mjs';
import {evaluateText} from '../evals/text-evaluation.mjs';
import {localAnalysis} from '../engine.mjs';

const chat='对方：今天加班很累，想安静休息。';
async function fixture(t) {
  const root=await mkdtemp(join(tmpdir(),'lens-gold-'));assert.equal(dirname(root),tmpdir());
  t.after(()=>rm(root,{recursive:true,force:true}));
  const dir=join(root,'dataset');await mkdir(dir);
  const manifestPath=join(dir,'manifest.json'),textPath=join(dir,'one.txt');await writeFile(textPath,chat);
  const manifest={version:1,datasetId:'synthetic-test',dataClass:'synthetic',approvedForCloud:true,authorizationRef:'synthetic-permission',reviewPlanId:'review-v1',cases:[{id:'one',textFile:'one.txt',goal:'关心近况',boundary:'尊重休息时间',expectedRoute:'ANY'}]};
  const save=()=>writeFile(manifestPath,JSON.stringify(manifest));await save();
  return {root,dir,textPath,manifestPath,manifest,save,options:{manifestPath,outputRoot:join(root,'results')}};
}

test('external evaluation preserves data class, hashes and two pending independent review forms',async t=>{
  const f=await fixture(t);f.manifest.dataClass='deidentified';await f.save();
  let calls=0;
  const a=await evaluateText({...f.options,fetcher:()=>{calls++;throw new Error('must not call');}});
  assert.equal(calls,0);assert.equal(a.report.synthetic,false);assert.equal(a.report.status,'PASS_MECHANICAL_ONLY');assert.equal(a.report.qualityAccepted,false);
  const original=await readFile(join(a.directory,'report.json'),'utf8');
  for(const slot of ['A','B']) {
    const review=JSON.parse(await readFile(join(a.directory,'review-'+slot+'.json'),'utf8'));
    assert.equal(review.slot,slot);assert.equal(review.status,'PENDING');assert.equal(review.reviewerId,null);
    assert.equal(review.reportHash,digest(original));assert.equal(review.cases[0].inputHash,a.report.cases[0].inputHash);
    assert.equal(review.cases[0].outputHash,a.report.cases[0].outputHash);assert.equal(review.cases[0].decision,null);
  }
  await writeFile(f.textPath,chat+'合成新片段');const b=await evaluateText(f.options);
  assert.notEqual(a.directory,b.directory);assert.notEqual(a.report.datasetHash,b.report.datasetHash);
  assert.equal(await readFile(join(a.directory,'report.json'),'utf8'),original);
});

test('unapproved cloud input and invalid unselected cases issue zero provider calls',async t=>{
  const f=await fixture(t);let calls=0;const options={...f.options,mode:'live',apiKey:'synthetic',fetcher:()=>{calls++;throw new Error('must not call');}};
  f.manifest.approvedForCloud=false;await f.save();await assert.rejects(()=>evaluateText(options),/approval/);
  assert.equal((await evaluateText({...f.options,mode:'validate'})).report.status,'VALIDATED_NOT_EVALUATED');
  f.manifest.approvedForCloud=true;f.manifest.cases.push({...f.manifest.cases[0],id:'two',textFile:'missing.txt'});await f.save();
  await assert.rejects(()=>evaluateText({...options,limit:1}));assert.equal(calls,0);
});

test('manifest rejects duplicate IDs, unknown fields, invalid goals and missing authorization references',async t=>{
  const f=await fixture(t),original=structuredClone(f.manifest);
  for(const mutate of [m=>m.cases.push(m.cases[0]),m=>m.qualityAccepted=true,m=>m.cases[0].goal='invalid',m=>delete m.authorizationRef,m=>m.cases[0].expectedRoute='PASS']){
    Object.keys(f.manifest).forEach(k=>delete f.manifest[k]);Object.assign(f.manifest,structuredClone(original));mutate(f.manifest);await f.save();
    await assert.rejects(()=>loadTextDataset(f.manifestPath));
  }
});

test('file readers reject lexical and directory-link escape paths for text and OCR',async t=>{
  const f=await fixture(t),outside=join(f.root,'outside');await mkdir(outside);await writeFile(join(outside,'sample.txt'),'合成外部文本');
  for(const path of ['../outside/sample.txt',join(outside,'sample.txt')])await assert.rejects(()=>readContainedFile(f.dir,path,100),/path|escapes/);
  await symlink(outside,join(f.dir,'linked'),process.platform==='win32'?'junction':'dir');
  await assert.rejects(()=>readContainedFile(f.dir,'linked/sample.txt',100),/escapes/);
});

test('dataset preflight bounds bytes and characters, rejects bad UTF-8 and non-files',async t=>{
  const f=await fixture(t);
  for(const value of ['字'.repeat(20001),Buffer.alloc(80001,65),Buffer.from([0xff,0xff]),'']){
    await writeFile(f.textPath,value);await assert.rejects(()=>loadTextDataset(f.manifestPath));
  }
  f.manifest.cases[0].textFile='.';await f.save();await assert.rejects(()=>loadTextDataset(f.manifestPath));
  await writeFile(f.manifestPath,' '.repeat(128001));await assert.rejects(()=>loadTextDataset(f.manifestPath),/limit/);
});

test('live mode without key records blocked cases and validate mode never invokes provider',async t=>{
  const f=await fixture(t);let calls=0;const fetcher=()=>{calls++;throw new Error('must not call');};
  const blocked=await evaluateText({...f.options,mode:'live',fetcher});
  assert.equal(blocked.report.status,'BLOCKED_MISSING_API_KEY');assert.equal(blocked.report.cases[0].status,'NOT_RUN');
  const valid=await evaluateText({...f.options,mode:'validate',apiKey:'synthetic',fetcher});
  assert.equal(valid.report.status,'VALIDATED_NOT_EVALUATED');assert.equal(valid.report.latency,null);assert.equal(calls,0);
});

test('live fixture calls independent judge, tracks observed usage and never auto-accepts quality',async t=>{
  const f=await fixture(t);let calls=0;const {judge,...analysis}=localAnalysis(chat,{name:'样本人物',claims:[]},'关心近况');
  const fetcher=async()=>{calls++;return new Response(JSON.stringify({status:'completed',usage:{input_tokens:10,output_tokens:5},output:[{content:[{type:'output_text',text:JSON.stringify(calls===1?analysis:{verdict:'REJECT',reason:'合成终审拒绝'})}]}]}));};
  const {report}=await evaluateText({...f.options,mode:'live',apiKey:'synthetic-key',fetcher});
  assert.equal(calls,2);assert.equal(report.requests,2);assert.equal(report.usage.reportedCalls,2);assert.equal(report.usage.input_tokens,20);
  assert.equal(report.cases[0].output.route,'SAFE_STOP');assert.deepEqual(report.cases[0].output.candidates,[]);
  assert.equal(report.cases[0].checks.independentJudge,true);assert.equal(report.qualityAccepted,false);assert.equal(report.humanReviewed,false);
});

test('CLI rejects malformed arguments without printing supplied sensitive values',()=>{
  const script=fileURLToPath(new URL('../evals/run.mjs',import.meta.url));
  const r=spawnSync(process.execPath,[script,'--manifest','synthetic-secret','--mode'],{encoding:'utf8',env:{...process.env,OPENAI_API_KEY:''}});
  assert.equal(r.status,1);assert(!r.stderr.includes('synthetic-secret'));assert.equal(r.stdout,'');
});
