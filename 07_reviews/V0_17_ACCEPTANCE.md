# v0.17.0 分步实施与交付验收

日期：2026-09-09。范围见 MADR-044。状态：可供用户测试的签名升级包；不等于正式生产发布。

## 实现

- 主播档案：称呼、风格、常用表达、表情、目标、边界和本人标签；当前登录主播显示在建议页。更换账号清空片段、图片、客户选择和反馈入口。
- 客户记忆/标记：分类、来源、待确认/确认、修改/删除。推测确认前不进入建议，确认后仍保留 INFERRED 来源，修改后重新确认。编辑档案使旧建议失效；恢复重放清理旧主播资料和派生历史。
- 九宫格：librime 数字拼音 schema，与原字典共用；全键切换、记住偏好、退格/翻页/真实候选提交。修正末行宽度不齐与空候选行空白。
- 主动 OCR：逐次系统授权单帧截图或主动选图；随 APK 提供中文模型。本机识别，输出待核对发言；含待核对标记时禁止分析。人工改为“我：/对方：”并删除非聊天内容后，批准文字上传。保留 FLAG_SECURE。没有后台连续读屏、自动发消息或自动确定微信联系人。
- 标准 Android Gradle 构建负责 AAR/资源/清单和中文模型打包，复用原 CMake/Rime 产物；锁定依赖版本和 SHA256。新版分阶段签名脚本沿用已有正式密钥。

## 实测

| 检查 | 结果与边界 |
|---|---|
| Node 服务回归 | 61/61；新增档案隔离、推测确认、旧建议失效、备份不复活旧档案 |
| 原生输入策略 | 22 条断言通过；帧像素步幅/截断检查通过 |
| Rime 模拟器 | 全键 3 词、九宫 3 词真实候选提交、退格与 schema 切换通过 |
| 九宫界面 | 4 项通过：数字候选、插入、进程重启偏好、切回全键；含签名候选包复测 |
| 手机云端合成流程 | 登录、主播档案、客户/记忆创建、分析、编辑、确认插入、重启登录、修改和删除通过；本地假模型，无百炼调用 |
| 离线 OCR | 无 Google Play 的 AOSP API36 模拟器，网络关闭。30/30 返回文字并要求核对；仅 22/30 与原文逐字一致，精确文字验收 FAIL |
| 正式构建 | assembleRelease 与 Lint vital 通过；依赖校验开启 |
| 正式签名升级 | v0.16 code17 → v0.17 code18 覆盖安装、启动通过；仅项目模拟器 |
| 原生兼容 | ARM64/x86_64；6 个 .so 的 ELF LOAD 对齐均 ≥16 KB，ZIP 对齐通过 |
| 后端更新 | 更新前、后分别加密备份；电脑后端 v0.17，本机与公网 health/library/root/admin 为 200/401/403/403 |

OCR 差异包括“谢谢”简繁混写、“明天”误为“明无/明夭”、“休息”误为“体息”。样本是合成字体、不同字号/位置；不是微信真实聊天质量基准。**离线可用通过、精确文字失败、人工质量未通过三者分开记录。** 当前只适合主播核对后使用，粘贴文字仍可用。

## APK

- `output/native/conversation-lens-0.17.0-cloud-release.apk`，约 36 MiB。
- SHA256：`bd0d19a6ff53a09ec9832dddc6bc59bd95f0616c7e2f578bb4655d112cddadcc`。
- 证书 SHA256：`0ce1d2c5fd366f7b441296fa483a2af20be18f5b5dd1f10c791f6b4eb4cd692e`，与旧正式包一致。
- HTTPS 地址沿用；APK 不包含模型 Key、ngrok token、邀请码或签名私钥。Android API26–36，版本号18。
- 证据：`output/native/release-receipt.json`、`release-upgrade-v017.json`、`elf-v017.json`、`nine-key-receipt.json`、`rime-smoke.txt`、`cloud-ui-receipt.json`、`ocr-offline-test.txt`。

## 故障处理记录（MADR-042）

1. Gradle 缓存锁无法删除：检索 `repo:gradle/gradle Windows Cannot delete file lock junction`，读取 https://github.com/gradle/gradle/pull/38153 。说明路径字符串比较误判同一 junction 锁，采用 canonical path 后消失；没有删持有中的锁。
2. Android 插件中文路径预检查：插件自身输出说明 `android.overridePathCheck=true`。官方旧 issue 跳转未取得有效问题正文，不假称已读到修复；只对 AGP 采用该开关，CMake/Ninja 仍走已验证 ASCII junction，实测 Java/资源/Lint/打包均通过。
3. 首次正式构建 Lint 依赖缺少校验值：报告全部为 missing checksums，未发现已锁哈希不匹配。读取 https://docs.gradle.org/8.13/userguide/dependency_verification.html ，其 detached configurations 段说明不同任务会发现新增依赖；对来自 Google Maven 的31.13.2工具依赖补记录后恢复严格校验。
4. 新 Lint 检出 localhost/127.0.0.1 缺少 includeSubdomains：读取 https://developer.android.com/privacy-and-security/security-config ，显式 false 后通过，不放宽网络范围。
5. DPAPI 备份密钥解码 FormatException：确认 Set-Content 行尾导致原始字符串解析失败，Trim 后成功；密钥从未输出明文。既有签名 DPAPI 沿用原身份，未重建密钥。

## 剩余验收与风险

- 小米实际安装升级、九宫日常选词、微信截图授权/通知返回/受保护画面/跨客户切换，待用户完成。代码无法自动识别同一微信输入框对应哪个客户，必须核对名称。
- OCR 真实截图黄金集、人工质量复核、准确率优化、截图标题/系统消息剔除与结构化逐行校正仍需完善；当前为保守的全文编辑校对。
- ngrok Cloud Traffic Inspector 正文捕获设置仍未独立核实，继续先用虚构聊天试验。
- 小样本真实回复质量、六平台组合与3人7天试点未完成；不以此更新标记整个项目生产完成。
- schema v2 保持严格恢复；升级前 v1 备份需配套旧版恢复流程，升级后另有 v2 加密备份。预算、身份与删除日志不能回滚。DPAPI 备份密钥只在本机账号可用，异机灾备尚未验收。
- 本地没有 Git 元数据；私有仓库同步与新 CI 结果单独记录，不用旧 CI 冒充本版通过。
