# MADR-047：本机验收交付与多机型、多版本兼容性门槛

- 日期：2026-09-09
- 状态：ACCEPTED；用户授权按计划推进，并明确不能只针对单一机型或系统版本。
- 关联：MADR-041、042、044、046；沿用既定 UI 与人工确认发送流程。

## 决策

1. 当前 GitHub 免费 Actions 分钟耗尽，截图显示账单用量为 $0，$12.02 已由折扣抵扣。工作分支改为仅手动选择 service/android/ios/all 执行；不自动购买、不增加费用限额。原 Draft PR 未合并，不把工作分支策略称为默认分支已上线。
2. 本机提供 `本机验收打包.cmd`；底层 `local_delivery.py` 串联检查、合成模拟器测试、HTTPS 边界、构建、已有身份签名及部署源码打包。代理跨 Windows 身份执行时分 prepare/sign，源文件、端点或准备回执变化后必须重做 prepare；不能换签名绕过 DPAPI。
3. ngrok Full Capture 关闭记为用户确认，非代理独立核验。保留既定费用上限与人工发送边界。
4. 产品以 Android 标准能力及实际窗口尺寸适配；小米只是首个真机样本。APK 当前 minSdk 26、targetSdk 36，含 arm64-v8a/x86_64；最低 SDK 声明不等于 Android 8—16 全部测试通过。32 位设备不在当前包范围，不能宣称所有手机可安装；无法运行 Android APK 的系统另行评估。
5. 模拟器首先覆盖 API 26/34/36，按系统行为分层逐步补齐 API 28/30/31/33/35。模拟器不能替代 HyperOS、ColorOS、OriginOS、One UI 等厂商系统真机验证。测试通过必须附 APK 哈希、API、尺寸、密度、字体、测试范围和结果。
6. OCR 解码保留原有1600边长采样作为默认，400万像素/4096边长策略只保留为实验。四尺寸扩展实验验证集均为35/40精确匹配，新策略有分尺寸退步及额外时延，证据不足以默认启用。两者均按图片尺寸计算，不以品牌分支定制。不能把合成文字精度代替实际聊天截图、说话人归属或所有机型精度。
7. 两层门槛：自动化验证 OS/API 与关键业务契约；真机验证安装授权、键盘日常输入、控件可达、屏幕主动识别与人工校对、流量联网及后台恢复。未通过项登记缺口，不将整套兼容性标记完成。

## 可重复执行

先 `python native/scripts/prepare_emulator.py --api 26`（或 34/36）下载校验官方镜像；确保专用 emulator-5556 已停止，再 `python native/scripts/start_emulator.py --api 26`。开机完成后运行 `python native/scripts/compatibility_qa.py --api 26`。只操作本项目命名的 AVD；运行时 API 与传入值不一致即拒绝。不得用该脚本操作个人手机。

兼容性脚本记录三种显示配置的 OCR 校对契约及标准手机配置的云端合成流程；校对契约用程序点击，不能证明每个按钮真实触摸可达。OCR 多尺寸基准使用独立 instrumentation 参数 benchmark=true，质量结果另存；benchmark=PASS 仅表示实验运行完成。

## 证据与限制

- 已阅读 Google 官方系统镜像清单：<https://dl.google.com/android/repository/sys-img/android/sys-img2-3.xml>（2026-09-09），API 26 r01 与 API 34 r04 x86_64 的下载路径及 SHA1 被固定在 prepare_emulator.py；本地安装另外生成 SHA256 回执。该镜像为 AOSP，不代表厂商 ROM。
- 已阅读 Android 图片解码说明：<https://developer.android.com/topic/performance/graphics/load-bitmap>（2026-09-09）；支持先读取尺寸、有界采样，不能单凭该文证明 OCR 提升。
- 已阅读 ML Kit 文档：<https://developers.google.com/ml-kit/vision/text-recognition/v2/android>；识别取决于文字有效像素，不承诺放大图片必然改善结果。
- 已阅读 GitHub workflow 语法：<https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions>；workflow_dispatch 的默认分支注册条件与工作分支修改分别记录。
- 本轮实际验收结果及未完成项以 `07_reviews/V0_17_3_COMPATIBILITY.md` 为准。
