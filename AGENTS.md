# AGENTS.md

本文件是仓库级开发约束。除非更深目录存在更具体的 `AGENTS.md`，所有修改均须遵守。

## 项目目标与边界

- 本项目是单教师使用的学生、课程、教案、反馈、错题和收费工作台。
- FastAPI 是唯一业务规则和数据库写入边界；Next.js 不得直连数据库或 Supabase 表。
- 当前实现到 Phase 2。不得提前实现 Phase 3 的反馈闭环、Phase 4 的错题生成或 Phase 5 的收费模块，也不得用假按钮、内存假数据或静态页面冒充业务完成。
- 开发、测试、截图和示例文档只能使用明确虚构的学生资料。

## 架构约束

- Web 位于 `apps/web`，后端、迁移和 Worker 位于 `apps/backend`。
- 浏览器通过 Next.js 同源 `/api/*` 代理访问 FastAPI；公共 API 使用 `/api/v1`。
- 所有数据库变化必须通过可重复执行的 Alembic 迁移，不得依赖手工 SQL。
- AI 调用必须经过 `AIProvider`；业务模块不得直接导入 OpenAI SDK。
- 文件必须经过 `StorageProvider`；数据库保存对象键，不保存客户端提供的路径。
- 提示词集中管理并版本化；业务代码只引用模板键，不得散落长提示词。
- AI 草稿和正式记录必须分离。只有人工批准事务可以更新正式进度、掌握度或文档版本。
- 金额使用整数分，时长使用整数分钟，时间以 UTC 入库并按 `Asia/Shanghai` 展示。

## 开发命令

```powershell
pnpm install
uv sync --project apps/backend --all-groups --no-install-project
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm api:generate
pnpm docx:sample
pnpm build
pnpm check
pnpm db:migrate
pnpm db:rollback
docker compose up --build -d
docker compose ps
```

若系统 PATH 没有 Node，可使用 Codex 工作区依赖提供的 Node/pnpm；面向普通开发者的 README 仍以 Node.js 24 LTS 为标准前提。

## 测试要求

- 每次阶段性交付必须运行 lint、类型检查、单元测试和生产构建。
- 修改模型或迁移时，在 PostgreSQL 上验证 `upgrade → downgrade → upgrade`，并运行 `alembic check`。
- 修改 OpenAPI 时重新生成 `packages/api-client` 并检查生成文件差异。
- AI/Worker 测试默认使用 Mock，不得因测试调用付费模型。
- 不得声称未实际执行的命令或测试通过；环境缺失必须列为未完成项。

## 安全边界

- 密钥只从环境变量读取。禁止把真实密钥、密码、学生信息、上传件、导出文件或数据库转储提交到 Git。
- 禁止把密钥放入 `NEXT_PUBLIC_*`、数据库、日志、异常消息、审计详情或 AI 提示词。
- 日志使用代号、实体 ID 和脱敏错误；不得记录完整提示词、学生答案或上传正文。
- 上传必须校验大小、允许类型、文件魔数和安全对象键；禁止路径遍历。
- 所有业务查询必须有当前教师所有权边界，即使系统当前只有一个账户。
- 重要记录默认归档；永久删除必须二次确认并写审计日志。
- API 错误必须使用统一错误结构并包含请求 ID，不向客户端泄露堆栈或数据库细节。

## Git 操作流程

1. 完成功能并运行当前阶段规定的检查。
2. 汇报改动，检查 `git status`、`git diff` 和敏感文件。
3. 等待用户本地体验并确认。
4. 只有用户明确授权后，才暂存当前阶段文件并创建一个本地提交。
5. 提交完成后报告 commit SHA；不得自动推送。
6. 只有再次收到明确授权，并核对当前分支、远程地址和待推提交后才推送私有 GitHub。
7. 禁止强推。创建远程仓库、绑定远程和首次推送都是独立外部操作。

Phase 0 建议提交信息：`chore: 完成 Phase 0 项目骨架与架构规划`。
