# 云端手机首版部署包（v0.16.0）

尚未部署到真实服务器。生产域名、TLS证书和预算仍需实际配置；本地生产签名身份已准备，尚未签出正式APK，示例配置默认禁止付费调用。
用户手机只安装 APK、邀请码登录并启用输入法。下面步骤由项目维护者执行。

当前个人电脑先行试点以 [MADR-041](../../03_decisions/MADR-041.md) 为准：电脑运行服务，固定公网HTTPS仅代理4318；手机只安装本项目APK，无需Tailscale。暂缓付费托管采购。连接验收见 [PC_HTTPS_ACCEPTANCE](../../07_reviews/PC_HTTPS_ACCEPTANCE.md)。PC_PILOT中的私人网络方案仅为历史记录。

前期采用托管服务与平台HTTPS域名的准备方案见 [HOSTED_PILOT.md](HOSTED_PILOT.md)，Blueprint为 `render.yaml`。该方案尚待账号和预算后创建；以下systemd步骤用于自管Linux，不要在托管平台直接照搬。

## 服务

使用 Linux + Node.js 24，单个服务进程；云端账户各有独立 SQLite 文件，身份/删除/费用账本独立存放。不接触原电脑 `runtime/lens.sqlite`，不自动迁移私人数据。

1. 建立专用 `lens` 系统用户，源码放 `/opt/conversation-lens`，其只需读取源码。
2. 创建 `/etc/conversation-lens` 与 `/var/lib/conversation-lens`，配置文件/数据仅授予维护者与 `lens` 必要权限，数据目录模式0700，密钥文件0600。Node 24 位于 `/usr/bin/node`；其他位置须同步修改 unit。
3. 将 `cloud-config.example.json` 复制成 `/etc/conversation-lens/cloud-config.json`。确认百炼地域、模型及当前费率。`inputPerMillion` / `outputPerMillion` 是每百万 token 价格换算的“微元”：1元=1,000,000微元。采用覆盖实际地域/模型/长度档位的最高适用费率，不依赖缓存折扣。记录核价来源和日期，填写日/月金额上限后才将 `verified` 设为 true。0或未核价会禁止模型调用。
4. `/etc/conversation-lens/model-key` 只放模型密钥，不放注释。不得将模型密钥写进 APK、源码或 Nginx 配置。
5. 单独产生32字节随机备份密钥，以64位十六进制存入 `/etc/conversation-lens/backup-key`，不与备份文件放在一起。保管生产密钥和签名密钥，纳入运维交接。
6. 安装附带的 systemd service/timer。先启动 `lens-cloud.service`，确认只有 `127.0.0.1:4318` 监听；此服务完全不启动4317管理工作区。
7. 配置真实域名、系统信任的 TLS 证书和 Nginx，唯一 upstream 为4318。安全组只开放必要的443和受限运维入口。验证配置后启动每日备份 timer。
8. 用手机 Wi-Fi 与移动网络各执行一次完整授权分析。证书续期、重启后恢复和外部路径拒绝必须实测。

邀请码由维护者在服务器产生（有效24小时、一次使用）：

```bash
node --disable-warning=ExperimentalWarning app/cloud-admin.mjs invite /var/lib/conversation-lens/data
```

只把邀请码私下交给对应试用者。找回账号时在末尾加原 `account_id`，生成新的邀请码；激活时撤销旧设备。单账号首版保留一个活跃设备。登录滑动有效30天、绝对有效180天，之后重新发邀请码。退出登录撤销当前设备，不等于删除云端人物。

## 费用和失败

每人每天默认20次，按UTC日切换。单进程全账号最多2个分析工作流；每次最多生成+终审两次调用。账本在请求前预留两调用的保守用量预算（每调用131072输入/6000输出token）。百炼文字请求另限序列化上下文65536字节、生成4500/终审512输出token，非思考模式。

账本金额是按配置费率核算的估计，不是供应商发票。未报告用量、超时或崩溃保留预留。实际用量超过配置上界时暂停新分析，必须人工核账。相同人物资料和片段的重复请求，包括旋转后换请求编号，不重复发起未知状态的付费任务。不是通用任意模型/工具计费系统。

必须配置供应商侧额度/账单监测；别的程序使用同一密钥的费用不属于本服务预算。示例未声称核实当前模型价格。模型别名变动或费率变化时重新核价并验收。

## 保留、删除和恢复

