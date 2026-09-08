// Text-only Bailian adapter. Credentials are accepted only from server configuration.
export function providerEndpoint(base = 'https://dashscope.aliyuncs.com/compatible-mode/v1') {
  const u = new URL(base);
  if (u.protocol !== 'https:' || u.username || u.password || u.search || u.hash || u.port ||
      !(/^(dashscope(?:-intl|-us)?\.aliyuncs\.com)$/.test(u.hostname) ||
        /^[a-zA-Z0-9-]+\.(cn-beijing|ap-southeast-1|ap-northeast-1|cn-hongkong|eu-central-1|us-east-1)\.maas\.aliyuncs\.com$/.test(u.hostname)) ||
      u.pathname.replace(/\/$/, '') !== '/compatible-mode/v1') throw new Error('百炼服务地址必须是受支持的阿里云 HTTPS 接口。');
  return u.href.replace(/\/$/, '') + '/chat/completions';
}

export async function boundedModelJSON(response) {
  if (Number(response.headers.get('content-length')) > 2_000_000) throw new Error('模型响应过大。');
  const parts=[];let size=0;
  for await (const part of response.body) {
    size+=part.length;if(size>2_000_000)throw new Error('模型响应过大。');parts.push(part);
  }
  return JSON.parse(Buffer.concat(parts).toString('utf8'));
}

export async function bailianCall(config,instructions,input,schema,name,fetcher) {
  if(input.some(i=>typeof i.content!=='string'))throw new Error('百炼首版仅支持文字分析。');
  const checklist=name==='relationship_analysis'?'\n输出前逐项自检：reviews 六项都要有非空 evidence_refs（例如 ["E1"]，前提是 E1 是本次原文证据）。长期关系意见也应锚定当前原话，写清“仅凭此条原话不能判断长期关系”，不能填空数组。不要提供 text 为空的候选；暂不回复写在 alternative，SAFE_STOP 的 candidates 为 []。六项 conclusion 各不超过60字，避免长篇解释。':'';
  const messages=[{role:'system',content:instructions+'\n只返回 JSON 对象，严格遵循以下 JSON Schema（所有字段必填，不添加字段）：'+JSON.stringify(schema)+checklist},...input];
  const maxTokens=name==='independent_judge'?512:4500;
  if(Buffer.byteLength(JSON.stringify(messages))>65_536)throw new Error('模型上下文过长，请缩短片段或人物资料。');
  config.beforeCall?.({maxInputTokens:131072,maxOutputTokens:maxTokens});
  const response=await fetcher(providerEndpoint(config.baseUrl),{
    method:'POST',redirect:'error',signal:AbortSignal.timeout(45000),
    headers:{Authorization:`Bearer ${config.key}`,'Content-Type':'application/json'},
    body:JSON.stringify({model:config.model,messages,max_tokens:maxTokens,stream:false,enable_thinking:false,response_format:{type:'json_object'}})
  });
  if(!response.ok)throw new Error(`百炼模型请求失败（HTTP ${response.status}）。请检查服务端配置或额度。`);
  const body=await boundedModelJSON(response);
  config.onResponse?.(body);
  config.onUsage?.({input_tokens:body.usage?.prompt_tokens,output_tokens:body.usage?.completion_tokens,total_tokens:body.usage?.total_tokens,input_tokens_details:body.usage?.prompt_tokens_details,model:body.model});
  const item=body.choices?.[0];
  if(item?.finish_reason!=='stop'||typeof item?.message?.content!=='string')throw new Error('百炼模型未完成输出，本次不提供建议。');
  return JSON.parse(item.message.content);
}
