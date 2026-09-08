import {open,lstat,realpath} from 'node:fs/promises';
import {constants} from 'node:fs';
import {resolve,dirname,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {goals} from '../engine.mjs';

export const digest=value=>createHash('sha256').update(value).digest('hex');
const fail=message=>{throw new Error(message);};
const inside=(root,path)=>{const rel=relative(root,path);return !isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep);};
const object=(v,keys)=>{if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!keys.includes(k)))fail('Invalid dataset object or unknown field');};
const id=v=>{if(typeof v!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(v))fail('Invalid dataset identifier');return v;};
const utf8=bytes=>{try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{fail('Invalid UTF-8 sample');}};

export async function readBoundedFile(path,limit) {
  if(!Number.isSafeInteger(limit)||limit<1)fail('Invalid byte limit');
  const info=await lstat(path);
  if(!info.isFile()||info.isSymbolicLink())fail('Dataset input must be a regular non-link file');
  const handle=await open(path,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
  try {
    const stat=await handle.stat();if(!stat.isFile()||stat.size>limit)fail('Dataset input exceeds byte limit');
    const buffer=Buffer.alloc(limit+1);let length=0;
    while(length<=limit){const {bytesRead}=await handle.read(buffer,length,Math.min(16384,limit+1-length),null);if(!bytesRead)break;length+=bytesRead;}
    if(length>limit)fail('Dataset input exceeds byte limit');return buffer.subarray(0,length);
  } finally {await handle.close();}
}

export async function readContainedFile(root,name,limit) {
  if(typeof name!=='string'||!name||name.includes('\0')||isAbsolute(name)||/^[A-Za-z]:/.test(name)||name.startsWith('\\'))fail('Invalid relative sample path');
  const candidate=resolve(root,name);if(!inside(root,candidate))fail('Sample path escapes dataset directory');
  const canonicalRoot=await realpath(root),canonicalFile=await realpath(candidate);
  if(!inside(canonicalRoot,canonicalFile))fail('Sample link escapes dataset directory');
  if((await lstat(candidate)).isSymbolicLink())fail('Sample links are not accepted');
  return readBoundedFile(canonicalFile,limit);
}

export async function loadTextDataset(manifestPath,{forCloud=false}={}) {
  const path=resolve(manifestPath),root=dirname(path);
  const project=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),canonical=await realpath(path);
  if(['app','native','.github'].some(dir=>inside(resolve(project,dir),canonical)))fail('External datasets must be kept outside source directories');
  const bytes=await readBoundedFile(path,128000);
  let m;try{m=JSON.parse(utf8(bytes));}catch{fail('Invalid manifest JSON');}
  object(m,['version','datasetId','dataClass','approvedForCloud','authorizationRef','reviewPlanId','cases']);
  if(m.version!==1||!['synthetic','deidentified'].includes(m.dataClass)||typeof m.approvedForCloud!=='boolean')fail('Invalid dataset version, data class or cloud approval');
  if(forCloud&&m.approvedForCloud!==true)fail('Explicit cloud approval is required');
  id(m.datasetId);id(m.authorizationRef);id(m.reviewPlanId);
  if(!Array.isArray(m.cases)||m.cases.length<1||m.cases.length>50)fail('Dataset requires 1–50 cases');
  const cases=[],seen=new Set();
  for(const c of m.cases) {
    object(c,['id','textFile','goal','boundary','expectedRoute']);id(c.id);
    if(seen.has(c.id))fail('Duplicate sample identifier');seen.add(c.id);
    if(!goals.includes(c.goal)||!['ANY','SAFE_STOP'].includes(c.expectedRoute)||typeof c.boundary!=='string'||c.boundary.length>1000)fail('Invalid goal, boundary or expected route');
    const text=utf8(await readContainedFile(root,c.textFile,80000));
    if(text.trim().length<4||text.length>20000)fail('Sample text must contain 4–20000 characters');
    const sample={id:c.id,text,goal:c.goal,boundary:c.boundary,route:c.expectedRoute};
    cases.push({...sample,inputHash:digest(JSON.stringify(sample))});
  }
  const manifestHash=digest(bytes);
  return {datasetId:m.datasetId,dataClass:m.dataClass,approvedForCloud:m.approvedForCloud,authorizationRef:m.authorizationRef,
    reviewPlanId:m.reviewPlanId,sourceKind:'external-manifest',manifestHash,
    datasetHash:digest(JSON.stringify({manifestHash,cases:cases.map(c=>c.inputHash)})),cases};
}

export async function loadBuiltinDataset() {
  const bytes=await readBoundedFile(fileURLToPath(new URL('./cases.json',import.meta.url)),128000);
  const cases=JSON.parse(utf8(bytes)).map(c=>{const sample={...c,boundary:'不承诺随时在线，不以消费交换亲密。'};return {...sample,inputHash:digest(JSON.stringify(sample))};});
  return {datasetId:'builtin-synthetic-v1',dataClass:'synthetic',approvedForCloud:true,authorizationRef:'project-synthetic',reviewPlanId:'synthetic-mechanical-v1',sourceKind:'builtin',datasetHash:digest(bytes),cases};
}
