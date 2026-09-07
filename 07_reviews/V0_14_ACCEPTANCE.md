# v0.14 四项推进与工程验收

日期：2026-09-07。本轮基于 v0.13，用户指定 `jianchao0653-a11y/live-chat-training` 私有仓库。状态：双端工程预览，**未达到生产发布或完整真人试点验收**。

## 已实现与验证

| 工作流 | 本轮交付 | 已有证据 | 尚未关闭 |
|---|---|---|---|
| Android 稳定性 | 横竖屏/大字号保留片段、重新批准；帧 stride/末行边界检查；截图服务启动失败处理 | 本地 API 36，18 项键盘回归、跨 App 中文与配对/分析/编辑/确认插入；5 项稳定性；JVM 22 断言与帧测试 | 真机厂商差异、单 App 捕获裁剪、真实相册、长时间后台 |
| 环境验收 | GitHub Ubuntu KVM + 官方 Android API 34/36；macOS 15 + Xcode 26.3 Simulator；真机版本矩阵采集脚本 | 私有 PR #3、工作流实际执行；iOS 首次 App/键盘构建、两项核心测试及启动通过 | 六个真机 OS×平台组合均 NOT_RUN；云端最终结果见下方 CI 回执 |
| GPT/OCR | 20 个合成文本场景；真实生成/独立终审用量跟踪；OCR 产品接口、3 张合成图、字符错误率/说话人/时延指标 | 本地机械文本检查通过；OCR 指标单测通过；无密钥生成 BLOCKED 回执 | 实际模型调用、20–50 组合法脱敏黄金样本、双人校准与费用核对 |
| iPhone 与保障 | SwiftUI 配对/文字/照片/候选、Keychain、建议扩展、30 秒单次可撤销授权；备份校验与恢复到新文件；发布缺口检查 | iOS 首次云端构建/核心测试/启动；服务端短授权重放、篡改、过期、撤销测试；隔离恢复测试 | 完全访问/App Group/签名真机、平台插入、完整键盘与分享扩展（未实现）、多人身份/自动保留期/备份删除 |

服务端本地 **30 项测试通过**。这些测试包含固定模型夹具，不代表真实模型质量。iOS 只提供建议插入与切回系统键盘，不宣称拥有完整拼音键盘。当前 App 照片选择入口可用源码已构建，独立系统分享扩展尚未实现。

## 构建与回执

新增本地系统文件选择器实测：`output/native/picker-receipt.json`。通过真实 DocumentsUI 浏览并选择原创合成 PNG，预览零上传，明确批准后恰好一次固定 OCR 夹具调用，转写回填后复选框未批准。此项补足模拟器真实选文件流程；不代表物理相册/云 OCR/单 App 捕获裁剪已验收。

- APK：`output/native/conversation-lens-0.14.0-debug.apk`，ARM64 + x86_64，minSdk 26/targetSdk 36。
- 本地 APK SHA256：`c105b72156f7f2971ca0798bd2afc3db9b53b7bbfc6c1e1bce0ca60858c43c14`。
- `output/native/build-receipt.json` 仅记录构建；其中 `runtimeVerified:false` 不被构建脚本改成运行通过。运行证据另见 `ci-native-receipt.json`、`stability-receipt.json`。
- `output/evals/local-report.json`：合成机械检查；`live-blocked.json`、`ocr-blocked.json`：缺少 API Key，不是 FAIL 品质结论。
- `native/release-readiness.json` 与 `output/release/readiness.json`：16 个发布验收包均未全部关闭；这是 DoD 清单，不是项目完成百分比。
- 私有 [PR #3](https://github.com/jianchao0653-a11y/live-chat-training/pull/3)，分支 `codex/mobile-acceptance-v014`。仅白名单源码、合成测试与工程文档；未上传私人聊天、SQLite、备份或密钥。
- 首轮 [34106837637](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34106837637)：service/iOS 成功，Android 失败在 sdkmanager 路径；已修复。
- 第二轮 [34107857991](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34107857991)：修复后实际重跑，最终结果继续登记在本文件的追加记录。
- 第四轮 [34110111177](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34110111177)：iOS App/键盘编译、两项核心测试与一项真实 UI 回归通过；UI 验证输入后明确批准、修改片段取消批准、断开连接清空片段。Android 最终矩阵和最新源代码结果以最终追加记录为准。

## 工程距离：用未闭合验收包量化

按 V 模型，单元/集成/系统测试分别证明实现、接口与受控环境行为；相关真机与真人观察才对应使用需求。Android 与服务的受控原型可类比 TRL 4，属于工程判断而非正式认证；不能把局部成熟度平移到双端整体。

当前关键路径：双端稳定性与 iOS 签名、真实 GPT/OCR 校准 → **6 个真实 OS×平台组合** → **首轮 3 人×7 天** → 修正并扩展另外 3 人 → 身份、保留/删除/恢复及发布评审。黄金集应有 **20–50 组合法脱敏样本和两名评审**。首轮观察本身至少七个自然日，尚未开始；这不包含准备、修复和下一轮，也不是总交付时长承诺。

缺少 WBS 权重、稳定交付速率与外部资源日期，报告“完成 90%”没有工程依据。准确结论是：**主要原型链路已形成，仍需真实环境、质量、运行保障与试点四类证据收口**。模拟器已消除本地没有 Mac 的编译障碍，不能消除第三方 App 限制、物理设备与签名的验收要求。

## 运行保障边界

六个主播配置位和限定主播的设备令牌不是六个认证租户。多人授权模型尚未实现，不把共享口令当作账户隔离。主数据按人物删除已有级联与测试，但备份可能含已删除内容，自动保留期及备份清理尚未实现。恢复模块仅对一致性快照做完整性/外键/应用表检查，复制到全新路径，不覆盖或激活运行库；真实部署仍需恢复演练。

本轮没有打开或修改 `runtime/lens.sqlite`，没有处理私人 TXT/ZIP/备份。全部端到端数据是合成、内存服务。没有实际调用 GPT/OCR，没有发送真实聊天消息。

## 决策和借鉴

[MADR-032–035](../03_decisions/MADR-032-035.md) 记录证据关闭、GitHub 模拟器、iOS 短授权和工程距离方法。[复用清单](../01_inputs/REFERENCE_REUSE_V014.md) 区分真实依赖、方法借鉴和候选库。
