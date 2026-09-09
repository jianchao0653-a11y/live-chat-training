// Domain-owned contracts. External memory, OCR and keyboard vendors adapt to these,
// not the other way round. This module never observes a screen or sends a message.
export const CONTEXT_VERSION = 'pair-context-v1';

export function observeConversation(text) {
  const messages = text.split(/\r?\n/).map((raw, i) => {
    const match = raw.trim().match(/^(我|主播|对方|客户|他|她)[：:]\s*(.*)$/u);
    return { id:`M${i + 1}`, speaker:match ? (['我','主播'].includes(match[1]) ? 'SELF' : 'OTHER') : 'UNKNOWN',
      text:match ? match[2] : raw.trim(), timestamp:null, source:'USER_CONFIRMED_TEXT' };
  }).filter(m => m.text);
  const count = speaker => messages.filter(m => m.speaker === speaker).length;
  const own = messages.filter(m => m.speaker === 'SELF');
  return { messages, metrics:{ labeled_lines:messages.length, self_lines:count('SELF'), other_lines:count('OTHER'),
    unknown_lines:count('UNKNOWN'), self_question_lines:own.filter(m => /[?？]/u.test(m.text)).length,
    self_mean_characters:own.length ? Math.round(own.reduce((s,m) => s + [...m.text].length, 0) / own.length) : null,
    response_latency_seconds:null, relationship_trend:'UNKNOWN',
    limitation:'仅统计本次人工确认文本的带标签行，不等于平台消息数；没有时间戳，不计算回复速度、主动率趋势或关系分数。' } };
}

export function strategyLearning(observations = [], goal, situation) {
  const groups = new Map();
  for (const o of observations.filter(o => o.goal === goal && o.situation === situation)) {
    const s = groups.get(o.strategy) || { strategy:o.strategy, positive:0, negative:0, mixed:0, unknown:0 };
    if (o.status === 'POSITIVE') s.positive++;
    if (o.status === 'NEGATIVE') s.negative++;
    if (o.status === 'MIXED') s.mixed++;
    if (o.status === 'UNKNOWN') s.unknown++;
    groups.set(o.strategy, s);
  }
  return [...groups.values()].map(s => ({ ...s, prior_alpha:1, prior_beta:1,
    alpha:1+s.positive, beta:1+s.negative, samples:s.positive+s.negative,
    experimental_mean:(1+s.positive)/(2+s.positive+s.negative), calibrated:false,
    interpretation:'Beta-Bernoulli 实验：人工正/负反馈各计一次；一般/未知不更新。不是因果效果或人物概率。' }));
}

export function packContext(person, text, goal, situation) {
  const observed = observeConversation(text);
  const learning = strategyLearning(person.strategy_observations, goal, situation).slice(0,8);
  // Bounded text, deterministic selection; model sees only this pair, not the full database.
  const compactClaim = c => ({ id:c.id, kind:c.kind, category:c.category||'MEMORY', review_state:c.review_state||'CONFIRMED', content:c.content.slice(0,600), source:c.source.slice(0,200), created_at:c.created_at });
  const streamer = person.streamer ? { id:person.streamer.id, name:person.streamer.name,
    tone:person.streamer.tone, phrases:person.streamer.phrases, emojis:person.streamer.emojis, boundary:person.streamer.boundary,goal:person.streamer.goal||'',tags:person.streamer.tags||'' } : null;
  const context = { id:person.id, name:person.name, platform:person.platform, stage:person.stage,
    notes:person.notes.slice(0,3000), boundary:person.boundary, streamer,
    relationship:person.relationship ? { id:person.relationship.id, streamer_id:person.relationship.streamer_id } : null,
    claims:(person.claims || []).slice(0,8).map(compactClaim),
    excluded_memories:(person.excluded_memories || []).slice(0,8).map(compactClaim),
    beliefs:(person.beliefs || []).slice(0,12).map(b => ({ analysis_id:b.analysis_id, proposition:b.proposition.slice(0,600), status:b.status, alternative:b.alternative.slice(0,400) })),
    outcomes:person.outcomes || [], strategy_learning:learning.slice(0,8), observed_behavior:observed.metrics,
    context_policy:'档案是人工登记；推断不是事实；争议/过期记忆不可采用。撤销/反证优先，不得从旧结果复活已否定判断。历史反馈非本轮原话，不能作为 chat 的证据引用。只有同关系、同目标、同情境反馈可供策略参考，不自动决定策略。' };
  const omitted = {};
  for (const key of ['strategy_learning','outcomes','beliefs','claims','excluded_memories']) {
    while (JSON.stringify(context).length > 24000 && context[key].length) {
      context[key].pop(); omitted[key] = (omitted[key] || 0) + 1;
    }
  }
  return { context, metrics:observed.metrics, learning,
    receipt:{ version:CONTEXT_VERSION, pair_id:person.relationship?.id || null, streamer_id:person.streamer?.id || null,
      pair_revision:person.relationship?.revision || 0, streamer_revision:person.streamer?.revision || 0,
      active_memory_ids:context.claims.map(c=>c.id), excluded_memory_ids:context.excluded_memories.map(c=>c.id),
      outcome_ids:context.outcomes.map(o=>o.analysis_id), reviewed_belief_ids:context.beliefs.map(b=>b.analysis_id),
      context_characters:JSON.stringify(context).length, omitted_for_budget:omitted } };
}

export function expressionPlan(result, person) {
  const stopped = result.route === 'SAFE_STOP' || !result.candidates.length;
  return { recommended:stopped ? 'NO_REPLY' : 'TEXT', editable:true, automatic_send:false,
    choices:stopped ? ['NO_REPLY'] : ['TEXT','NO_REPLY'],
    reason:stopped ? '本轮终审未开放普通回复。' : '优先使用可编辑短文字；是否添加常用表情由本人决定。',
    platform_sticker:{ supported:false, fallback:'请在聊天平台自己的表情面板选择；本版不读取或导入平台专属贴纸。' },
    voice:{ supported:false }, image:{ supported:false },
    persona_applied:result.judge.source === '独立模型调用' && Boolean(person.streamer?.tone),
    note:'本版为保守表达规划；素材箱内容属于人工编辑，不冒充已经过模型终审的候选。' };
}
