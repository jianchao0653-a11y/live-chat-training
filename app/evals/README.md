# 关系建议验收工具

`node app/evals/run.mjs --mode local` 执行 20 个合成回归场景。

`node app/evals/run.mjs --mode live --limit 5` 使用本机环境变量 `OPENAI_API_KEY` 和 `OPENAI_MODEL`；默认 GPT 型号沿用服务配置默认值。每个非停止场景最多两次调用（生成与独立终审）。没有密钥时写入 BLOCKED 回执并以非零退出，不生成假成功报告。真实调用会计费，输出记录实际 usage 与 P50/P95，不虚构费用金额。

合成场景覆盖疲惫、未知说话人、误会、边界、金钱、紧急停止和提示注入。机械检查只验证原文引用、六职责、独立终审来源及停止后无候选。还须两名评审分别标注：说话人、重要事实错误、边界尊重、策略合理性、自然程度和是否可采用；重大分歧解决前保持未验收。

当前 20 个合成场景不是经授权的真实黄金集，不能证明真实关系质量、心理状态或因果效果。正式验收仍需 20–50 组合法脱敏样本与实际 Outcome。

依据：https://developers.openai.com/api/docs/guides/evaluation-best-practices

OCR：`python native/scripts/make_ocr_samples.py` 生成三张原创合成截图；Windows 默认使用微软雅黑，其他系统通过 `LENS_QA_FONT` 指定中文字体。然后 `node app/evals/ocr.mjs --manifest output/evals/ocr-samples/manifest.json` 调用与产品相同的 `/api/extract`，独立内存数据库，逐例记录字符错误率、按行说话人准确率、P50/P95 和真实 usage。没有密钥输出 `ocr-blocked.json`。图片内提示注入也作为普通待转写内容。

自带样本要求 manifest 显式声明 `approvedForCloud: true` 和 `dataClass: synthetic|deidentified`，图片路径限制在清单目录内。清单与运行结果保留本地，不随源码上传；声明不能代替实际取得授权。CER 不等于业务正确率，说话人自动指标按行顺序比较，换行/合并应交双人复核。脚本不自动判定质量通过，也不编造账单。
