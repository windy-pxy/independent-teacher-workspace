# 独立教师工作台

仅供一名教师个人使用的课程与教学工作流系统。Phase 0—7 已完成并验收，当前准备实现 Obsidian 单向 Markdown 导出。

## 当前能力

- 单教师账户登录、服务端会话、HttpOnly Cookie、CSRF/Origin 校验和所有权隔离。
- 学生档案、学科和学生学科关联的创建、编辑与安全归档。
- 长期教学计划、层级条目、结构化进度和不可变调整快照。
- 单节课程创建、月历/列表、编辑、完成、取消、调课和补课关联。
- 课程完成时记录实际时长；计划进度在课后反馈批准时统一更新。
- 今日/未来七天课程、计划进度、本周和本月课时的基础仪表盘。
- 结构化教案草稿：教学目标、时间安排、知识讲解、例题、练习、易错点、作业、答案解析和教师注意事项独立编辑。
- Mock/OpenAI 统一 AI 接口、集中且版本化的提示词模板、后台生成任务和局部章节重生成。
- 教案提交审核、批准/驳回、不可变版本历史，以及仅批准版本可导出的教师版 DOCX。
- 课后关键词快速录入、AI 结构化整理、人工修订、提交审核及不可变版本历史。
- 反馈批准事务同步教学计划、结构化知识点掌握度证据和下次课建议；批准前不改正式数据。
- 文本错题、PNG/JPEG 安全上传、可替换视觉识别、人工审核、复习记录和结构化掌握状态。
- 根据正式错题、错误原因、知识点与学生基础生成针对性练习；题目、答案和解析经教师批准后才发布。
- 课时、应收、实际收款、多课程分摊、欠费查询和 CSV/XLSX 报表。
- Caddy/NATAPP 部署、生产配置预检、加密备份恢复、安全与性能检查。
- PDF、DOCX、TXT 资料安全上传和文本分段；生成教案时由教师明确选择要引用的资料。
- Mock/OpenAI/DeepSeek 可替换 AI Provider；DeepSeek 适配器使用兼容 Chat Completions 的 JSON 模式。
- DOCX 使用年级样式配置，当前提供通用小学/初中/高中视觉档案；后续可在不改变教案数据结构的情况下增加固定模板。
- Next.js 16 Web，通过同源代理访问 FastAPI；所有按钮均连接真实 API。
- FastAPI `/health/live` 和 `/health/ready`，统一请求 ID 与错误结构。
- PostgreSQL + SQLAlchemy 2 + Alembic 基础迁移。
- PostgreSQL 队列 Worker，支持领取租约、心跳接口、有限重试及 Mock 任务。
- AI 与文件存储统一接口；OpenAI 使用 Responses API，DeepSeek 使用官方兼容接口，模型名均只由环境变量配置。
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
pnpm check:release
pnpm security:static
pnpm security:dependencies
pnpm performance:smoke
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
- DeepSeek 密钥和模型分别由 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 提供；密钥不要通过聊天、前端或日志传递。
- 图片识别独立使用 `VISION_AI_PROVIDER`；默认 `mock`。当前真实视觉适配器为 OpenAI，需同时配置 `OPENAI_API_KEY` 和 `VISION_OPENAI_MODEL`；文本仍可使用 DeepSeek。
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
- **仓库路径包含中文且 BuildKit 报 sharedkey/non-printable ASCII**：优先临时执行 `subst W: (Resolve-Path .).Path`，到 `W:\` 运行 `docker compose up --build -d`，再回到原目录执行 `subst W: /D`；须先确认 `W:` 未被占用。当前 Docker Desktop 也可用 `$env:DOCKER_BUILDKIT='0'; docker compose build` 后接 `docker compose up -d` 兼容构建。两种方式均不删除或迁移数据库卷。
- **Docker Hub 需要本机代理**：Docker CLI 使用 Windows 地址（如 `HTTP_PROXY=http://127.0.0.1:<端口>`）；构建容器通过 `.env` 中的 `DOCKER_BUILD_HTTP_PROXY=http://host.docker.internal:<端口>` 和对应 HTTPS 变量访问同一代理。不要把包含认证信息的代理 URL 提交到 Git。
- **OpenAPI 类型变化**：运行 `pnpm api:generate` 并提交生成的 JSON 和 TypeScript 类型。

## Phase 1 使用说明

首次迁移后先创建教师账户，然后访问 <http://localhost:3000/login> 登录。推荐按“学科 → 学生 → 关联学生学科 → 教学计划 → 课程”的顺序录入。完成课程时只记录实际时长，正式计划进度由课后反馈批准事务更新。

当前不支持重复课程规则。调课会保留原课程为“已调课”，并创建一节关联的新课程；取消后的课程可在新建课程时选为补课来源。

## Phase 2 使用说明

