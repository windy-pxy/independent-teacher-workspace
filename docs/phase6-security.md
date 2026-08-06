# Phase 6：安全与性能验收

## 已实施控制

- 生产启动拒绝默认密钥、短数据库密码、HTTP Origin、不安全 Cookie、通配 Host、IP/占位域名和缺失的 Supabase 凭证。
- FastAPI 生产环境关闭 OpenAPI；Web/API 返回 CSP、禁止嵌入、MIME 嗅探、Referrer Policy 等响应头，Caddy 增加 HSTS。
- 请求 ID 仅接受 1–128 位安全字符；未处理异常统一返回脱敏 `INTERNAL_ERROR`。
- 登录连续失败达到阈值后临时锁定；内存中只保留账户名 SHA-256，不保存密码或明文账户名。重启 API 会清空限流状态，这是单实例本地部署的已知边界。
- 本地和 Supabase Storage 使用同一对象键校验；Supabase 错误不返回上游正文或 service-role key。
- Phase 6 验收时实际图片上传仅允许 PNG/JPEG；Phase 7 后续增加的资料库安全边界和未集成常驻恶意软件扫描的限制，以 [phase7-material-library.md](phase7-material-library.md) 为准。
- 收款、审核版本和审计日志不通过普通 UI 硬删；备份恢复具有双重确认和自动恢复前快照。
- PostgreSQL、Python、Node 和 Caddy 容器基础镜像同时固定版本标签与 manifest digest；升级 digest 前必须重新构建并执行本验收矩阵。

## 自动安全检查

```powershell
pnpm security:static
pnpm security:dependencies
```

静态检查覆盖 Git 跟踪的 `.env`、私钥、数据库转储、生成文档、运行目录和常见凭证特征，并要求所有 GitHub Actions 使用完整 commit SHA。依赖检查使用 `pnpm audit --audit-level high` 和 PyPA `pip-audit`。

Phase 6 审计发现旧 Next.js 间接依赖的 `sharp`/`postcss` 漏洞后，已升级到 Next.js 16.3.0；Python 审计发现的 `cryptography 49.0.0` 和 `pytest 8.4.2` 漏洞也已升级到修复版本。任何未来高危结果都应阻止发布，不能通过文档忽略。

## 性能基线

```powershell
pnpm performance:smoke
```

脚本对 API ready 和 Web 登录页分别预热后发送 30 个请求、并发 5，要求全部成功且 p95 不超过 1000ms。它不登录、不读取学生数据，也不是容量测试。业务规模增长后，应另行测试仪表盘、课程月视图和大量错题查询。

## 最终验收矩阵

| 范围 | 自动证据 |
|---|---|
| 登录、CSRF、所有权隔离 | FastAPI 集成测试 |
| 学生→计划→课程→教案→反馈→掌握度 | Phase 1–3 闭环测试 |
| 错题→复习→针对性练习→审核 | Phase 4 测试 |
| 课时→应收→收款分摊→作废→报表 | Phase 5 测试 |
| DOCX | 结构、内容、Word 兼容性和示例渲染测试 |
| PostgreSQL | Alembic `upgrade → downgrade → upgrade` 与 `alembic check` |
| 备份恢复 | 加密备份、SHA-256、隔离 PostgreSQL 恢复演练 |
| 容器 | Compose 静态检查、构建、健康检查和迁移容器退出码 |
| 供应链 | pnpm audit、pip-audit、Action SHA 固定 |

浏览器视觉和 NATAPP 公网链路仍需要教师本人最终体验；自动测试不能证明真实域名、运营商网络或 Microsoft Word 在每台设备上的行为。
