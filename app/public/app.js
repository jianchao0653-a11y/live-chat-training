const $ = (s, root = document) => root.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const state = { page: 'workspace', people: [], streamers:[], streamerId:sessionStorage.getItem('lens_streamer') || '0001', config: {}, stats: {}, csrf: '', personId: '', goal: '自然接话', text: '', mode: 'local', result: null, draft: '', busy: false, access: sessionStorage.getItem('lens_access') || '' };
const goals = ['自然接话','关心近况','修复误会','表达边界'];
const outcomeNames = { POSITIVE:'有所帮助', MIXED:'效果一般', NEGATIVE:'需要调整', UNKNOWN:'尚未观察' };
const claimNames = { FACT:'已确认事实', SELF_DECLARED:'对方自述', INFERRED:'待确认推断', DISPUTED:'有争议', EXPIRED:'已过期' };
let toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 5000); }
async function api(path, method = 'GET', data) {
  if (/^(bootstrap|analyses|people\/\d+)$/.test(path)) path += `?streamer_id=${state.streamerId}`;
  if (data !== undefined) data = { ...data, streamer_id:state.streamerId };
  const response = await fetch(`/api/${path}`, { method, headers: { 'Content-Type':'application/json', 'X-CSRF-Token':state.csrf, 'X-Access-Token':state.access }, ...(data !== undefined ? { body:JSON.stringify(data) } : {}) });
  const body = await response.json();
  if (!response.ok) { const e = new Error(body.error || '操作失败'); e.status = response.status; throw e; }
  return body;
}
async function refresh() {
  const b = await api('bootstrap'); state.csrf = b.csrf; state.people = b.people; state.config = b; state.stats = b.stats; state.streamers = b.streamers;
  $('#streamerSelect').innerHTML = b.streamers.map(s=>option(s.id,state.streamerId,`${s.id} · ${s.name}`)).join('');
  if (!state.people.some(p => p.id === state.personId)) state.personId = state.people[0]?.id || '';
  $('#modeBadge').textContent = b.configured ? '模型已接入' : '规则体验模式';
}
function heading(title, sub, action = '') { return `<div class="page-heading"><div><span class="eyebrow">CONVERSATION LENS / 关系智能</span><h1>${title}</h1><p>${sub}</p></div>${action || `<span class="today">${new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</span>`}</div>`; }
function button(text, action, css = 'secondary') { return `<button class="${css}" data-action="${action}">${text}</button>`; }
function option(value, selected, label = value) { return `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>${esc(label)}</option>`; }
const date = (v) => new Date(v).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });

