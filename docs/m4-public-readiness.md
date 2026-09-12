# M4 公网运行前准备与验收记录

核实日期：2026-09-12（Asia/Shanghai）。本阶段完成“可以安全进入小范围公网试用前的应用能力”，不代表已经购买服务器、完成备案或部署公网。

## 已实现

- 新注册教师默认没有 AI 权限和额度；既有已启用账户迁移后获得每月 200 次上限，避免升级后突然不可用。
- AI 次数按 UTC 月份原子预留，仅当业务参数与归属校验通过、任务即将进入队列时扣除。无效输入、越权请求和重复生成冲突不会消耗额度；任务提交后即使模型失败也计入次数，因为供应商可能已经产生费用。
- Worker 在实际调用模型前重新检查账户是否启用、AI 权限和删除状态。管理员关闭权限、停用账户或教师申请删除后，尚未开始的任务不会调用付费模型。
- “模板与 AI”显示当前账户本月已用、上限和剩余次数。平台管理员只能在服务器终端设置额度，不把部署级 API 密钥交给教师。
- 注册必须明确勾选当前版本隐私说明；服务端保存告知版本和接受时间。生产环境开放注册时必须配置真实 `SUPPORT_CONTACT`。
- “账户安全”可下载当前教师的结构化 JSON、上传附件和已生成 DOCX。ZIP 不包含密码哈希、恢复码、会话令牌或其他教师资料。
- 删除账户需输入当前密码和完整账户名。默认有 7 天撤销期，申请时撤销其他会话并取消未开始的 AI 任务；当前会话可在账户页取消。到期后 Worker 或管理员命令清除数据库记录和文件对象。
- 服务器终端提供 AI 额度、停用、启用和到期清理命令；操作写入脱敏审计记录。

## 管理命令

下列命令只在受控服务器终端执行，不暴露为浏览器管理员接口：

```powershell
cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync `
  python -m teacher_workspace.manage_users ai <账户名> --limit 100

cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync `
  python -m teacher_workspace.manage_users deactivate <账户名> --confirm <账户名>

cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync `
  python -m teacher_workspace.manage_users activate <账户名> --confirm <账户名>

cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync `
  python -m teacher_workspace.manage_users purge-due --confirm PURGE-DUE
```

设置额度为 `0` 会关闭 AI 并取消未开始任务。停用账户会撤销会话、关闭 AI 和取消未开始任务；重新启用后仍需单独设置额度。已申请删除的账户不能用 `activate` 绕过撤销流程。

## 实际验证

- 普通测试：Web 16 项；后端 65 项通过，另 2 项仅在专用 PostgreSQL 环境执行。
- 独立 PostgreSQL：迁移 `upgrade → downgrade → upgrade` 和 `alembic check` 通过。
- 双教师真实数据链：全业务隔离、账户 ZIP 隔离、附件清除、到期账户全量清除、另一教师资料不变通过。
- 并发额度：10 个并发请求争抢 3 次额度，恰好 3 次成功、7 次返回额度耗尽。
- Edge 新手流程：注册隐私确认、空数据、保存与重启持久化、AI 未开通提示、ZIP 下载、错误删除确认、申请和撤销、并发冲突、多标签换号阻断通过，页面运行异常 0。
- 发布前本机备份 `20260912T015023Z-4cc68076` 已校验，并在一次性 PostgreSQL 容器中恢复成功：迁移 `20260910_0008`、36 张表、2 个存储文件。备份位于 Git 忽略目录且未上传。
- 最终 `pnpm check:release` 退出 0：lint、类型检查、Web 16 项测试、后端 65 项测试（另 2 项 PostgreSQL 专用测试在下述验证中执行）、OpenAPI 生成、生产构建、静态安全和依赖漏洞检查全部通过。
- M4 的 API、Worker 和 Web 镜像实际构建成功；随后使用保留现有卷的 `docker compose up -d --no-build` 完成本机升级。
- 迁移服务实际执行 `20260910_0008 → 20260911_0009`。API 与 Web 健康检查均返回 200，数据库、API、Worker、Web 正常运行；升级前后账户、学生、学科、课程和资料数量一致。

## 尚未完成与开放门槛

- 没有邮件服务；账户找回继续使用一次性展示、只存哈希的离线恢复码。这是已明确的产品选择，不把它伪装成邮件验证码。
- 公开隐私说明不是法律意见。运营者应根据实际主体、未成年人数据处理和所在地区要求咨询专业人士。
- 尚未购买云服务器/域名，未配置公网 HTTPS、备案、异地加密备份或实际跨网络设备。
- `REGISTRATION_ENABLED` 继续默认为 `false`。只有 M5 云端 HTTPS、真实支持联系方式、备份、自启和跨设备验收通过后，才可先向少量受邀教师开放。
