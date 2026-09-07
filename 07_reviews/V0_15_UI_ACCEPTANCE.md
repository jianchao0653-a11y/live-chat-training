# v0.15 统一移动 UI 验收

2026-09-07。用户确认「清爽浅色＋低饱和绿」。**最终源码与四个云端作业通过**：[run 34119039965](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34119039965)，源码 `a867e11ea9f62c808ab9170688f34630930ebcec`。状态：可供安装体验的工程预览；未达到真机/生产发布验收。

## 交付

Android 键盘、安装页、设备连接、人物/片段/图片/候选页面，以及 iPhone 主 App 和建议扩展，采用共同颜色角色、字体层级、间距、圆角和主次操作。键盘工具栏减少占高、第二行字母缩进、人物确认展开全宽。iPhone 长草稿使用可滚动预览，主按钮独立白字样式；Android 显式采用深色导航区域与浅色系统图标。

设计锁定见 [视觉规范 1.0](../02_product/MOBILE_UI_SYSTEM.md) 和 [MADR-036](../03_decisions/MADR-036.md)。后续按可复现的可读性、误触、裁切或平台缺陷修改共享样式，避免零散改色。

## 验证与产物

| 验证 | 最终结果与边界 |
|---|---|
| Android API34 / API36 云端 | 两个作业均 success；每个18项键盘、Settings跨App中文、配对/分析/编辑/返回/本人确认插入，以及5项稳定性通过 |
| Android 本地 API36 | 最终双架构包通过上述流程及系统选图；回执全部匹配最终 APK 哈希 |
| 系统选图 | 原创合成 PNG 真实选取、预览零上传、批准后一次固定 OCR、回填需新批准；不是云 OCR 质量 |
| iPhone | 主 App+建议扩展构建，2核心+1 UI测试、安装启动通过；导出页面就绪后的 XCTest 截图 |
| 服务 | 30项测试与20个合成文本机械场景通过；不是模型质量验收 |
| 可读性 | 七组主要文字配色均≥4.5:1；主按钮白字7.05:1，导航白色图标6.03:1；实际双端画面检查，非全面无障碍认证 |

本地安装包：[conversation-lens-0.15.0-debug.apk](../output/native/conversation-lens-0.15.0-debug.apk)，ARM64+x86_64；SHA256 `ce7637f446201e144902b183df26523ee14e19a55841222be4fd5f6ac385cb0a`。调试签名与16KB对齐已核验。保留 v0.14 APK，SHA256 `c105b72156f7f2971ca0798bd2afc3db9b53b7bbfc6c1e1bce0ca60858c43c14`。

云端 API34 APK SHA256 `fb81db5b60713c580880900bf90fed87f32963f17ca4d929b768d6d4e3005496`；API36 `1ba4cfd3446491aaec012e850af3182a0750ae0e373b0ee4c2360c63a98c9e19`。每个 runner 的临时调试签名不同，不能混用哈希。

iOS环境：iPhone SE (3rd generation) / com.apple.CoreSimulator.SimRuntime.iOS-26-2 / Xcode26.3。模拟器 App tar.gz SHA256 `4c089b4385d4c0d985f9fe9d580a578e10a4284d5ed5f1ac82eb0a28e58eb62f`，不是签名 IPA。

四份云端产物与 jobs/artifacts 元数据在 `output/ci/run-34119039965/`，ZIP均与GitHub digest核对。本地截图和对比计算在 `output/ui-v015/`；[Android实际截图](../output/ui-v015/android-nihao-candidates.png)、[iPhone实际截图](../output/ui-v015/ios-connection.png)。Android建议页保持 FLAG_SECURE，以控件树、操作可达性与批准流程检查，不关闭保护截图。

## 验收中修正的问题

API34建议页打开时序使旧测试过早填写：改为页面/按钮就绪等待，仅重试明确的字段未就绪，保留原断言并在失败时存控件树。独立 run34116725290 已四作业通过。

实际截图发现 Android 导航图标模式与本地不同、iOS主按钮受父页面文字色影响：分别固定深色导航区域/浅色图标、隔离主按钮样式。simctl启动命令早于首帧，因此增加页面就绪后的XCTest截图导出。历史中途取消或中间截图不替代本次最终结果。

## 工程距离

UI体系与受控原型已落地；仍缺六个真机 Android/iPhone×抖音/快手/微信组合，真实GPT/OCR与20–50合法脱敏黄金样本/双人校准、首轮3人×7天及修复后扩3人、身份隔离/保留与备份删除/部署恢复/签名发布。iPhone扩展不是完整拼音键盘，完整扩展真机交互与无障碍仍待验。`native/release-readiness.json` 维持 NOT_READY，不用完成百分比掩盖这些缺口。

四项工程成果与实际复用账本仍见 [v0.14验收](V0_14_ACCEPTANCE.md)、[MADR032–035](../03_decisions/MADR-032-035.md) 和 [参考复用清单](../01_inputs/REFERENCE_REUSE_V014.md)。v0.14原功能基线 run34112887861 四作业全绿已归档。
