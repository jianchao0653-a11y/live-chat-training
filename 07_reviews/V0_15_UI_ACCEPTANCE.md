# v0.15 统一移动 UI 验收

2026-09-07。用户确认清爽浅色＋低饱和绿。设计锁定见 [视觉规范](../02_product/MOBILE_UI_SYSTEM.md) 与 [MADR-036](../03_decisions/MADR-036.md)。

范围：Android 键盘、安装页、连接/片段/图片/候选；iPhone SwiftUI 主 App 和 UIKit 建议扩展。采用共享 token、明确主次按钮、分区、字体和间距。v0.14 原包保留，新包为 `output/native/conversation-lens-0.15.0-debug.apk`。

最终本地 APK SHA256：`3a535f4199a1bd424fc33b85d7b9960c29e18191ab0b3ec77ec54c521336d9d9`，ARM64+x86_64，调试签名与 16KB 对齐已核验。v0.14 原包 SHA256 仍为 `c105b72156f7f2971ca0798bd2afc3db9b53b7bbfc6c1e1bce0ca60858c43c14`，没有覆盖。

| 验证 | 结果与边界 |
|---|---|
| 本地 API36 键盘 | 18 项通过：拼音/翻页/连续输入/退格/符号/英文/换行/密码隔离/系统切换等 |
| 原生建议链 | Settings 跨 App 中文、配对、分析、编辑、返回、本人确认单次插入通过 |
| 稳定性 | 旋转保留、1.3倍字体操作可达、重建需新批准、断网无可插入结果、恢复重新分析插入：5项通过 |
| 系统选图 | 原创合成 PNG 真实选择、预览零上传、批准后一次固定 OCR、回填需新批准通过；不是云 OCR 质量 |
| 视觉 | 实际键盘截图人工检查，去除默认阴影、调整第二行缩进、统一导航栏；建议页保持 FLAG_SECURE，交互与控件树验证 |
| 文字对比 | 七组主要文字配色通过 4.5:1；正文13.59、次级5.61、主按钮7.05；不是全面无障碍认证 |

回执与截图：`output/ui-v015/`，包含 `contrast.json`、键盘与密码截图、插入截图及各项哈希回执。[键盘实际截图](../output/ui-v015/android-nihao-candidates.png)。

最终源码提交 `6fbc5a1e49be50824334bba95442ef8e3dac1991`；私有云端 run [34115756817](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34115756817)。此前 `b043085` / run `34114964064` 被包含 iPhone 长草稿滚动修正的新提交替代，工作流按 concurrency 配置取消，不能记为最终通过或产品回归失败。Android 产品源码与本地最终验收包一致。

工程缺口保持不变：六个真机 OS×聊天平台组合、真实模型/OCR 校准、三人七天首轮试点、签名发布、身份/保留与部署恢复。不以 UI 完成表示整个项目完成。


## 最终收口进度

测试修正提交 `ab5ef2379cf13a4aac5f97443dcfbfc0ebae54cd` / run [34116725290](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34116725290) 已四作业全绿。修正针对 API34 建议页异步打开：先等待配对页、确保按钮可见，再填写；仅重试明确的字段未就绪，失败时保存控件树，所有产品断言保留。

实际截图另发现两个对比度问题：Android 导航按钮被系统渲染为白色，iOS 主按钮白字被页面样式覆盖。已分别以 IME 主题/系统栏外观和独立 SwiftUI 主按钮样式修正，未改变整体设计。最终产品提交 `3aa3b7b8c54908669167386f16586aca1302e65b`，run [34117307838](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34117307838)。最终 Android 本地全部回归已重新通过，回执均匹配本文顶部 APK 哈希。云端最终结果在此追加。