async function navigate(page) {
  if (state.busy) { toast('正在分析，请稍候完成后再切换页面。'); return; }
  state.page = page; document.querySelectorAll('[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  $('#breadcrumb').textContent = `工作区 / ${{ workspace:'对话工作台', people:'人物与关系', history:'分析与复盘', settings:'设置与数据' }[page]}`;
  try {
    if (page === 'workspace') renderWorkspace();
    if (page === 'people') await renderPeople();
    if (page === 'history') await renderHistory();
    if (page === 'settings') renderSettings();
  } catch (e) { toast(e.message); }
}

function renderWorkspace() {
  $('#main').innerHTML = heading('每一次对话，都更懂一点。','从当下的聊天出发，找到有分寸的回应。',button('＋ 新建关系','new-person')) + `
    <div class="stats">
      <div class="stat"><div><small>本主播已建立的关系</small><strong>${state.people.filter(p=>p.pair_id).length.toString().padStart(2,'0')}</strong></div><span class="stat-icon">♧</span></div>
      <div class="stat"><div><small>对话分析记录</small><strong>${state.stats.analyses.toString().padStart(2,'0')}</strong></div><span class="stat-icon">✧</span></div>
      <div class="stat"><div><small>已完成的反馈</small><strong>${state.stats.outcomes.toString().padStart(2,'0')}</strong></div><span class="stat-icon">↗</span></div>
    </div>
    <div class="workspace-grid"><section class="panel input-panel">
      <div class="panel-heading"><h2><span class="step-number">01</span>这次，想聊些什么？</h2><small>CONTEXT</small></div>
      <div class="form-row"><label>选择关系<select id="personSelect">${state.people.length ? state.people.map(p => option(p.id,state.personId,`${p.name} · ${p.id}${p.pair_id?'':' · 待建立关系'}`)).join('') : '<option value="">先新建关系档案</option>'}</select></label><label>聊天平台<input id="platformDisplay" value="${esc(state.people.find(p=>p.id===state.personId)?.platform || '—')}" readonly></label></div>
      <div class="sub-label"><span>这次的沟通目标</span><small>一次专注一件事</small></div>
      <div class="chips">${goals.map(g=>`<button class="chip ${g===state.goal?'selected':''}" data-goal="${g}">${g}</button>`).join('')}</div>
      <div class="input-heading"><label for="chatText">聊天上下文</label>${button('试试示例 ↗','sample','text-button')}</div>
      <div class="textarea-wrap"><textarea id="chatText" maxlength="20000" placeholder="粘贴最近几轮聊天，保留说话人和先后顺序。&#10;&#10;对方：今天忙了一整天，有点累。&#10;我：怎么啦，工作不顺利吗？&#10;对方：没什么，就是想安静一会儿。">${esc(state.text)}</textarea><span class="char-count" id="charCount">${state.text.length} / 20,000</span></div>
      <div class="input-tools">${button('▧ 上传截图','upload','text-button')}<input type="file" id="imageInput" accept="image/png,image/jpeg,image/webp" class="file-hidden"><span>先核对原文，再开始分析</span></div>
      <div class="mode-row"><label for="analysisMode">分析方式<select id="analysisMode">${option('local',state.mode,'本地规则体验')}${option('model',state.mode,'模型深度分析')}</select></label><span>六领域审阅 · 首席策略 · 独立终审</span></div>
      <button id="analyzeButton" data-action="analyze" class="primary analyze-button" ${state.busy?'disabled':''}>${state.busy?'<span class="loading"></span> 正在理解上下文…':'✧ 分析并生成建议'}<span>→</span></button>
      <p class="input-note">建议可自由编辑，发送由你决定</p>
    </section><section class="panel result-panel" id="resultPanel">${renderResult()}</section></div>
    <div class="bottom-strip"><div><strong>6 + 2 个审阅视角</strong>　让建议有依据，也有边界</div><small>证据与记忆 · 情绪与需要 · 长期关系 · 冲突修复 · 边界 · 表达</small></div>`;
}

function renderResult() {
  const a = state.result;
  const head = `<div class="panel-heading"><h2><span class="step-number">02</span>找到合适的回应</h2>${a ? `<span class="result-badge ${a.result.route==='SAFE_STOP'?'warn':''}">${a.mode==='local'?'本地规则':'模型分析'} · ${esc(a.result.route)}</span>` : '<small>INSIGHT & EXPRESSION</small>'}</div>`;
  if (state.busy) return head + '<div class="empty-result"><div class="lens-illustration"></div><h3>正在整理证据与策略</h3><p>模型模式会在生成建议后进行单独终审，请保持页面打开。</p><div class="status-loading"><span class="loading"></span>完成后会自动保存</div></div>';
  if (!a) return head + `<div class="empty-result"><div class="lens-illustration"></div><h3>好回应，从理解开始</h3><p>添加一段聊天，观微会帮你理清情境、选择策略，找到适合自己的表达。</p><div class="empty-flow"><b>看见情境</b>→<b>选择策略</b>→<b>自然表达</b></div></div>`;
  const r = a.result;
  return head + `<p class="summary-line">${esc(r.summary)}</p>
    <div class="strategy-block"><small>本轮策略 / ${esc(a.name || state.people.find(p=>p.id===a.person_id)?.name || '')}</small><h3>${esc(r.strategy)}</h3><p>${esc(r.reason)}</p></div>
    <div class="candidate-heading"><span>${r.candidates.length?'选择一句，改成你的语气':'本轮建议暂停普通回复'}</span><span>${r.candidates.length} 个表达选择</span></div>
    ${r.candidates.map((c,i)=>`<button class="candidate" data-candidate="${i}"><span class="candidate-head"><span>${String(i+1).padStart(2,'0')} / ${esc(c.label)}</span><span>编辑这句 ↗</span></span><p>${esc(c.text)}</p></button>`).join('')}
    <div class="risk">◈ ${esc(r.risk)}</div>
    ${r.expression?`<p class="muted">表达方式：${r.expression.recommended==='TEXT'?'可编辑文字':'暂不回复'} · 手动发送。原生贴纸、语音与图片发送未接入。</p>`:''}
    <details class="review-details"><summary>查看依据与 6 + 2 审核详情</summary>
      ${r.context_receipt?`<div class="review-item"><strong>本轮上下文回执</strong><p>主播 ${esc(r.context_receipt.streamer_id)} · 关系修订 ${r.context_receipt.pair_revision} · ${r.context_receipt.active_memory_ids.length} 条可用记忆 · ${r.context_receipt.excluded_memory_ids.length} 条争议/过期记忆 · ${r.context_receipt.outcome_ids.length} 条近期反馈。</p><small>仅当前关系检索，不上传整个数据库。已否定判断作为限制，不作为事实。</small></div>`:''}
      ${r.behavior?`<div class="review-item"><strong>可观测行为 · 不推测心理</strong><p>我方 ${r.behavior.self_lines} 行，对方 ${r.behavior.other_lines} 行，未知说话人 ${r.behavior.unknown_lines} 行；我方问句 ${r.behavior.self_question_lines} 行。</p><small>${esc(r.behavior.limitation)}</small></div>`:''}
      ${r.strategy_learning?.length?`<div class="review-item"><strong>同关系 × 同目标 × 同情境的反馈</strong>${r.strategy_learning.map(s=>`<p>${esc(s.strategy)}：正面 ${s.positive} / 负面 ${s.negative} / 一般 ${s.mixed} / 未知 ${s.unknown}。实验 Beta(${s.alpha}, ${s.beta})，均值 ${s.experimental_mean.toFixed(3)}，未校准。</p>`).join('')}<small>仅人工观察统计，不是因果效果。一般/未知不算负面；本地规则不据此自动优化措辞。</small></div>`:''}
      <p class="muted">${a.mode==='local'?'规则体验模式：以下为模板化职责检查，不能代表模型或真人专家质量。':'六领域与首席策略合并为一次模型调用，终审使用第二次独立调用。'}</p>
      ${r.evidence.map(e=>`<div class="evidence-quote"><span class="tag">${esc(e.id)} · 原文自述</span> ${esc(e.quote)}</div>`).join('')}
      ${r.reviews.map((v,i)=>`<div class="review-item"><strong>E${i+1} · ${esc(v.role)}</strong><p>${esc(v.conclusion)}</p><small>依据：${esc(v.evidence_refs.join('、'))}</small></div>`).join('')}
      <div class="review-item"><strong>R1 · 首席关系策略师</strong><p>${esc(r.chief.conclusion)}</p><p>${esc(r.chief.conflict)}</p></div>
      <div class="review-item"><strong>R2 · ${esc(r.judge.source)} / ${esc(r.judge.verdict)}</strong><p>${esc(r.judge.reason)}</p></div>
      <div class="review-item"><strong>替代解释</strong><p>${esc(r.alternative)}</p></div>
      ${a.belief?`<div class="review-item"><strong>贝叶斯实验记录 · 未校准</strong><p>${esc(a.belief.proposition)}</p><p>规则证据支持该假设，仍需核实。重复分析不会重复增加证据权重。</p><small>技术参数：先验 ${a.belief.prior}，似然比 ${a.belief.likelihood}，后验 ${Number(a.belief.posterior).toFixed(3)}。这是实验权重，不是对人物的准确概率。</small></div>`:''}
    </details>
    <div class="draft-section"><label for="draftText">我的草稿<textarea id="draftText" maxlength="12000" rows="3" placeholder="选择上面的表达，或写下自己的回应">${esc(state.draft)}</textarea></label>
      ${renderToolbox()}
      <div class="draft-actions">${button('复制草稿','copy','primary')}${button('暂不回复','no-reply')}</div>
      <details class="review-details" ${a.outcome?'open':''}><summary>记录这次对话的后续</summary><div class="feedback"><label>观察到的结果<select id="outcomeStatus">${Object.entries(outcomeNames).map(([k,v])=>option(k,a.outcome?.status || 'UNKNOWN',v)).join('')}</select></label><label>实际发生了什么<textarea id="outcomeNote" rows="2" maxlength="2000" placeholder="例如：对方说想先休息，第二天主动继续聊。">${esc(a.outcome?.note || '')}</textarea></label><div class="draft-actions">${button(a.outcome?'更新反馈':'保存反馈','save-outcome')}</div></div></details>
    </div>`;
}

function renderToolbox() {
  const s = state.streamers.find(s=>s.id===state.streamerId);
  const phrases = (s?.phrases || '').split('\n').map(s=>s.trim()).filter(Boolean);
  const emojis = (s?.emojis || '').split(/\s+/).filter(Boolean);
  return `<details class="review-details"><summary>我的表达素材箱</summary><p class="muted">在设置中登记常用语和表情；点选添加到草稿，仍需本人核对，不代表模型终审已通过。</p><div class="chips">${[...phrases,...emojis].map(t=>`<button class="chip" data-phrase="${esc(t)}">${esc(t)}</button>`).join('') || '尚未登记素材，可到设置中添加。'}</div></details>`;
}

function showPersonForm(person = null) {
  $('#personForm').reset(); $('#personTitle').textContent = person ? '编辑关系档案' : '建立一段关系档案';
  if (person) for (const k of ['id','name','platform','stage','notes','boundary']) $('#personForm').elements[k].value = person[k] || '';
  else $('#personForm').elements.id.value = '';
  $('#personDialog').showModal();
}

async function renderPeople() {
  const p = state.personId ? await api(`people/${state.personId}`) : null;
  $('#main').innerHTML = heading('记住人，也记住关系。','把已知事实与待确认的判断放在各自的位置。',button('＋ 新建关系','new-person')) +
    (p ? `<div class="people-layout"><div class="person-list">${state.people.map(p=>`<button class="person-card ${p.id===state.personId?'selected':''}" data-person="${p.id}"><span class="avatar">${esc(p.name.slice(0,1))}</span><div><strong>${esc(p.name)}</strong><small>${esc(p.platform)} · ${esc(p.stage)}</small></div><span class="person-id">${p.id}</span></button>`).join('')}</div>
    <section class="panel"><div class="profile-top"><span class="avatar">${esc(p.name.slice(0,1))}</span><div><h2>${esc(p.name)}</h2><small>${p.id} · ${esc(p.platform)} · ${esc(p.stage)}</small></div>${button('编辑档案','edit-person','text-button')}</div>
      <div class="profile-section"><h3>当前主播的关系背景</h3>${!p.relationship?'<p class="notice">此人物尚未与当前主播建立关系。点击“编辑档案”保存后开始；不会继承其他主播的私聊记忆。</p>':''}<p>${esc(p.notes || '还没有记录背景。可以先从最近聊到的一件事开始。')}</p></div>
      <div class="profile-section"><h3>表达边界</h3><p>${esc(p.boundary || '尚未登记。')}</p></div>
      <div class="profile-section"><h3>本关系证据与记忆 <small>· ${p.claims.length} 条</small></h3>${p.claims.map(c=>`<div class="claim"><select data-claim-status="${c.id}" aria-label="记忆状态">${Object.entries(claimNames).map(([k,v])=>option(k,c.kind,v)).join('')}</select><div><p>${esc(c.content)}</p><small>来源：${esc(c.source)}</small></div><button class="text-button" data-delete-claim="${c.id}" aria-label="删除记忆">×</button></div>`).join('') || '<p>还没有记忆记录。每条记录都需要来源。</p>'}
      <form id="claimForm" class="claim-form"><select name="kind" aria-label="记忆类型">${Object.entries(claimNames).map(([k,v])=>option(k,'SELF_DECLARED',v)).join('')}</select><input name="content" required maxlength="1000" aria-label="记忆内容" placeholder="一条具体、可核实的信息"><input class="source" name="source" required maxlength="500" aria-label="信息来源" placeholder="来源，例如：9 月 7 日，对方聊天中自述"><button class="secondary" type="submit">＋ 添加记忆</button></form></div>
      <div class="profile-section"><h3>信念与反证</h3><p>保留可反驳的情境判断；当前参数未经过校准。</p>${p.beliefs.map(b=>`<div class="belief-card"><strong>${esc(b.proposition)}</strong><p>${esc(b.evidence)}</p><p>替代解释：${esc(b.alternative)}</p><select data-belief="${b.analysis_id}" aria-label="信念状态">${[['UNCONFIRMED','待确认'],['SUPPORTED','人工确认支持'],['DISPUTED','标记争议 / 反证'],['RETIRED','撤销此假设']].map(([k,v])=>option(k,b.status,v)).join('')}</select><div class="belief-math">实验先验 ${b.prior} · 似然比 ${b.likelihood} · 后验 ${Number(b.posterior).toFixed(3)} · 状态变更不伪造新证据</div></div>`).join('') || '<p>完成聊天分析后，有适用证据时会建立记录。</p>'}</div>
      <div class="profile-section">${button('删除该人物在所有主播下的数据','delete-person','text-button')}</div>
    </section></div>` : `<div class="empty-page"><h2>先认识第一个人</h2><p>档案会从 0001 开始编号。称呼、平台和关系阶段即可开始。</p>${button('建立关系档案','new-person','primary')}</div>`);
  $('#claimForm')?.addEventListener('submit', async e => { e.preventDefault(); try { await api('claims','POST',{ ...Object.fromEntries(new FormData(e.target)), person_id:state.personId }); await refresh(); await renderPeople(); toast('记忆已保存，来源已关联。'); } catch(e) {toast(e.message);} });
}

async function renderHistory() {
  const rows = await api('analyses');
  $('#main').innerHTML = heading('让每一次尝试，都有回响。','回看当时的判断、最终表达与真实发生的结果。') + `<div class="toolbar"><input id="historySearch" placeholder="搜索称呼、平台或沟通目标" aria-label="搜索分析记录"></div><div class="history-list" id="historyList"></div>`;
  const list = (q = '') => {
    const filtered = rows.filter(r => `${r.name} ${r.platform} ${r.goal}`.includes(q));
    $('#historyList').innerHTML = filtered.map(r=>`<button class="history-card" data-analysis="${r.id}"><span class="avatar">${esc(r.name.slice(0,1))}</span><div><strong>${esc(r.name)} <small> / ${esc(r.goal)}</small></strong><p>${esc(r.platform)} · ${date(r.created_at)} · ${r.mode==='local'?'规则体验':'模型分析'}</p></div><span class="tag">${esc(outcomeNames[r.outcome_status] || '待反馈')}</span><span class="arrow">↗</span></button>`).join('') || '<div class="empty-page"><h2>这里会留下对话的线索</h2><p>暂无符合条件的分析记录。</p></div>';
  }; list(); $('#historySearch').addEventListener('input',e=>list(e.target.value));
}

function renderSettings() {
  $('#main').innerHTML = heading('按你的方式，开始测试。','连接模型，查看能力范围，管理本地数据。') + `<div class="settings-grid"><section class="panel"><h2>模型连接</h2><p>接入后可分析复杂对话，并通过两次独立调用完成生成与终审。未接入时可以体验本地基础规则。</p>
    <form id="settingsForm"><label>提供商<input value="OpenAI · Responses API" readonly></label><label>模型名称<input name="model" value="${esc(state.config.model)}" required maxlength="100"></label><label>API Key<input name="key" type="password" autocomplete="off" maxlength="500" placeholder="${state.config.configured?'已配置，留空保留现有密钥':'输入 API Key'}"></label><p class="muted">密钥仅保存在服务器内存，重启后需重新输入，或通过 OPENAI_API_KEY 环境变量配置。模型分析与截图转写会把你提交的内容及所选档案发送到 OpenAI。</p><button class="primary" type="submit">保存模型设置</button> ${button('清除密钥','clear-key','text-button')}</form>
    <div class="notice">当前：${state.config.configured?'已配置密钥；是否可用以实际分析为准':'本地规则体验，可测试操作流程。专业分析需要模型接入。'}</div></section>
    <div><section class="panel"><h2>本版能力</h2>${[['电脑 / 手机浏览器工作台','已实现 · 响应式'],['人物、关系与证据数据库','已实现 · SQLite'],['6+2 分析与独立终审','规则可用 / 模型待连接测试'],['截图转写后人工核对','需图片输入模型'],['反馈与贝叶斯记录','已实现 · 实验参数'],['Android 原生输入法与建议','v0.14 工程预览'],['单帧授权与确认插入','Android 模拟器已验证'],['iPhone 原生入口','已构建 / 真机待验']].map(([k,v])=>`<div class="capability"><span>${k}</span><small>${v}</small></div>`).join('')}</section>
    <section class="panel profile-section"><h2>数据管理</h2><p>这是单人测试工作区，数据库位于本机 runtime/lens.sqlite。导出包括关系、证据、分析和反馈，不包括密钥。</p><div class="draft-actions">${button('导出 JSON','export')}${button('打开人物管理','go-people')}</div><p class="muted">退出服务前可以导出备份。人物删除会级联删除其关联记录，并生成删除回执。</p><div id="exportStatus"></div></section></div></div>`;
  $('#settingsForm').addEventListener('submit',async e=>{e.preventDefault();try{await api('settings','PUT',Object.fromEntries(new FormData(e.target)));await refresh();renderSettings();toast('模型设置已更新。');}catch(e){toast(e.message);}});
  const s = state.streamers.find(s=>s.id===state.streamerId);
  $('#main').insertAdjacentHTML('beforeend',`<section class="panel streamer-profile"><h2>主播 ${esc(s.id)} · 个人表达与输入习惯</h2><p>六个配置位不是六个登录账号；本版仍由玉麒麟在单人工作区管理。人物称呼可共用，关系背景、记忆、反馈按主播分开。</p><form id="streamerForm"><div class="form-row"><label>主播花名<input name="name" value="${esc(s.name)}" required maxlength="60"></label><label>输入习惯（仅登记，尚未接入原生键盘）<select name="input_layout">${option('SYSTEM',s.input_layout,'保留熟悉的系统输入法')}${option('NINE_KEY',s.input_layout,'偏好九键')}${option('QWERTY',s.input_layout,'偏好二十六键')}</select></label></div><label>公开人设、语气与表达偏好<textarea name="tone" maxlength="1000" rows="2" placeholder="例如：简短自然，少用追问，不装熟。不要登记不必要的私人信息。">${esc(s.tone)}</textarea></label><div class="form-row"><label>本人认可的常用语（每行一句）<textarea name="phrases" maxlength="2000" rows="3">${esc(s.phrases)}</textarea></label><label>常用 Unicode 表情（空格分隔）<textarea name="emojis" maxlength="200" rows="3">${esc(s.emojis)}</textarea></label></div><label>主播自己的表达边界<textarea name="boundary" maxlength="1000" rows="2">${esc(s.boundary)}</textarea></label><p class="muted">模型分析时按登记语气生成并终审。本地模式保留规则候选，不伪装成个性化模型输出。平台私有贴纸不作为 Unicode 表情导入。</p><button type="submit" class="primary">保存当前主播配置</button></form></section>`);
  $('#streamerForm').addEventListener('submit',async e=>{e.preventDefault();try{await api(`streamers/${state.streamerId}`,'PUT',Object.fromEntries(new FormData(e.target)));state.result=null;state.draft='';await refresh();renderSettings();toast('主播配置已保存；下一次分析使用新的语气与边界。');}catch(e){toast(e.message);}});
  if(state.config.local) {
    $('#main').insertAdjacentHTML('beforeend',`<section class="panel"><h2>手机设备连接</h2><p>为当前主播 ${esc(s.name)} 配对手机。设备仅能访问这位主播已建立的关系；连接八小时到期，电脑重启服务后需要重新配对。</p><button id="pairDevice" class="primary">生成两分钟配对码</button><p id="pairCode" role="status"></p><div id="deviceList"></div></section>`);
    const pairButton=$('#pairDevice'), pairCode=$('#pairCode');
    pairButton.onclick=async()=>{pairButton.disabled=true;try{const r=await api('devices/pairing','POST',{});if(pairCode.isConnected)pairCode.textContent=`主播 ${r.streamer_id} · 配对码：${r.code} · ${new Date(r.expires_at).toLocaleTimeString()} 前有效 · 仅使用一次`; }catch(e){toast(e.message);}finally{pairButton.disabled=false;}};
    const list=$('#deviceList');
    const refreshDevices=async()=>{try{const r=await api('devices');if(!list.isConnected)return;list.innerHTML=r.devices.map(d=>`<div class="capability"><span>${esc(d.name)} · 主播 ${esc(d.streamer_id)}</span><button data-revoke-device="${esc(d.id)}">撤销连接</button></div>`).join('') || '<p class="muted">暂无已配对设备。</p>';}catch(e){toast(e.message);}};
    list.onclick=async e=>{const b=e.target.closest('[data-revoke-device]');if(!b)return;try{await api(`devices/${b.dataset.revokeDevice}`,'DELETE');await refreshDevices();toast('设备连接已撤销，未使用候选同步失效。');}catch(e){toast(e.message);}};
    refreshDevices();
    const refreshButton=document.createElement('button');refreshButton.textContent='刷新设备列表';refreshButton.onclick=refreshDevices;list.after(refreshButton);
  }
}

async function analyze() {
  if (state.busy) return;
  if (!state.personId) { showPersonForm(); return; }
  if (!state.people.find(p=>p.id===state.personId)?.pair_id) { showPersonForm(await api(`people/${state.personId}`)); toast('先为当前主播建立这段关系，不会复用其他主播的背景。'); return; }
  if (state.text.trim().length < 4) { toast('先粘贴最近几轮聊天，再开始分析。'); $('#chatText').focus(); return; }
  if (state.mode === 'model' && !state.config.configured) { toast('先在设置中连接模型，或选择本地规则体验。'); return; }
  state.busy = true; state.result = null; state.draft = ''; renderWorkspace();
  $('#chatText').disabled = true; $('#personSelect').disabled = true; $('#analysisMode').disabled = true;
  try {
    const a = await api('analyze','POST',{ person_id:state.personId, text:state.text, goal:state.goal, mode:state.mode });
    state.result = a; state.draft = a.outcome?.draft || ''; await refresh();
    toast(a.cached ? '已找到相同分析，复用记录，不重复累计证据。' : '分析已保存，可以选择表达并编辑。');
  } catch(e) { toast(e.message); }
  finally { state.busy = false; renderWorkspace(); }
}

async function extract(file) {
  if (!file) return;
  if (!state.config.configured) { toast('截图识别需要先接入模型。当前可直接粘贴文字。'); return; }
  if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 4_000_000) { toast('请选择小于 4 MB 的 PNG、JPEG 或 WebP 截图。'); return; }
  state.busy = true; $('#analyzeButton').disabled = true; $('#chatText').disabled = true; $('#personSelect').disabled = true; toast('正在转写截图，完成后请核对文字。');
  try {
    const data = await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});
    const r = await api('extract','POST',{image:data});
    state.text = r.text; state.result = null; state.draft = ''; toast(r.warning || '转写完成，请核对说话人与文字后再分析。');
  } catch(e) { toast(e.message); } finally { state.busy = false; renderWorkspace(); }
}

