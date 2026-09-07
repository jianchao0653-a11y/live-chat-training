# v0.15 统一移动 UI 验收

2026-09-07。用户确认清爽浅色＋低饱和绿。设计锁定见 [视觉规范](../02_product/MOBILE_UI_SYSTEM.md) 与 [MADR-036](../03_decisions/MADR-036.md)。

范围：Android 键盘、安装页、连接/片段/图片/候选；iPhone SwiftUI 主 App 和 UIKit 建议扩展。采用共享 token、明确主次按钮、分区、字体和间距。v0.14 原包保留，新包为 `output/native/conversation-lens-0.15.0-debug.apk`。

UI 初轮本地编译、18 项键盘与 Settings 跨 App 中文、配对/分析/编辑/确认插入通过；后续视觉微调和最终源码仍须绑定最终回执。最终哈希、云端运行与可视证据将在下方追加。

工程缺口保持不变：六个真机 OS×聊天平台组合、真实模型/OCR 校准、三人七天首轮试点、签名发布、身份/保留与部署恢复。不以 UI 完成表示整个项目完成。
