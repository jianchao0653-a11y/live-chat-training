export function editDistance(expected, actual) {
  const a=Array.from(expected), b=Array.from(actual);
  let row=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=1;i<=a.length;i++) {
    const next=[i];
    for(let j=1;j<=b.length;j++) next[j]=Math.min(next[j-1]+1,row[j]+1,row[j-1]+(a[i-1]===b[j-1]?0:1));
    row=next;
  }
  return row[b.length];
}
export function ocrMetrics(expected, actual) {
  const normalize=s=>s.normalize('NFC').replace(/\s+/gu,'');
  const target=normalize(expected), observed=normalize(actual);
  const speakers=s=>s.split(/\r?\n/).filter(x=>x.trim()).map(x=>x.match(/^\s*([^:：]+)[:：]/)?.[1]?.trim()??null);
  const gold=speakers(expected), read=speakers(actual);
  return {characterErrorRate:editDistance(target,observed)/Math.max(1,Array.from(target).length),exactText:target===observed,
    orderedSpeakerLineAccuracy:gold.filter((s,i)=>s!==null&&s===read[i]).length/Math.max(gold.length,read.length,1),expectedLines:gold.length,actualLines:read.length};
}