人物与确认记忆保留至用户删除；分析及反馈最多30天，启动和每小时清理。清理某人物过期分析时会同时清除其派生历史，避免残留副本。修改人物背景或既有记忆会清除该人物旧分析与反馈；界面操作前明确确认。新增记忆不清空历史；首次新增反馈可累积，修改既有反馈清除其他派生历史。

每日04:00短暂停服务，生成 AES-256-GCM 加密备份并清除超过7天的本工具备份；失败通过 systemd 状态检查，必须告警处理。`lens-backup.service` 的启停必须在真实 systemd 环境演练；当前只通过程序级合成验证。

备份仅包含人物数据库。身份、费用和删除账本是恢复时必需的**当前权威状态**，不能回滚到旧备份。须另行保护该状态文件与磁盘；若整台服务器丢失且无法取得最新账本，工具拒绝仅凭历史人物备份恢复。此限制避免删除数据重新出现，但尚不等于灾难容灾方案。

恢复到新目录，现有目录不可覆盖，先停止服务：

```bash
node --disable-warning=ExperimentalWarning app/cloud-admin.mjs restore /var/lib/conversation-lens/data /var/lib/conversation-lens/backups/SELECTED.lensbackup /var/lib/conversation-lens/recovered-NEW
```

工具验证加密和SQLite schema，保留当前费用账本，撤销旧登录与邀请码，并重放备份后删除/修改记录。为避免旧背景复活，发生过修改或删除的人物旧快照会整个人物丢弃；恢复回执报告数量。检查新目录后由维护者切换服务配置。失败目录有 `.restore-incomplete` 标记，禁止启动。

服务与备份共用 `.service.lock`，不得在进程仍运行时删除锁文件。崩溃遗留锁时，维护者先核对其中PID及进程已停止，再清除该锁；工具不自动猜测。

## APK签名与交付

构建时把部署域名写入 APK。运行不需要用户输入地址或 API Key。

```powershell
python native/scripts/build_android.py --cloud-url https://YOUR-REAL-DOMAIN --release
```

需事先通过受保护环境配置 `LENS_RELEASE_KEYSTORE`、`LENS_RELEASE_ALIAS`、`LENS_RELEASE_STORE_PASSWORD`、`LENS_RELEASE_KEY_PASSWORD`；密码不出现在命令行。正式构建拒绝缺失域名或调试签名文件，关闭 debuggable，输出签名与对齐校验结果及APK哈希。

保留同一正式签名用于所有更新。旧0.15调试包与正式签名不同，首次切换不能原地覆盖；在确认云端资料可用后卸载旧调试包再安装。正式包后续同签名升级须真机验证。私有仓库仅供源码/构建，不作为公网业务服务器。

Windows本地已经执行一次 `native/scripts/prepare_release_key.py`，生成独立RSA3072生产签名身份，密码受当前Windows用户DPAPI保护；重复执行会拒绝覆盖。部署完成后，可执行 `python native/scripts/build_release.py https://YOUR-REAL-DOMAIN` 使用该身份构建，密码不写入命令行或回执。上述脚本位于源码仓库，部署ZIP不含移动构建工具。

当前公钥证书SHA256为 `0ce1d2c5fd366f7b441296fa483a2af20be18f5b5dd1f10c791f6b4eb4cd692e`。私钥与受保护密码仅在本地 `runtime/release-signing/`，不得上传仓库或随APK分发。尚未验证异机备份与恢复：直接复制DPAPI文件到其他Windows账号不能解密，正式交付前必须完成安全保管和恢复演练。签名身份准备成功不等于正式包或升级验收完成。

## 外部验收

- `/`、`/api/bootstrap`、`/api/export`、`/api/settings` 均403；无token的 `/api/native/roster` 为401。
- HTTPS合法、过期或错误证书不能连接，无密钥/预算时不产生模型调用。
- 服务重启后账号可用；退出/撤销后旧token不可用；A账号不能访问B账号任意资源。
- 人物修改/记忆删除使旧候选失效；恢复备份后删除内容不出现。
- 三人同时试用不重复计费，断网不自动付费重试。
- 发布门槛见 `native/CLOUD_ACCEPTANCE_PACKET.md`，人工质量和7天观察不能由合成测试替代。

接口参考（2026-09-08读取）：[百炼OpenAI兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[OpenAI用量预留示例](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api)。未复制第三方实现；沿用自有服务和原生UI。
