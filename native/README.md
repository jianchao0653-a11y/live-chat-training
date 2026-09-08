# 观微 v0.15 统一 UI 工程预览

最新 v0.16 云端手机首版见 [MADR-040](../03_decisions/MADR-040.md)、[验收](../07_reviews/CLOUD_V016_ACCEPTANCE.md)、[部署](deploy/README.md)。已实现邀请码登录与手机人物管理，云端调试包仅内置本地测试地址；生产域名、签名、小米真机和七天试点未完成。下方为原电脑服务模式说明。

v0.15.1 安全补丁已通过本地与云端合成验收：[新版双架构 APK](../output/native/conversation-lens-0.15.1-debug.apk)、[本轮回执](../07_reviews/V0_15_1_SECURITY_ACCEPTANCE.md)。SHA256 `b0b0511237ca8f83bcf7b57299cbad78874064e0ed59e5d80cbd761afe1d2580`。下方 0.15.0 安装包仍是历史 UI 基线；真机和生产发布未通过。

新增 [视觉规范](../02_product/MOBILE_UI_SYSTEM.md)、[MADR-036](../03_decisions/MADR-036.md) 和 [v0.15 UI 验收](../07_reviews/V0_15_UI_ACCEPTANCE.md)。[当前 Android 包](../output/native/conversation-lens-0.15.0-debug.apk)；下方 v0.14 包保留为功能基线。

[Android 安装包](../output/native/conversation-lens-0.14.0-debug.apk) · [v0.14 验收与剩余工作](../07_reviews/V0_14_ACCEPTANCE.md) · [iPhone 工程](ios/README.md) · [v0.13 历史验收](../07_reviews/V0_13_ACCEPTANCE.md)

