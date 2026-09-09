# 观微原生输入现场

这是独立于 v0.11 网页业务工作台的 Android 离线输入测试工程。当前实施阶段：v0.12 原生输入预览；实际构建与运行结果以 [验收记录](../07_reviews/NATIVE_ANDROID_ACCEPTANCE.md) 为准。

## 当前范围

- 原创 Android `InputMethodService`、26 键简体拼音、候选点选与翻页、组合态、退格、英文/符号、换行和系统输入法选择器。
- 真实链接 librime 1.17.0；原样使用 Rime 官方 `rime-pinyin-simp` 的 Apache-2.0 词库。不是自写拼音算法，不复制 Trime 前端。
- 输入引擎在进程内的单一后台队列运行；更换输入框、隐藏键盘或销毁服务使旧结果失效。按键保持顺序，候选刷新期间不可点击旧候选。
- 密码、可见密码、网页密码、数字密码与 `NO_PERSONALIZED_LEARNING` 绕过中文引擎。所有字段均关闭 Rime 用户词库学习。本包没有网络、剪贴板、无障碍或屏幕采集权限。
- 只提交文字到当前编辑框，不调用 `performEditorAction` 或模拟发送按键。单行框“换行”键收起键盘，多行框插入换行；拼音组合中先选词。

这不是完整产品：没有九键、滑行、长按弹层、语音、平台贴纸、AI 建议、与网页档案互通或 MediaProjection。输入速度、词库质量与宿主兼容性需要真实使用测试。Android 最低 API 26、目标 API 36；目标 SDK 不表示最新全部系统或机型已经认证。

## 构建

Windows + JDK 21 + Python 3.12。准备工具只写入本项目 `runtime/`，不更改系统 PATH；使用 Google 官方校验值验证下载，再记录 SHA256。

```powershell
python native/scripts/prepare_tools.py
python native/scripts/prepare_sources.py
python native/scripts/test_policy.py
python native/scripts/build_android.py
```

默认构建 `arm64-v8a`（现代 Android 手机）与 `x86_64`（模拟器）。使用官方 CMake/NDK、aapt2、javac、D8、zipalign、apksigner，无 Gradle/Android Studio 安装前置。所有源码依赖固定在 [dependencies.lock.json](dependencies.lock.json)，不在构建期间联网。

Windows 中文路径会触发旧版 Ninja 响应文件编码问题；构建脚本自动在系统临时目录创建唯一英文目录联接，仍指向本项目。受限沙箱可能需要单独允许经此联接执行编译器。构建目录为 `runtime/native-build-ascii/`。

产物路径：`output/native/conversation-lens-0.12.0-debug.apk`；签名、架构与校验回执：`output/native/build-receipt.json`。使用本机生成的调试签名，仅供本地测试，不作为正式商店发布包。调试签名文件在 `runtime/android-tools/`；保留它才能覆盖安装同签名更新。

## 安装与试打

1. 将 APK 安装到自己的测试手机，打开“观微输入法·测试”。
2. 点击“在系统设置中启用”，由本人启用；再点击“选择观微输入法”。
3. 在内置合成测试框打 `nihao`、`zhongguo`、`xiexie`，选择候选，试退格、翻页、英文、符号与换行。
4. 点击键盘“切换”，随时切回熟悉的输入法。
5. 在真实平台只使用自己批准的合成/脱敏内容，消息仍由本人发送。

首次准备词库在设备本地执行，期间可切换输入法。卸载此独立 APK 会清除其私有词库部署文件，不影响电脑上的 SQLite 业务库。

## 可选模拟器

```powershell
python native/scripts/prepare_emulator.py
```

下载固定的 AOSP API 36 镜像与 Google Android Emulator，约 1.3 GB 压缩文件。模拟器需要可用虚拟化；不自动修改 Hyper-V、BIOS 或安装内核驱动。模拟器只用于合成输入测试，不登录聊天账号。

验证命令（脚本固定只操作 `emulator-5556`）：

```powershell
python native/scripts/start_emulator.py
python native/scripts/build_qa.py
& runtime/android-tools/sdk/platform-tools/adb.exe -s emulator-5556 install -r -t output/native/lens-synthetic-qa.apk
python native/scripts/android_qa.py smoke
python native/scripts/android_qa.py install
python native/scripts/android_qa.py workflow
python native/scripts/android_qa.py cross-app
```

`lens-synthetic-qa.apk` 是独立测试检查器，不要当作产品包安装给试点参与者。测试脚本会在专用模拟器中启用输入法、显示软键盘、重开测试页面和系统设置，全部使用合成文字。完成后运行 `powershell.exe -NoProfile -File native/scripts/stop_emulator.ps1`；脚本核对记录中的 PID 和 LensPreview 命令行后，只关闭本项目模拟器。当前 Emulator 37 的控制台退出命令未可靠生效，因此使用已核对进程的方式停止。

## iPhone 接续边界

保留 MADR-029：主 App/分享或照片入口取得用户批准的上下文、完成网络分析；键盘扩展只插入最小批准文本。键盘默认不直接联网，Open Access 与共享容器能力另行确认。Windows 本轮不能编译、签名或验证 iOS；没有 IPA，也不以 Android 工程替代 iPhone 交付。

## 主要文件

- `android/java/.../LensImeService.java`：输入生命周期、队列、候选与键盘。
- `android/cpp/rime_bridge.cpp`：JNI 适配和引擎会话。
- `android/cpp/rime_smoke.cpp`：实际链接引擎的合成输入检查。
- `android/assets/rime/`：原创最小方案；词典在打包时从已锁定原件复制。
- `scripts/build_android.py`：编译、许可证打包、调试签名与校验。

许可证全文随 APK 与输出目录提供；还包含 libc++、RapidJSON、Darts-clone、utf8cpp、X11 等传递声明。OpenCC 库编译入引擎，但本轮简体方案不启用繁简转换，也不捆绑 OpenCC 词典、Lua 插件或 Trime 代码。
