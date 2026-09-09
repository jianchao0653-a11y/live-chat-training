# MADR-044：主播身份、九宫拼音与主动屏幕识别

- 日期：2026-09-09
- 状态：ACCEPTED；v0.17.0 测试交付，人工/真机验收待完成
- 授权：用户确认“同意你的建议，分步骤执行完成任务”。

## 决策

一个登录账号对应一位主播；客户、关系、记忆和反馈按账号隔离。先支持小米 Android、微信单聊文字。沿用 MADR-036 的视觉规范与 MADR-041 的电脑后端、固定 HTTPS、单 APK 交付路线。

1. 主播维护称呼、表达风格、常用语、表情、目标、边界和本人标签。编辑档案使旧建议失效，避免继续引用旧信息。
2. 客户标记和记忆保留来源；本人填写、聊天确认、推测、争议和失效分开。推测初始待确认，不进入建议；确认后仍保留推测来源，修改后重新确认。
3. 九宫格复用 librime 和原有 pinyin-simp 字典，以数字拼写映射提供真实候选；支持全键盘切换并保存本机布局偏好。停用学习，不记录日常输入。
4. 主播每次主动发起截图并获得系统授权；中文 OCR 模型随包提供，本机识别，人工校对说话人和文字后才提交分析。保留 FLAG_SECURE；黑屏按受保护内容处理，不视为崩溃、不绕过保护。
5. Android 的输入框信息不能可靠区分同一微信中的不同联系人。每次准备建议和插入时显示客户名称并要求确认；不以头像、标题或输入框标识推断唯一身份。

## 实施顺序与标准

- 档案和关系隔离：跨账号读取、修改、确认均拒绝；重启保留档案；旧建议因修改失效；备份恢复不复活删除的资料。
- 九宫格：真实数字序列产生目标候选并可提交；退格、翻页、全键切换、偏好保持和英文/私密输入回归。
- OCR：打包离线中文模型，取消/超时释放截图，未知说话人可修正；仅批准的文字上传；至少 30 个合成或授权样本评测，真机结果另记。
- 交付：回归通过后迁移前备份；同一正式签名、递增版本号 APK；小米安装升级、离线输入和流量分析由用户真机验收，不以模拟器代替。

## 已有证据与限制

2026-09-09：Node 串行测试 61/61 通过，包含新增档案跨账号隔离/失效、推测确认回归。Android x86_64 调试构建通过；项目 API36 模拟器 Rime 原生测试通过：全键 nihao/zhongguo/xiexie，以及九宫 64426/94664486/943943 候选提交、退格与方案切换。

后续实施已集成随包 OCR，完成 v0.17.0 正式签名测试包与后端更新，详情见 [验收记录](../07_reviews/V0_17_ACCEPTANCE.md)。离线合成30张均可识别，但仅22张逐字一致，精确文字与人工质量未通过。新 schema v2 的严格恢复校验不接受 v1 快照；更新前后各有加密备份，不能放宽 schema 检查来恢复旧快照。

## 技术来源与适用性（2026-09-09 读取）

- https://github.com/rime/home/wiki/SpellingAlgebra ：xlit 等长字符映射与 speller/algebra 规则；本项目原创数字 schema，算法和字典复用原依赖，实际 native smoke 已验证。
- https://developers.google.com/ml-kit/vision/text-recognition/v2/android ：随包中文模型 `com.google.mlkit:text-recognition-chinese:16.0.1`；无首次模型下载要求。尚需验证 AOSP 无 Google Play 环境与小米真机。
- https://dl.google.com/dl/android/maven2/com/google/mlkit/text-recognition-chinese/16.0.1/text-recognition-chinese-16.0.1.pom ：存在传递 AAR 依赖，不能只加一个 Java import；采用标准依赖打包流程前需验证产物与许可。
- https://developer.android.com/build/releases/past-releases/agp-8-13-0-release-notes ：AGP 8.13 支持 API36.1，要求 Gradle8.13；拟以标准 Android 构建处理 OCR 依赖，保留现有 CMake/Rime 产物复用。

构建遇到已记录的 ASCII junction 下 clang Permission denied，沿用此前已验证的外部执行权限方案后成功；不修改防病毒策略。未发现需要更换 Rime 的证据。