v0.14 增加 Android 旋转/大字号恢复、截图帧边界检查、断网恢复验收，以及 iPhone 主 App 和建议键盘扩展。iOS 已在私有仓库 GitHub macOS/Xcode 模拟器完成首次构建、核心测试和启动；真实签名安装、共享容器、完全访问与三平台插入仍待验。云端矩阵见 [PR #3](https://github.com/jianchao0653-a11y/live-chat-training/pull/3)，不把模拟器通过视为真机完成。

保留真实 librime 1.17.0 简体拼音、候选与翻页、英文/符号、退格和系统键盘切换。新增限定主播的设备配对、聊天片段分析、编辑候选、返回原输入框后确认插入，以及实际后续反馈。不会替用户点击发送。

截图采用 MediaProjection：每次申请系统授权，3 秒后仅保留一帧，立即释放投屏与前台服务。完成通知打开预览，只有点击“批准此图并提交转写”才联网识别；转写文字必须人工校对并再次批准分析。也可通过系统文件选择器选择一张截图。

## 连接电脑与手机

1. 电脑执行 `npm.cmd start`，打开 http://localhost:4317 ，选择当前主播并建立人物关系。模型与密钥只在电脑服务中配置；规则试算无需密钥。
2. 在自己的测试手机安装 APK，打开观微，按页面提示启用并选择输入法。
3. 当前最直接的连接方式是 USB 调试转发。开启手机开发者选项中的 USB 调试，连接电脑，在手机确认这台电脑，然后运行：

   ```powershell
   & runtime/android-tools/sdk/platform-tools/adb.exe reverse tcp:4317 tcp:4318
   ```

   多设备连接时为 adb 添加 `-s 设备序列号`。测试结束可运行 `adb reverse --remove tcp:4317` 并关闭 USB 调试。此步骤不会自动读取聊天。

4. 电脑“设置与数据 → 手机设备连接”生成配对码。Android 打开“连接分析服务”，填写 `http://127.0.0.1:4317` 与六位配对码，点击配对；iPhone 连接方式见 iOS 工程说明。
5. 回到实际聊天输入框，点击键盘“建议”，核对人物、目标及你主动粘贴的片段。选择规则试算或 GPT 分析，明确批准后提交。
6. 选择候选，可修改文字。点击“保留草稿并返回原聊天”；再次确认正在与按钮中所列人物聊天，然后插入。检查文字并自行发送。
7. 后续再次打开建议，可记录上次插入对应的实际观察。未发送或尚未收到回应时使用“未知”，不得把插入当作积极反馈。

局域网明文 HTTP 地址不被 Android 客户端接受。远程连接必须使用系统信任的 HTTPS 服务根地址，客户端拒绝重定向和证书绕过；HTTPS 部署、手机厂商兼容性不属于本次已验证范围。USB 转发实测仅限项目模拟器，物理手机仍需现场测试。

HTTPS upstream 仅允许指向原生专用端口 4318；不要转发管理工作区 4317。见 [部署边界](../app/DEPLOYMENT.md)。

## 截图使用

从聊天输入框进入建议，点击“截取一次屏幕”。允许通知后重新点击截图，在系统对话框选择单个应用或整屏。授权后建议界面退到后台，3 秒后截一帧，通知提供停止和预览入口。通知被禁用时不开始截图。

截取结束点击通知预览图片。确认画面正确且可以提交后再批准转写。系统限制捕获的页面可能是空白；可以丢弃或改用主动选择图片，不绕过受保护窗口。默认没有麦克风、后台持续录屏、无障碍读取或剪贴板采集。

截图最长边最多 1600 像素；选择文件最大 15 MB，解码时缩小。图片与草稿只保存在进程内存，输入现场最长 15 分钟；取消、失效或退出进程后丢弃。建议界面禁止系统截图与最近任务缩略图；QA 截图因此不展示该界面的图片像素。

## 授权与失效

- 配对码两分钟有效、一次使用，最多五次错误尝试；最多六台设备，每台仅授权一个主播，最长八小时。
- 服务重启、授权到期或电脑撤销设备后必须重新配对。手机设备令牌使用 Android Keystore AES-GCM 加密，保存在应用私有的 no-backup 目录；不把模型 API Key 放入 APK。
- 候选票据两分钟有效、只消费一次。服务端检查人物、关系、上下文、宿主、档案修订与停止结论；前后两次校验 Android 编辑框，防止网络返回时插入另一个输入框。
- 切换实际编辑框、改人物/目标/片段、在原输入框继续键入，会使旧建议失效。密码、NO_PERSONALIZED_LEARNING、号码、邮箱、网址等输入框不提供建议入口。
- Android 无法可靠判断同一个聊天 App、同一个编辑框 ID 当前对应哪个人物。因此每次插入必须由本人确认人物；不能宣称自动防止同 App 切换聊天造成的人物混淆。
- 插入不自动写入正向反馈；只记录本人实际观察。六个主播配置位不是多租户登录。

批准分析的文字与结果由电脑现有 SQLite 服务持久化。图片本身不写入项目数据库/文件；云服务保留政策与本地数据库的保留期、备份、磁盘加密仍需单独治理。

## 构建与合成测试

Android 最低 API 26、目标 API 36，ARM64 与 x86_64 双架构。Windows + JDK 21 + Python 3.12 + Node 24；工具和依赖已固定在项目 `runtime/`。首次获取工具参考历史说明，后续构建不需要网络。

```powershell
python native/scripts/build_android.py
python native/scripts/test_policy.py
npm.cmd test
python native/scripts/start_emulator.py
python native/scripts/build_qa.py
& runtime/android-tools/sdk/platform-tools/adb.exe -s emulator-5556 install -r -t output/native/lens-synthetic-qa.apk
python native/scripts/android_qa.py install
python native/scripts/android_qa.py workflow
python native/scripts/android_qa.py cross-app
```

`native_fixture.mjs` 只创建内存合成数据库，OCR 为明确标记的固定夹具。`assistant_qa.py` 提供 pair/analyze/insert 操作与 UI 辅助函数，仅操作 `emulator-5556`。真实云端质量、时延与费用未由这些测试验证。

测试完成运行 `powershell.exe -NoProfile -File native/scripts/stop_emulator.ps1`，只停止经 PID 和命令行核对的本项目模拟器。QA APK 是独立的测试检查器，不向使用者分发。

Windows 中文路径下构建会通过经核对的临时 ASCII 联接运行工具，仍写回本项目。调试签名用于本地试用，保留 `runtime/android-tools/lens-local-debug.keystore` 以便同签名升级。依赖许可证随 APK 和输出目录提供。

## 尚未完成

ARM64 仅完成构建和 16 KB 对齐，未在物理手机运行。抖音、快手、微信真机兼容性、九键、横屏和大字号覆盖、语音及平台贴纸、真实 GPT/OCR 验收仍待完成。iPhone 工程已在 macOS/Xcode Simulator 完成构建与核心/UI 测试；尚无签名 IPA 和物理设备验收。
