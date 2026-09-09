# v0.15.1 安全收口验收

2026-09-08，承接用户“按计划开展”。[MADR-038](../03_decisions/MADR-038.md)、[部署边界](../app/DEPLOYMENT.md)。

上轮源码 `826617485377105ba7d0bafab2d5b3c1964a5299` 的 [run34174136792](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34174136792) 已核对 service、Android API34/36、iOS 全部成功。本轮修改移动源码，不能借用该结果宣称本轮已验收。

## 本轮变更与待验状态

- SEC-05：Android 本机断开清空私人表单、人物与反馈、恢复对象，重建未连接页面；断开与旋转回归在本地 API36 和云端 API34/36 均通过。
- SEC-06：iOS 异步流按读取量限制、长度前置拒绝、总资源超时和共享文件有界读取/写入；新增 3 项 Swift 测试在 macOS/Xcode Simulator 通过。
- SEC-02：本机新增原生专用端口 4318，所有非 native 路径拒绝。带实际无转发标记/Host 改写的 HTTP 代理、路径规范化、配对、撤销和共享 store 生命周期回归本地通过。管理端口 4317 仍禁止代理，真实 HTTPS 部署待验。
- 新版 0.15.1 / build16；旧 0.15.0 包与 UI 基线保留。无配色布局变更，无真实 GPT/OCR 或真实聊天发送。

本地和云端 Node 全套 37 项通过；Swift/Android 运行结果见下方。发布继续 NOT_READY；真实账号权限、保留/备份治理、六个真机平台组合、模型黄金集双人校准、3 人 7 天试点与签名分发仍未完成。

## 本地 Android 回执

源码 `de4f9e11a9c6304e9108efbfb1b30853b19cc860`；新版 APK `output/native/conversation-lens-0.15.1-debug.apk`，ARM64+x86_64，SHA256 `b0b0511237ca8f83bcf7b57299cbad78874064e0ed59e5d80cbd761afe1d2580`，调试签名和 16 KB 对齐检查通过。旧 v0.15.0 包未覆盖。

项目 API36 模拟器通过 6 项稳定性：旋转保留片段、大字号可达、重建后重新批准、断网无可插入结果、恢复网络后重新分析/插入、**断开后清除片段/反馈且旋转不恢复**。配对/分析/编辑/确认插入和系统 Settings 跨 App 检查也在该流程通过。不是物理手机证据。

`output/security-v0151/` 保存构建、稳定性与断开 UI XML 回执。本次模拟器及内存 fixture 服务已停止，旋转/字体设置恢复。构建脚本中的 `runtimeVerified:false` 只说明该脚本不执行运行验收；运行结论由独立稳定性回执证明。

后续资源与操作：[真机/黄金集/试点执行包](../native/NEXT_ACCEPTANCE_PACKET.md)。截至本轮，环境模型密钥未配置，实际设备/签名/两位评审安排待确认，未调用真实 GPT/OCR。

## 最终云端回执与关闭范围

源码 `de4f9e11a9c6304e9108efbfb1b30853b19cc860`，[run34175618854](https://github.com/jianchao0653-a11y/live-chat-training/actions/runs/34175618854) **四作业全部 success**，私有 Draft PR #3 保持未合并。

| 作业 | 已核对日志证据 |
|---|---|
| service | 37 项 Node 测试通过；20 合成机械场景通过，requests=0，humanReview=PENDING |
| Android API34、API36 | 各 18 项键盘检查、Settings 跨 App 中文、配对/分析/编辑/确认插入、6 项稳定性（含断开与旋转） |
| iOS | 5 项核心测试（原 2＋新增 3），1 项 UI 测试，App/建议扩展构建、启动及截图产物生成成功 |

`output/ci/run-34175618854/` 已保存作业状态、产物元数据和过滤后的验证日志。四份产物已由 GitHub 成功生成，但本机下载文件交付链接返回 **HTTP 403**；没有完成本地 ZIP 归档和 ZIP SHA256 复核。元数据中的 digest 是 GitHub 声明值，不能冒充本机计算结果。临时签名下载请求已删除。云端产物仍可从该 run 页面访问，保留期至 2026-09-15；本地双架构 APK 的哈希与实际运行证据独立可用。

SEC-05/06 的已定位代码缺陷及合成回归已关闭；不宣称完成真机内存攻击、系统全部缓冲清理或所有生命周期验证。SEC-02 的新专用入口通过代理集成测试，实际 HTTPS/证书/upstream 外部验收仍未关闭。模型流量保护、严格恢复及未知字段修复继续通过；不等于多租户或完整生产安全验收。
