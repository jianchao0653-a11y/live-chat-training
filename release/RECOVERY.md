# 完整检查点与灾难恢复

## 已实现的工具边界

`app/recovery-checkpoint.mjs` 在既有服务互斥锁内导出完整加密检查点：身份、会话、费用、删除、客户分类账本和各账号资料。沿用 AES-256-GCM，随机 IV，独立 32 字节恢复密钥；校验 SQLite schema、完整性、外键及文件边界。密钥应由维护者保存在独立受保护介质，不写进仓库或回执。

```text
node native/scripts/recovery_checkpoint.mjs export SOURCE_DIRECTORY NEW_BACKUP_FILE KEY_FILE
node native/scripts/recovery_checkpoint.mjs import BACKUP_FILE NEW_DIRECTORY KEY_FILE SHA256
```

所有路径均显式提供。导出要求服务已正常停止，不自动启停服务；目标必须不存在。KEY_FILE 是恰好 32 字节的二进制密钥文件。不要将口令当作随机密钥。SHA256 来自独立保存的导出回执，用于验证文件身份，不证明备份最新。

导入不依赖原电脑或 DPAPI，恢复到新目录并撤销旧会话/邀请码，执行资料保留规则。**导入始终留下 `.restore-incomplete` 隔离标记**，服务拒绝启动；普通历史恢复工具也拒绝将该隔离身份库冒充最新账本。

## 上线前必须补足的证据

完整检查点是一个时点快照。导出后原端继续写入，就可能产生更晚的扣费、删除和修改。旧快照即使通过解密、哈希和完整性验证，也不满足“账本不得回滚”。因此工具不提供仅靠勾选或删标记的上线捷径。

1. 明确可接受的业务资料丢失时长、停机时长，以及独立存储介质和责任人。
2. 为身份/费用/删除/分类账本建立独立的最新副本与单写入端控制，恢复时对账供应商可能已发生的调用。
3. 对比当前权威账本、完整检查点与恢复资料；重放后续删除/修改，检查去重记录；原端必须停止写入。
4. 用独立的临时部署完成登录、资料、费用和删除验收后，再安排正式切换。没有最新账本时保持隔离。
5. 单独备份并异机演练 APK 签名私钥、密码及服务凭据。复制 DPAPI 密文文件本身不构成跨机密钥恢复。

## 日常备份

原 `pc_backup.py` 仍是历史资料备份，不能替代完整检查点。Windows 每日自动备份任务和异机存储尚未配置。应先确定介质和维护窗口，再配置任务；不得以自动停服脚本打断未完成模型请求。原备份目录七天清理策略不自动覆盖维护者指定的完整检查点位置，该位置应单独实施访问控制与到期清理。

合成演练已覆盖原目录丢失后的隔离恢复、账本保留、旧登录撤销、错误密钥/哈希拒绝及禁止上线。真实整机灾备、最新账本副本与签名恢复仍是发布阻断项。

## 依据

2026-09-15 阅读：[Node SQLite backup](https://nodejs.org/api/sqlite.html#sqlitebackupsourcedb-path-options)、[Node crypto](https://nodejs.org/api/crypto.html#cryptocreatecipherivalgorithm-key-iv-options)、[Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)。SQLite backup 可用于独立一致副本，但跨库一致性依靠本项目停服互斥；DPAPI 通常要求相同登录身份和电脑。这些文档不证明本机已落实异机备份。
