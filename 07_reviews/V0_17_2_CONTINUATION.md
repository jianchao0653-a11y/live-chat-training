# v0.17.2 未完成事项续办记录

2026-09-09。此轮新增截图逐条校对，补齐网页示例的浏览器验收，并验证当前真实模型链路。没有宣布整项目上线完成。

## 已完成

1. 截图识别后弹出逐条校对：编辑错字，选择我/对方，排除标题/时间；原识别保留对照，未确认不能回填，回填后需再次批准分析。取消不覆盖已有片段，输入现场过期拒绝回填，FLAG_SECURE保留。
2. `test_policy.py`：原EditorPolicy22断言、FramePixels及新OcrReview边界检查通过；包含未确认、排除、纠错、多行归属、空内容和长度限制。
3. 项目模拟器仪器测试 `OcrTestRunner -e review true`：实际编辑框/选择框操作、未确认拦截、回填、再次批准、取消、过期现场和安全窗口全部PASS。最终回执 `output/continuation-20260909/ocr-review-ui.txt`。
4. Android合成云端UI：登录、主播档案、人物记忆、策略依据、编辑确认插入、实际反馈draft落库、重启与删除全部通过。日志 `cloud-ui.log`。Node71/71及HTTPS Python5项通过。
5. 上轮P2-01补完真实浏览器验收：在独立内存库先建“已有档案·合成”，点击示例自动新建并选中“林间 · 独立示例”；规则分析保存后仅新人物有1条，原人物0条。Playwright快照与独立API断言通过，无私人数据和模型调用。
6. 同原证书签名、16KB zipalign通过；模拟器正式0.17.1→0.17.2覆盖安装、冷启动Status:ok。新版后端正常停服、既有密钥加密备份1账户后升级；既有公网HTTPS健康/权限检查通过。
7. 已批准预算内真实合成smoke通过：生成和终审2调用，账本3790微元（0.00379元）；合成人物已删，测试session撤销、账户停用。回执 `output/evals/pc-live-3374edba-9f1c-4df6-93fe-9d8ec4d08aca.json`。这是链路验证，humanReviewed=false。

## 交付

- `output/native/conversation-lens-0.17.2-cloud-release.apk`，code20，ARM64+x86_64，原HTTPS入口。
- SHA256 `7c4fd4e27a9119b047d8b475744d01b4ab236d80f41a48d93e5d7b59a87a12ce`。
- 原证书SHA256 `0ce1d2c5fd366f7b441296fa483a2af20be18f5b5dd1f10c791f6b4eb4cd692e`。
- 后端包 `output/cloud/conversation-lens-0.17.2-server.zip`，SHA256 `e6e1e837764f610c6e7925373fb3af6d2e7b995201333aa92643cc404248611e`。
- [MADR-046](../03_decisions/MADR-046.md)；手机使用清单在 `output/native/小米实测清单-v0.17.2.md`。

## 尚未完成及下一步

| 事项 | 现在能证明什么 | 仍需什么 |
|---|---|---|
| 小米手机体验 | 模拟器升级、控件、真实服务链路已通过 | 用户实际覆盖安装、关闭Wi-Fi用流量取得首条建议，并测试常用聊天App |
| OCR精确质量 | 已有22/30合成精确匹配；新增校对验证通过 | 授权实际截图的逐字识别/说话人质量集；本次未改识别引擎，不宣称分数提高 |
| 回复质量 | 一次真实合成生成+终审成功 | 人工评审自然度、背景匹配、边界及可用性；3人7天试用不能由脚本替代 |
| GitHub CI | 上轮无runner/无steps的失败已确认；用户Summary错误文字已请求 | 取得具体账户/平台错误后对因处理，不盲目重跑、不自行购买 |
| ngrok正文捕获 | 官方默认元数据、Full Capture主动开启；本地inspect关闭 | 当前账户Full Capture关闭的实际设置核验；浏览器连接工具本轮未能启动 |

持续预算仍20次/日、1元/日、10元/月，不因验收放宽。productionReady=false。所有测试与网页夹具使用合成数据，个人小米未由代理操作。

## 仓库与收尾回执

19个明确源/决策/验收文件已推私有分支 `codex/mobile-acceptance-v014`，源码提交 `e27779367a4aca90ca10d3220860bf7e1e995069`，Draft PR #3保持未合并。本次触发run34326766926，四作业仍未分配runner且无steps即失败，不能记为CI通过，未手工重跑。更新后的文档单独skip ci提交。

Playwright合成快照归档 `output/playwright/v0172-*.yml`，隔离断言回执 `output/continuation-20260909/web-sample-receipt.json`。独立网页夹具、浏览器和模拟器已结束。PC服务PID16332继续运行，以控制器status实时结果为准。