访问 <http://localhost:3000/lesson-plans>，选择一节课程和提示词模板后创建生成任务。开发环境默认 `AI_PROVIDER=mock`，无需密钥且不会产生费用；启用真实模型时在服务端 `.env` 设置 `AI_PROVIDER=openai`、`OPENAI_API_KEY` 和 `OPENAI_MODEL`，重启 API 与 Worker。

生成成功后可逐章节编辑并保存新版本，也可只重生成指定章节。教案须先提交审核并批准，Word 导出入口才会开放；任何编辑和重生成都会创建不可变新版本，不直接覆盖历史内容。提示词版本和当前 AI 配置可在 <http://localhost:3000/settings/ai> 查看与维护，页面不会显示 API 密钥。

生成虚构示例文档：

```powershell
pnpm docx:sample
```

输出写入被 Git 忽略的 `var/exports`。当前公式以 Unicode/纯文本形式导出，不承诺 Word 原生 OMML 公式编辑。

## Phase 3 使用说明

完成一节课程后访问 <http://localhost:3000/feedback>，选择课程并填写少量关键词。保存后可以先人工编辑，或交给 Mock/真实模型整理；AI 结果始终是草稿，必须先提交审核，再由教师点击“批准并同步”。批准会在单个数据库事务中更新计划条目、知识点掌握度证据和反馈内的下次课建议，任一步失败都会整体回滚。

开发与测试默认使用 Mock。启用 DeepSeek 时，只在服务端 `.env` 中设置：

```dotenv
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的服务端密钥
DEEPSEEK_MODEL=你在 DeepSeek 控制台确认的当前模型名
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

然后重启 API 和 Worker。不要把真实密钥发到聊天、截图或提交到 Git；首次切换真实模型时建议只用虚构学生验证输出。Obsidian 目前不参与正式数据写入，后续可作为可选 Markdown 导出、离线查阅和备份目标。

## Phase 4 使用说明

访问 <http://localhost:3000/wrong-questions> 可手工录入正式错题，或上传 PNG/JPEG 图片生成识别草稿。上传会校验扩展名、MIME、文件魔数和大小，并使用 UUID 对象键保存；识别结果必须提交审核并由教师批准，才成为正式错题。正式错题可持续记录复习结果和“未学习/薄弱/一般/熟练/已掌握”状态。

访问 <http://localhost:3000/practice>，选择学生学科、正式错题、难度和题量后生成针对性练习。每道题必须包含答案与解析；生成内容可保存新版本，提交审核并批准后才发布。开发默认使用 Mock，不读取真实题图且不产生费用。

若以后启用真实图片识别，只在服务端 `.env` 设置：

```dotenv
VISION_AI_PROVIDER=openai
OPENAI_API_KEY=你的服务端密钥
VISION_OPENAI_MODEL=你在提供商控制台确认支持图片输入的当前模型名
```

文本生成可以继续设置为 `AI_PROVIDER=deepseek`，两类任务互不绑定。完整数据和审核边界见 [docs/phase4-wrong-questions.md](docs/phase4-wrong-questions.md)。

## Phase 5 使用说明

创建或编辑课程时设置每小时单价。计划中课程按计划分钟显示预计应收，课程完成后按实际分钟重新计算。访问 <http://localhost:3000/billing> 可以按周或按月查看课时、应收、实际到账和欠费，记录一次真实收款并把它分摊到一节或多节课程；同一课程也允许分多次收款。

人工覆盖应收必须填写原因。误录的收款不会硬删除，需要填写理由作废；对应分摊会从有效到账中排除。页面可直接导出 UTF-8 CSV 或 XLSX，导出文本已防止电子表格公式注入。完整规则见 [docs/phase5-billing.md](docs/phase5-billing.md)。

## Phase 6 使用说明

Phase 6 已完成实现、本地自动化验证和用户验收。部署模式和 NATAPP 操作见 [docs/deployment.md](docs/deployment.md)，备份恢复见 [docs/backup-restore.md](docs/backup-restore.md)，安全验收见 [docs/phase6-security.md](docs/phase6-security.md)。NATAPP 公网域名、真实 Supabase Storage 和生产数据恢复仍需在取得对应账号、域名或生产环境后单独验证。

项目的提交和推送必须遵循 [AGENTS.md](AGENTS.md) 中的“双重确认”流程。

## Phase 7 使用说明

访问 <http://localhost:3000/materials>，可把 PDF、DOCX 或 UTF-8 TXT 资料关联到指定学生学科。系统保存原文件，同时提取有长度上限的文本片段；扫描版和加密 PDF 暂不支持，原文件正文不会写入日志。

生成教案前，在 <http://localhost:3000/lesson-plans> 勾选本节真正需要的资料。每次最多选择 10 份，发送给模型的资料正文总量限制为 12000 字符；未勾选的资料不会进入该次 AI 上下文。资料正文按不可信输入处理，不能改变系统角色或触发工具调用。
