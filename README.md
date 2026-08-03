# 独立教师工作台

仅供一名教师个人使用的课程与教学工作流系统。本仓库当前完成 **Phase 1：学生、学科、教学计划、课程与基础仪表盘**。AI 教案、课后反馈闭环、错题和收费仍属于后续阶段。

## 当前能力

- 单教师账户登录、服务端会话、HttpOnly Cookie、CSRF/Origin 校验和所有权隔离。
- 学生档案、学科和学生学科关联的创建、编辑与安全归档。
- 长期教学计划、层级条目、结构化进度和不可变调整快照。
- 单节课程创建、月历/列表、编辑、完成、取消、调课和补课关联。
- 课程完成前由教师确认实际时长及需要推进的计划条目。
- 今日/未来七天课程、计划进度、本周和本月课时的基础仪表盘。
- Next.js 16 Web，通过同源代理访问 FastAPI；所有按钮均连接真实 API。
- FastAPI `/health/live` 和 `/health/ready`，统一请求 ID 与错误结构。
- PostgreSQL + SQLAlchemy 2 + Alembic 基础迁移。
- PostgreSQL 队列 Worker，支持领取租约、心跳接口、有限重试及 Mock 任务。
- AI 与文件存储统一接口；真实 OpenAI、Supabase 和 DOCX 功能留到对应阶段。
- 前后端 lint、类型检查、测试、构建及 GitHub Actions。

详细文档见 [docs/requirements.md](docs/requirements.md)、[docs/architecture.md](docs/architecture.md)、[docs/data-model.md](docs/data-model.md) 和 [docs/roadmap.md](docs/roadmap.md)。

## 前置条件

- Node.js 24 LTS
- pnpm 11.9（根 `package.json` 已固定）
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop（用于 PostgreSQL 和完整 Compose 验收）
- Git 2.46 或更高版本

Windows 安装 uv：

```powershell
py -3.12 -m pip install --user uv
```

## 首次安装

```powershell
Copy-Item .env.example .env
pnpm install
uv sync --project apps/backend --all-groups --no-install-project
```

打开 `.env`，至少替换 `POSTGRES_PASSWORD` 和 `SESSION_SECRET`。真实密钥不得写入 `.env.example`。

### 推荐：Docker Compose 启动

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

服务地址：

- Web：<http://localhost:3000>
- API 存活检查：<http://localhost:8000/health/live>
- API 就绪检查：<http://localhost:8000/health/ready>
- 本地 API 文档：<http://localhost:8000/api/docs>

停止服务但保留数据库：

```powershell
docker compose down
```

不要随意执行 `docker compose down -v`；它会删除本地数据库和文件卷。

### 本机进程启动

先确保 PostgreSQL 已启动且 `.env` 中 `DATABASE_URL` 可访问：

```powershell
pnpm db:migrate
pnpm dev
```

也可分别启动：

```powershell
pnpm dev:web
pnpm dev:api
pnpm dev:worker
```

## 数据库和账户

执行迁移：

```powershell
pnpm db:migrate
```

回退一个版本：

```powershell
pnpm db:rollback
```

创建唯一教师账户：

```powershell
cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync python -m teacher_workspace.cli
```

命令使用 Argon2id 推荐参数保存密码哈希，不会保存明文密码。

## 质量检查

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm api:generate
pnpm build
pnpm check
```

迁移发生变化时还应在真实 PostgreSQL 上验证：

```powershell
pnpm db:migrate
pnpm db:rollback
pnpm db:migrate
cross-env PYTHONPATH=apps/backend/src uv run --project apps/backend --no-sync alembic -c apps/backend/alembic.ini check
```

## 配置与数据安全

- 开发默认 `AI_PROVIDER=mock`，不会调用付费模型。
- OpenAI 密钥和模型分别由 `OPENAI_API_KEY`、`OPENAI_MODEL` 提供，只在后端/Worker 使用。
- 本地文件默认写入 `var/storage`，已被 Git 忽略。
- 所有示例必须使用虚构学生；不要把真实学生信息、上传件、导出文档或备份放入仓库。
- 生产部署必须启用 TLS、`SESSION_COOKIE_SECURE=true`、强随机会话密钥和独立数据库密码。

完整要求见 [docs/security.md](docs/security.md)。

## 常见问题

- **健康页显示 API 未就绪**：检查 API、PostgreSQL 和 Alembic 迁移；访问 `/health/ready` 查看脱敏错误。
- **`uv` 找不到**：重新打开终端，或用 `py -3.12 -m uv` 验证安装。
- **3000/8000/5432 端口冲突**：修改 `.env` 中 Web/API 端口；数据库端口如需修改也应同步更新 `DATABASE_URL`。
- **Docker Desktop 未启动**：先启动 Docker Desktop，等待引擎就绪后再运行 Compose。
- **Docker 报 WSL/Virtual Machine Platform 未启用**：以管理员身份运行 `wsl --install --no-distribution`，重启 Windows 后重新启动 Docker Desktop。
- **仓库路径包含中文且 BuildKit 报 sharedkey/non-printable ASCII**：临时把仓库映射到纯 ASCII 盘符后构建，例如 `subst W: (Resolve-Path .).Path`，在 `W:\` 运行 `docker compose build`，完成后执行 `subst W: /D`。不要在盘符已被占用时覆盖映射。
- **Docker Hub 需要本机代理**：Docker CLI 使用 Windows 地址（如 `HTTP_PROXY=http://127.0.0.1:<端口>`）；构建容器通过 `.env` 中的 `DOCKER_BUILD_HTTP_PROXY=http://host.docker.internal:<端口>` 和对应 HTTPS 变量访问同一代理。不要把包含认证信息的代理 URL 提交到 Git。
- **OpenAPI 类型变化**：运行 `pnpm api:generate` 并提交生成的 JSON 和 TypeScript 类型。

## Phase 1 使用说明

首次迁移后先创建教师账户，然后访问 <http://localhost:3000/login> 登录。推荐按“学科 → 学生 → 关联学生学科 → 教学计划 → 课程”的顺序录入。完成课程时，系统会弹出确认窗口；只有教师勾选并确认的计划条目才会改变正式进度。

当前不支持重复课程规则。调课会保留原课程为“已调课”，并创建一节关联的新课程；取消后的课程可在新建课程时选为补课来源。

## 下一阶段

Phase 2 将实现 AI 统一接口、集中提示词模板、教案草稿/审核/版本管理，以及 DOCX 示例和自动测试。Phase 1 不会调用付费模型，也没有提前实现错题、反馈闭环或收费模块。

项目的提交和推送必须遵循 [AGENTS.md](AGENTS.md) 中的“双重确认”流程。
