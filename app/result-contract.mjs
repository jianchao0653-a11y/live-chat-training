// Provider schemas alone do not reject blank or duplicate replies.
export function validateCandidates(candidates) {
  const nonempty=(s,max)=>typeof s==='string' && s.trim().length>0 && s.length<=max;
  const texts=candidates.map(c=>c.text.replace(/[\s，。！？、；：,.!?;:]/gu,'').toLowerCase());
  if(candidates.length<1 || candidates.length>3 || texts.some(s=>!s) || new Set(texts).size!==texts.length ||
    candidates.some(c=>!nonempty(c.label,60)||!nonempty(c.text,1000)))
    throw new Error('建议须为一至三条非空、不同且可编辑的候选。');
}

export function suppressRejectedResult(result,goal) {
  result.route='SAFE_STOP';result.candidates=[];
  result.summary='本轮分析未通过审核。';result.strategy='暂停采用本轮建议';
  result.reason='资料与结论仍需核对，本轮不采用。';
  result.risk='本轮结论不能用于回复或已确认记忆。';
  result.alternative='核对资料来源与当前客户后重新提交，或选择普通输入。';
  result.reviews=result.reviews.map(review=>({...review,conclusion:'本轮分析未通过终审，相关结论不采用。'}));
  result.chief={goal,conclusion:result.strategy,conflict:'来源或边界尚未满足审核要求。'};
  result.judge={...result.judge,verdict:'REJECT',reason:'本轮分析未通过审核，请核对资料与边界。'};
  if(result.profile){result.profile.observations=[];result.profile.unknowns=['本轮结论尚未通过审核，请核对来源与当前客户。'];}
  return result;
}
