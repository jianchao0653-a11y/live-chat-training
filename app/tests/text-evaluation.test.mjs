import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {loadTextDataset,readContainedFile,digest} from '../evals/dataset.mjs';
import {evaluateText} from '../evals/text-evaluation.mjs';
import {localAnalysis} from '../engine.mjs';

const cliScript=fileURLToPath(new URL('../evals/run.mjs',import.meta.url));
const cliOutputRoot=fileURLToPath(new URL('../../output/evals/',import.meta.url));
const syntheticKey=label=>['sk','synthetic',label].join('-');
function cliEnv(overrides={}) {
  // Do not enumerate or inherit the caller's credential values or NODE_OPTIONS.
  const env={};
  for(const name of ['SystemRoot','WINDIR','TEMP','TMP'])if(process.env[name]!==undefined)env[name]=process.env[name];
  return {...env,...overrides};
}
function runCli(args,env={},nodeArgs=[]) {
  return spawnSync(process.execPath,[...nodeArgs,cliScript,...args],{encoding:'utf8',env:cliEnv(env),timeout:15000});
}
async function cliReport(t,result) {
  assert.equal(result.error,undefined);const summary=JSON.parse(result.stdout);
  // Only remove the unique directory this subprocess just reported under its fixed output root.
  assert.equal(dirname(summary.directory),resolve(cliOutputRoot));
  t.after(()=>rm(summary.directory,{recursive:true,force:true}));
  return {summary,report:JSON.parse(await readFile(join(summary.directory,'report.json'),'utf8'))};
}

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
  const r=runCli(['--manifest','synthetic-secret','--mode']);
  assert.equal(r.status,1);assert(!r.stderr.includes('synthetic-secret'));assert.equal(r.stdout,'');
});

test('CLI default/local/validate ignore missing and non-readable synthetic credential file paths',async t=>{
  const f=await fixture(t),keyDirectory=join(f.root,'synthetic-key-directory');await mkdir(keyDirectory);
  for(const mode of [null,'local','validate'])for(const keyFile of [join(f.root,'synthetic-key-does-not-exist'),keyDirectory]) {
    const args=['--manifest',f.manifestPath,...(mode?['--mode',mode]:[])];
    const r=runCli(args,{LENS_MODEL_KEY_FILE:keyFile,OPENAI_API_KEY:syntheticKey('openai-sentinel'),DASHSCOPE_API_KEY:syntheticKey('bailian-sentinel')});
    assert.equal(r.status,0,r.stderr);const {summary,report}=await cliReport(t,r);
    assert.equal(summary.status,mode==='validate'?'VALIDATED_NOT_EVALUATED':'PASS_MECHANICAL_ONLY');
    assert.equal(report.sourceKind,'external-manifest');assert.equal(report.authorizationRef,'synthetic-permission');
    assert.equal(report.requests,0);assert.equal(report.qualityAccepted,false);
    assert(!r.stdout.includes('sk-synthetic'));assert(!r.stderr.includes(keyFile));
  }
});

test('CLI offline modes never inspect model environment configuration, even with denied access',async t=>{
  const f=await fixture(t),guard=join(f.root,'deny-model-env.mjs');
  await writeFile(guard,`const forbidden=new Set(['LENS_MODEL_PROVIDER','LENS_MODEL_KEY_FILE','OPENAI_API_KEY','DASHSCOPE_API_KEY','LENS_BAILIAN_BASE_URL','LENS_BAILIAN_MODEL','OPENAI_MODEL']);
let accessed=false;const original=process.env;
process.env=new Proxy(original,{get(target,name,receiver){if(forbidden.has(name)){accessed=true;throw new Error('SYNTHETIC_MODEL_ENV_ACCESS_DENIED');}return Reflect.get(target,name,receiver);}});
process.on('beforeExit',()=>{if(accessed)process.exitCode=86;});
globalThis.fetch=()=>{throw new Error('SYNTHETIC_NETWORK_DENIED');};`);
  for(const mode of ['local','validate']) {
    const r=runCli(['--mode',mode,'--manifest',f.manifestPath],{LENS_MODEL_PROVIDER:'synthetic-invalid-provider',LENS_MODEL_KEY_FILE:join(f.root,'synthetic-protected-key')},['--import',pathToFileURL(guard).href]);
    assert.equal(r.status,0,r.stderr);const {report}=await cliReport(t,r);
    assert.equal(report.requests,0);assert.equal(report.cases.length,1);
  }
});

test('CLI live preserves missing-key blocking, key-file errors and manifest authorization without exposing values',async t=>{
  const f=await fixture(t);
  const blocked=runCli(['--mode','live','--manifest',f.manifestPath]);
  assert.equal(blocked.status,2,blocked.stderr);const {report}=await cliReport(t,blocked);
  assert.equal(report.status,'BLOCKED_MISSING_API_KEY');assert.equal(report.requests,0);assert.equal(report.cases[0].status,'NOT_RUN');
  const secretPath=join(f.root,syntheticKey('nonexistent-key-file'));
  const missing=runCli(['--mode','live','--manifest',f.manifestPath],{LENS_MODEL_KEY_FILE:secretPath});
  assert.equal(missing.status,1);assert.equal(missing.stdout,'');assert(!missing.stderr.includes(secretPath));assert(!missing.stderr.includes('sk-synthetic'));
  f.manifest.approvedForCloud=false;await f.save();
  const unapproved=runCli(['--mode','live','--manifest',f.manifestPath],{OPENAI_API_KEY:syntheticKey('not-a-real-credential')});
  assert.equal(unapproved.status,1);assert.equal(unapproved.stdout,'');assert(!unapproved.stderr.includes('sk-synthetic'));
  assert.match(unapproved.stderr,/EVALUATION_INPUT_OR_IO_ERROR/);
});
