# 关系建议验收工具

## 外部黄金文本清单

新入口支持 `--manifest`，先校验整份清单和全部文件，再按 `--limit` 选择样本；后面的未选样本不合法，也不会先发送前面的样本。示例见 `examples/text-manifest.json` 与 `demo-01.txt`，请复制到新的 `output/evals/` 子目录后使用。外部清单不能放在 app/native/.github 源码目录，私人原文不得替换仓库的 `cases.json`。

```powershell
node app/evals/run.mjs --mode validate --manifest output/evals/my-gold/text-manifest.json
node app/evals/run.mjs --mode local --manifest output/evals/my-gold/text-manifest.json
node app/evals/run.mjs --mode live --manifest output/evals/my-gold/text-manifest.json --limit 5
```

`validate` 只校验，不运行分析、不调用模型；`local` 是规则流程；`live` 要求 `approvedForCloud:true`、合法 `dataClass` 和本机密钥。示例默认 false，不视为已批准云端上传。`authorizationRef` 与 `reviewPlanId` 使用不含身份的代号，分别回指本地授权依据与预先冻结的评审方案，声明本身不证明已经取得授权。

外部清单 version=1，1–50 条，ID 唯一；每条包含 id/textFile/goal/boundary/expectedRoute。expectedRoute 仅 ANY 或 SAFE_STOP，ANY 不声称验证 FAST/DEEP 选择正确。文本为 UTF-8，4–20,000 字符且不超过 80 KB；清单最多 128 KB。路径须在清单目录内，绝对路径、目录、文件链接及逃出目录的符号链接/Windows junction 均拒绝。此校验不替代 OS 权限，输入目录必须由可信操作者控制，不保证抵抗并发恶意替换父目录。

每次生成独立 `output/evals/text-UUID/`，含 report.json、review-A.json、review-B.json；重复运行不覆盖旧回执。报告区分 synthetic/deidentified、全量/子集，记录样本/清单摘要、结果摘要和真实返回的 usage（缺少 usage 不冒充完整测量），费用仍为待账单复核。每个选中样本最多两次生成/终审调用，无自动重试；失败仍可能计费。

双人表分别保留 reviewerId 空值和 PENDING，绑定同一运行/报告摘要、输入和结果摘要。它们是待填写模板，不是两名真人已评审的证据；没有自动合并/裁决或质量放行功能。无论机械检查是否通过，qualityAccepted 和 humanReviewed 均保持 false。外部结果可能引用原文，按私人样本保护，勿提交 GitHub；自动保留期/备份清理尚未实现。

OCR 同步使用有界读取与真实路径检查；仍按既有 OCR manifest 契约执行，不改变产品接口或直接读取运行数据库。

文本报告 scope 为 engine-only-minimal-context：只使用样本原文、目标和边界，人物阶段未提供；不读取生产 Pair 的记忆/反馈，也不代表完整生产上下文链路通过。延迟统计包含已尝试的失败样本，不能单凭 P50/P95 判定真实性能已验收。

`node app/evals/run.mjs --mode local` 执行 20 个合成回归场景。

`node app/evals/run.mjs --mode live --limit 5` 使用本机环境变量 `OPENAI_API_KEY` 和 `OPENAI_MODEL`；不带 manifest 时仍使用内置合成场景。没有密钥时在独立运行目录写入 BLOCKED 回执并以退出码 2 结束；输入/IO失败退出 1，控制台不回显原文或密钥。

合成场景覆盖疲惫、未知说话人、误会、边界、金钱、紧急停止和提示注入。机械检查只验证原文引用、六职责、独立终审来源及停止后无候选。还须两名评审分别标注：说话人、重要事实错误、边界尊重、策略合理性、自然程度和是否可采用；重大分歧解决前保持未验收。

当前 20 个合成场景不是经授权的真实黄金集，不能证明真实关系质量、心理状态或因果效果。正式验收仍需 20–50 组合法脱敏样本与实际 Outcome。

依据：https://developers.openai.com/api/docs/guides/evaluation-best-practices

OCR：`python native/scripts/make_ocr_samples.py` 生成三张原创合成截图；Windows 默认使用微软雅黑，其他系统通过 `LENS_QA_FONT` 指定中文字体。然后 `node app/evals/ocr.mjs --manifest output/evals/ocr-samples/manifest.json` 调用与产品相同的 `/api/extract`，独立内存数据库，逐例记录字符错误率、按行说话人准确率、P50/P95 和真实 usage。没有密钥输出 `ocr-blocked.json`。图片内提示注入也作为普通待转写内容。

自带样本要求 manifest 显式声明 `approvedForCloud: true` 和 `dataClass: synthetic|deidentified`，图片路径限制在清单目录内。清单与运行结果保留本地，不随源码上传；声明不能代替实际取得授权。CER 不等于业务正确率，说话人自动指标按行顺序比较，换行/合并应交双人复核。脚本不自动判定质量通过，也不编造账单。
