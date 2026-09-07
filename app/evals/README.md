# 关系建议验收工具

`node app/evals/run.mjs --mode local` 执行 20 个合成回归场景。

`node app/evals/run.mjs --mode live --limit 5` 使用本机环境变量 `OPENAI_API_KEY` 和 `OPENAI_MODEL`；默认 GPT 型号沿用服务配置默认值。每个非停止场景最多两次调用（生成与独立终审）。没有密钥时写入 BLOCKED 回执并以非零退出，不生成假成功报告。真实调用会计费，输出记录实际 usage 与 P50/P95，不虚构费用金额。

合成场景覆盖疲惫、未知说话人、误会、边界、金钱、紧急停止和提示注入。机械检查只验证原文引用、六职责、独立终审来源及停止后无候选。还须两名评审分别标注：说话人、重要事实错误、边界尊重、策略合理性、自然程度和是否可采用；重大分歧解决前保持未验收。

当前 20 个合成场景不是经授权的真实黄金集，不能证明真实关系质量、心理状态或因果效果。正式验收仍需 20–50 组合法脱敏样本与实际 Outcome。

依据：https://developers.openai.com/api/docs/guides/evaluation-best-practices
