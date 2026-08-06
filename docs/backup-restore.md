# Phase 6：备份、校验和恢复

## 备份内容

每个备份目录包含：

- PostgreSQL custom-format `database.dump`；
- 本地对象卷 `storage.tar.gz`；
- `manifest.json`：备份 ID、创建时间、Git commit、Alembic 版本、文件大小和 SHA-256。

备份目录位于被 Git 忽略的 `var/backups`。备份可能包含全部学生资料，即使加密也不得提交到 GitHub。

## 创建和验证

普通本地备份：

```powershell
pnpm backup:create
pnpm backup:verify -- var/backups/<backup-id>
```

异地副本必须加密。密码只通过当前进程环境变量读取：

```powershell
$env:BACKUP_ENCRYPTION_PASSWORD="来自密码管理器的独立随机密码"
pnpm backup:create -- --encrypt
pnpm backup:drill -- var/backups/<backup-id>
Remove-Item Env:BACKUP_ENCRYPTION_PASSWORD
```

加密采用流式 AES-256-GCM 和 PBKDF2-HMAC-SHA256（600,000 次），每个文件使用独立随机 salt 和 nonce。密码不写入清单、日志或命令参数；丢失密码后无法恢复。

`verify` 检查目录 ID、文件名安全、大小和 SHA-256。`drill` 会解密归档，在随机命名的隔离 PostgreSQL 17 容器中恢复数据库，核对迁移和表数量，并检查对象归档路径；它不会接触当前数据库。

## 真正恢复

覆盖恢复是破坏性操作。命令同时要求备份 ID 和替换开关：

```powershell
pnpm backup:restore -- var/backups/<backup-id> `
  --confirm-backup-id <backup-id> `
  --replace-current-data
```

执行过程：

1. 重新校验清单和 SHA-256；
2. 自动创建一次恢复前安全备份；
3. 停止 Web、Worker、API；
4. 使用 `pg_restore --clean --if-exists` 恢复数据库；
5. 在随机临时容器中替换本地对象卷；
6. 重新启动 Compose。

任一步失败都不会把半成品标记为成功；数据库恢复失败时服务保持停止，供人工检查。不要手工删除自动安全备份。

## 保留策略

建议至少采用 3-2-1：三份副本、两种介质、一份异地加密副本。

- 最近 7 天：每日一份；
- 最近 4 周：每周一份；
- 最近 12 个月：每月一份；
- 每季度抽取一份执行 `backup:drill`；
- 更换电脑、升级数据库或执行大迁移前额外备份。

删除过期备份前先核对绝对路径、备份 ID和至少一份可恢复副本。备份清理没有自动化硬删，防止路径配置错误导致批量丢失。

## Supabase 边界

当前自动备份工具覆盖标准 Compose PostgreSQL 和默认本地对象卷。切换 Supabase Storage 前，必须同时配置 Supabase bucket 的版本/导出策略，并定期导出对象清单；仅备份 PostgreSQL 不包含 Storage 实际文件。真实 Supabase 恢复演练需要你提供自己的私有项目，Phase 6 不会使用或虚构 service-role key。