document.addEventListener('click',async e=>{
  const target = e.target.closest('button'); if(!target) return;
  try {
    if (target.dataset.page) return await navigate(target.dataset.page);
    if (state.busy) return;
    if (target.dataset.goal) { state.goal=target.dataset.goal; state.result=null;state.draft='';renderWorkspace();return; }
    if (target.dataset.person) { state.personId=target.dataset.person;state.result=null;state.draft='';return await renderPeople(); }
    if (target.dataset.analysis) { const a=await api(`analyses/${target.dataset.analysis}`); state.result=a; state.personId=a.person_id; state.text=a.input;state.goal=a.goal;state.mode=a.mode;state.draft=a.outcome?.draft || ''; return await navigate('workspace'); }
    if (target.dataset.candidate !== undefined) { state.draft=state.result.result.candidates[Number(target.dataset.candidate)].text; $('#draftText').value=state.draft; $('#draftText').focus(); return; }
    if (target.dataset.phrase !== undefined) { state.draft=(state.draft+target.dataset.phrase).slice(0,12000);$('#draftText').value=state.draft;$('#draftText').focus();return; }
    if (target.dataset.deleteClaim) { await api(`claims/${target.dataset.deleteClaim}`,'DELETE');state.result=null;state.draft='';await refresh();await renderPeople();toast('记忆已删除，旧分析缓存失效；历史分析中的引用不会自动擦除。');return; }
    switch(target.dataset.action){
      case 'new-person':showPersonForm();break;
      case 'edit-person':showPersonForm(await api(`people/${state.personId}`));break;
      case 'go-people':await navigate('people');break;
      case 'analyze':await analyze();break;
      case 'sample':
        { const p=await api('people','POST',{ name:'林间 · 独立示例', platform:'视频号', stage:'熟悉中', notes:'这是合成测试档案，与真实个人无关。用于体验聊天分析流程。', boundary:'尊重休息时间，不以礼物衡量关系。' }); state.personId=p.id; await refresh(); }
        state.text='对方：今天又加班到很晚，有点累。\n我：辛苦了，项目最近很忙吗？\n对方：嗯，事情一直做不完，不太想说话。\n我：那你先休息？\n对方：也不是不想理你，就是想安静一下。'; state.goal='关心近况';state.result=null;state.draft='';renderWorkspace();toast('已填入合成示例，点击分析即可体验。');break;
      case 'upload':$('#imageInput').click();break;
      case 'copy':
        state.draft=$('#draftText').value;
        if(!state.draft.trim()){toast('先选择或填写一段草稿。');break;}
        try{await navigator.clipboard.writeText(state.draft);toast('已复制，可到聊天平台粘贴并手动发送。');}catch{ $('#draftText').focus();$('#draftText').select();toast('浏览器未开放剪贴板，已选中文字，请手动复制。'); }break;
      case 'no-reply':state.draft='';$('#draftText').value='';toast('已清空草稿，可以记录“暂不回复”的后续结果。');break;
      case 'save-outcome':state.result=await api('outcomes','POST',{analysis_id:state.result.id,status:$('#outcomeStatus').value,note:$('#outcomeNote').value,draft:$('#draftText').value});state.draft=$('#draftText').value;await refresh();renderWorkspace();toast('反馈已保存。未观察结果不会被算作负面。');break;
      case 'clear-key':await api('settings','PUT',{clear:true,model:state.config.model});await refresh();renderSettings();toast('服务器内存中的密钥已清除。');break;
      case 'export':{const data=await api('export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`conversation-lens-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出本地数据，不含密钥。');break;}
      case 'delete-person':$('#confirmDialog').showModal();break;
    }
  }catch(e){toast(e.message);}
});
document.addEventListener('input',e=>{
  if(e.target.id==='chatText'){state.text=e.target.value;$('#charCount').textContent=`${state.text.length} / 20,000`;if(state.result){state.result=null;state.draft='';$('#resultPanel').innerHTML=renderResult();}}
  if(e.target.id==='draftText')state.draft=e.target.value;
});
document.addEventListener('change',async e=>{
  try{
    if(e.target.id==='personSelect'){state.personId=e.target.value;state.result=null;state.draft='';$('#platformDisplay').value=state.people.find(p=>p.id===state.personId)?.platform || '—';$('#resultPanel').innerHTML=renderResult();}
    if(e.target.id==='streamerSelect'){
      if(state.busy){e.target.value=state.streamerId;toast('分析期间不能切换主播。');return;}
      state.streamerId=e.target.value;sessionStorage.setItem('lens_streamer',state.streamerId);state.result=null;state.draft='';state.text='';await refresh();await navigate(state.page);
    }
    if(e.target.id==='analysisMode'){state.mode=e.target.value;state.result=null;state.draft='';$('#resultPanel').innerHTML=renderResult();}
    if(e.target.id==='imageInput')await extract(e.target.files[0]);
    if(e.target.dataset.belief){await api('beliefs','PUT',{analysis_id:e.target.dataset.belief,status:e.target.value});state.result=null;state.draft='';toast('状态已更新，原始证据保留；下一轮分析会读取纠正结果。');}
    if(e.target.dataset.claimStatus){await api(`claims/${e.target.dataset.claimStatus}`,'PUT',{kind:e.target.value});state.result=null;state.draft='';toast('记忆状态已更新，旧分析缓存失效。争议/过期内容不再作为事实使用。');}
  }catch(e){toast(e.message);}
});
$('#personForm').addEventListener('submit',async e=>{
  e.preventDefault();const submit=$('button[type="submit"]',e.target);submit.disabled=true;
  try{const data=Object.fromEntries(new FormData(e.target));const p=await api(data.id?`people/${data.id}`:'people',data.id?'PUT':'POST',data);state.personId=p.id;state.result=null;state.draft='';await refresh();$('#personDialog').close();await navigate(state.page);toast(`档案 ${p.id} 已保存。`);}catch(e){toast(e.message);}finally{submit.disabled=false;}
});
$('#closePerson').addEventListener('click',()=>$('#personDialog').close());
$('#modeBadge').addEventListener('click',()=>navigate('settings'));
$('#confirmDialog').addEventListener('close',async()=>{
  if($('#confirmDialog').returnValue!=='delete')return;
  try{const r=await api(`people/${state.personId}`,'DELETE');state.result=null;state.draft='';state.text='';await refresh();await renderPeople();toast(`关联数据已删除。回执：${r.id}`);}catch(e){toast(e.message);}
});

async function boot(){
  try{await refresh();renderWorkspace();}
  catch(e){
    $('#main').innerHTML=heading('连接你的测试工作区','输入服务启动时配置的设备访问口令。')+`<section class="panel"><form id="accessForm"><label>访问口令<input name="token" type="password" autocomplete="off" required></label><div class="draft-actions"><button type="submit" class="primary">连接工作区</button></div><p class="notice">${esc(e.message)}</p></form></section>`;
    $('#accessForm').addEventListener('submit',async e=>{e.preventDefault();state.access=new FormData(e.target).get('token');sessionStorage.setItem('lens_access',state.access);await boot();});
  }
}
await boot();
