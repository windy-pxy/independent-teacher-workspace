# 项目上下文与续接指南

最后核实：2026-09-11（Asia/Shanghai）。这是工作交接快照，不代替源码、AGENTS.md 或实际验收证据。恢复工作时必须重新检查文件和服务状态。

## 1. 当前状态

- 项目目录：`C:\Users\wyf\Documents\教培个人工作流`。
- 项目已从个人工作台进入“多个独立教师各自注册、登录、管理私人教学资料”的分阶段升级。
- 原 Phase 0—8 已验收；此前的千问视觉扩展、侧边导航和内嵌编辑界面已经完成并提交。
- 新升级路线使用 M1—M5 编号，见 `docs/multi-teacher-roadmap.md`，不要与原 Phase 编号混淆。
- M1 已提交并推送；M2 已完成开发与发布检查，进入提交推送步骤，尚未部署到现有运行环境。具体提交 SHA 以 Git 记录为准；M3—M5 未完成。
- 用户已于 2026-09-11 明确要求读取交接文件并继续，已恢复 M2 收尾；不购买或部署未授权的外部资源。
- 目标模式的总体目标仍未完成，不可把本次交接或 M2 局部验证当作多教师平台最终完成。

### 2026-09-11 续跑最新记录（优先于下方历史）

- Docker 启动后原服务健康，M2 尚未部署；提交/推送结果以当前 Git 状态为准。
- 补验恢复码保存确认与刷新不回显，隔离 PostgreSQL 7 项和真实 Edge 流程通过。
- 额外依赖扫描发现 Next.js、sharp、js-yaml、nanoid、Vitest 和 pypdf 漏洞，已按官方修复版本调整依赖并更新锁文件；详见 `docs/security-patches-20260911.md`。
- 修复后 `pnpm security:dependencies` 已通过；新的 PostgreSQL/Edge 回归也已通过。
- 补丁后完整 `pnpm check:release` 已通过，工具会话 73840 已退出 0：lint/types、前端12项、后端58项/1项专用跳过、构建、契约、静态与依赖安全、三套 Compose 配置均通过。该专用测试已在 PostgreSQL 七项测试中通过。不存在仍需等待的检查会话。
- 已创建并校验本地备份 `var/backups/20260911T014605Z-0bca09b3`（普通本地备份，未加密、未上传），尚未用它覆盖恢复任何数据。
- 下一步：核对 M2 提交推送结果，推进 M3；运行容器需要在保留备份的情况下集成升级。不要因旧段落写“暂停”停止已获明确授权的续跑。

### Git

- 分支：`main`。
- 现有私有远程：`https://github.com/windy-pxy/independent-teacher-workspace.git`。
- 最近提交：`45b34e0` — `feat: 完成多教师改造 M1 会话隔离与验收基础`。已推送；本次检查分支与 `origin/main` 一致。
- 前一提交：`f3f5235` — 工作台界面与内嵌编辑；再前为 `9d59c22` — 千问视觉。
- 工作区有大量 M2 未提交更改，不要 reset、checkout 或覆盖恢复。
- `README.md` 的两行正式使用清单链接和 `docs/go-live-checklist.md` 是本轮 M2 前已存在的未提交内容，不能未经检查混入 M2 提交或删除。

### 运行环境

- Windows / PowerShell；Docker Desktop 已运行。
- 现有 `teacher-workspace-db-1`、`api-1`、`web-1` 健康；`worker-1` 运行。该环境仍是之前验收版本，不是本次 M2。
- Web 使用 `http://localhost:3000`；现有数据库和存储含用户实际资料，必须保留。
- 本次没有升级/回滚现有资料库，没有删除其卷，没有调用付费 AI。
- M2 真实数据库测试使用独立、随机命名的 `teacher-accounts-validation-*` 临时容器，测试后已移除。
- 测试 API/Web 临时用 8101/3101；最后核实这些端口没有监听。明天应重新核实，不依据旧 PID 操作。
- `.env` 已有真实服务端配置，禁止打印全文、提交、截图或复制到交接文件。

## 2. 已完成内容

### 既有业务

学生和学科、长期教学计划、课程/课表、仪表盘、结构化 AI 教案、版本/人工审核、DOCX 导出、关键词课后反馈与进度闭环、错题/视觉识别、针对性练习、课时收费、资料库、Obsidian 单向快照、备份/安全检查基础。

已有 DeepSeek 文本与千问视觉适配配置；开发验收必须 Mock，不得误用真实付费配置。

### M1：已提交推送

- 登录/退出边界取消旧请求、清理查询缓存。
- 退出状态与失败重试提示，成功后完整进入登录页。
- SQLite 真实 API 验证退出再登录仍可读取保存的学生。
- 组件测试验证旧缓存和迟到请求；Edge 模拟接口验证退出失败/重试/后退。
- 首次使用者验收原则已写入根 AGENTS.md。

### M2：已实现但未提交

- `/register`：配置控制开放、用户名校验、密码确认、重复账户处理、一次性展示恢复码与保存确认。
- `/recover`：恢复码重设密码，旧码使用后失效，撤销全部会话。
- `/account`：改密码、轮换恢复码、有效会话列表、撤销其他会话。
- Argon2id 密码哈希；恢复码和会话令牌只存 SHA-256 哈希。
- PostgreSQL 持久化限流，覆盖注册、登录、恢复和当前密码验证。
- 迁移 `20260910_0008` 移除单启用用户限制，增加恢复码哈希、AI 权限和限流表。既有账户 AI 权限保留；新注册账户明确关闭 AI 权限。
- 若有多个启用用户，降级回单教师迁移会明确拒绝，不偷偷禁用或删用户。
- 校验错误不再返回原输入/context，避免密码等敏感字段回显。
- 5 个 AI 生成入口使用统一 `AIUserDep` 权限检查；手工录入不受影响。
- OpenAPI 和 TypeScript 契约已生成，但最终提交前仍应再次生成检查。
- 新增 Playwright 开发依赖及可重复运行的隔离 PostgreSQL + Edge 测试脚本。
- 新界面沿用纸张底色、松绿侧栏、内嵌表单；视觉检查后调整字段间距。

## 3. 文件结构与关键位置

```text
/
├─ AGENTS.md                         仓库约束（必须先读）
├─ PROJECT_CONTEXT.md                本交接文件
├─ README.md                         安装/启动命令
├─ .env.example                      无密钥配置示例
├─ compose*.yaml                     本机/生产/验证容器配置
├─ apps/
│  ├─ backend/
│  │  ├─ alembic/versions/            迁移，M2 新增 20260910_0008
│  │  ├─ src/teacher_workspace/
│  │  │  ├─ auth.py                   注册/会话/密码/恢复/AI 权限
│  │  │  ├─ account_schemas.py        M2 请求响应约束（新）
│  │  │  ├─ auth_limits.py            数据库原子限流（新）
│  │  │  ├─ models.py / config.py
│  │  │  ├─ main.py                   统一错误/中间件
│  │  │  ├─ phase1.py … phase8.py    业务接口
│  │  │  └─ providers/               AI/存储抽象
│  │  └─ tests/test_accounts.py       M2 账户测试（新）
│  └─ web/
│     ├─ AGENTS.md / CLAUDE.md        next dev 新生成，见下述注意
│     └─ src/
│        ├─ app/login/ register/ recover/
│        ├─ app/(workspace)/account/ 新账户安全页面
│        ├─ components/account-entry.tsx / .test.tsx
│        ├─ components/app-shell.tsx
│        └─ lib/session-cache.ts
├─ packages/api-client/              OpenAPI + 类型契约
├─ scripts/
│  ├─ validate_accounts_postgres.py  临时数据库、迁移及可选浏览器
│  └─ validate_accounts_browser.cjs  可见 UI 驱动的真实流程
├─ docs/
│  ├─ multi-teacher-roadmap.md       M1—M5 路线
│  ├─ m2-account-verification.md     M2 已有证据/限制
│  ├─ cloud-purchase-guide.md        云资源购买流程
│  └─ 其他需求/架构/ER/安全/阶段文档
└─ var/validation/                   忽略的测试日志/截图，不提交
```

`next dev` 自动新建了 `apps/web/AGENTS.md` 与 `CLAUDE.md`，当前未提交。AGENTS 要求修改 Next.js 前阅读该安装版本 `node_modules/next/dist/docs/` 中相关文档。两文件本次已读取；后续不要误认为它们是用户业务实现或随意删除反复生成。`next-env.d.ts` 在 dev/build 之间会切换 `.next/dev/types` 与 `.next/types`，最终以生产构建生成结果核查。

## 4. 已确认技术决策

- Next.js 16 / React / TypeScript strict / Tailwind 4；后端 FastAPI、Pydantic2、SQLAlchemy2 异步、Alembic、PostgreSQL。
- Node24、pnpm11；Python3.12、uv；Docker Compose。
- FastAPI 是唯一业务和数据库写入边界；浏览器只经 Next 同源 `/api/v1` 代理。
- 每位教师一个独立私人空间，继续使用 `owner_user_id` 及关联归属链；不新增不必要的 Workspace/Member 双重归属体系。
- 数据持久化在 PostgreSQL/文件存储；退出只撤销会话，不删除业务记录。浏览器缓存不是事实源。
- 注册默认 `REGISTRATION_ENABLED=false`，M3/M4 隔离与安全验证完成前不对公网开启。
- 无邮件服务时采用离线恢复码，不做假邮件找回。恢复码长期有效直到轮换或单次使用，不能描述成短期验证码；密码和恢复码全丢时暂没有邮箱自助找回。
- AI 密钥仍为部署级服务端环境变量。新增教师不能自动无限消耗现有付费额度；M4 待完成费用/配额方案。
- 已有初始化 CLI 只负责空系统第一位可信教师，不是普通教师注册入口。
- 不买 GPU，不本机部署大模型；Obsidian 仅单向快照，PostgreSQL 唯一正式事实源。

## 5. 验证记录：严格区分最终状态

### 已实际通过

- M1 `pnpm check`：前端10项/后端52项，lint/types/build/静态安全通过（见路线图）。
- M2 较早一次完整 `pnpm check`：前端10项/后端57项、lint/types、OpenAPI、生产构建、静态安全通过。之后又加了测试和少量 UI，不能作为最终版本全部通过的证据。
- 后续前端测试：12项通过（包含2项注册组件测试）。
- 最近隔离 PostgreSQL 脚本：迁移 `upgrade → downgrade → upgrade` + `alembic check` 通过；7项账户测试通过，包括真实 PostgreSQL 并发重复注册和持久限流。
- 最近 Edge 实测：真实 API + 真实迁移测试库，注册错误提示/成功、保存虚构学生、退出、新浏览器登录取回学生、恢复密码、旧会话失效、账户安全页通过；页面运行异常0。
- 已查看 `var/validation/m2-register.png` 和 `m2-account.png`；截图不提交。
- 临时数据库及 API/Web 已在测试结束后清理，不影响原服务。

### 当前最后一轮检查

整理结束前已收到第二轮 `pnpm check` 的完整输出，工具会话 **3133 已正常结束，退出码 0**：lint、所有类型检查、前端 12 项测试、后端 58 项通过/1 项跳过、OpenAPI 生成、前后端生产构建、静态安全检查全部通过。跳过的是要求真实 PostgreSQL 的并发注册测试，已在上述独立 PostgreSQL 的 7 项测试中实际通过，不是未测试。

同命令后续的 `docker compose config --quiet` 已执行并通过。当前没有这轮检查仍在运行；不需要明天等待旧会话。最新源码若再修改必须重跑相关检查。`git diff --check` 通过。

浏览器最初两次失败是测试脚本定位/导航等待问题，已修正后实测通过；另一次工具依赖链接失效经 `pnpm install --frozen-lockfile` 修复。不能把这些脚本问题算成业务缺陷修复。

## 6. 待办与风险

### M2 收尾

1. 核实交接后的源码是否变动；上述最后检查已通过，若继续改动则重跑完整 `pnpm check` 与 Compose 静态检查。
2. 新增恢复码保存确认后补充账户页面浏览器验证；不要把之前截图视为这一操作的全部验收。
3. 确认迁移、契约和最新测试一致；整理新增 Next 自动生成文件、脚本可移植性与依赖锁。
4. 审查 Git 差异、敏感内容和运行文件忽略；区分旧的 go-live 文档改动。
5. 更新 M2 验收文档后，按已授权流程独立提交、推送并报告 SHA。当前尚未执行。

### M3—M5

- 全业务双教师同时启用的读写/关联/版本/文件/AI 任务/导出越权测试；不能仅依靠两用户列表为空。
- 同浏览器不同标签页切换账户：目前 M1 只覆盖登录退出边界缓存；必须防旧标签页带着新 Cookie 把内容误存到另一账户。
- PostgreSQL 和服务重启后持久化；跨设备修改冲突与未保存离开提醒。
- AI 权限管理/费用/配额、防滥用和后台任务权限；目前 `User.ai_access_enabled` ORM 默认仍为 true（注册显式 false、数据库默认 false），后续需审查是否改为默认拒绝并明确可信初始化与测试设置。
- 恢复/限流边界、账户停用、数据导出删除、隐私告知、安全检查与备份恢复演练。
- 服务器/域名/HTTPS/云端唯一正式数据源迁移/新设备跨网络访问，均未完成。
- 不得声称网站已成为多人可正式公开运营的平台。

## 7. 恢复工作操作

先读 `AGENTS.md`、本文件、`README.md`、`docs/multi-teacher-roadmap.md` 与 M2 验收文档，再执行：

```powershell
git status --short --branch
git log -3 --oneline
docker compose ps
pnpm install --frozen-lockfile
uv sync --project apps/backend --all-groups --no-install-project
pnpm check
docker compose config --quiet
uv run --project apps/backend --no-sync python scripts/validate_accounts_postgres.py --browser
git diff --check
```

浏览器脚本 Windows 默认复用 Edge，只连接临时测试服务，不要改成连接真实资料库进行破坏性测试。不要为了运行隔离测试关闭现有用户服务。

若 PATH 缺失，可在当前 PowerShell 会话前置工具路径（不要覆盖系统 HOME/CODEX_HOME）：

```powershell
$env:PATH = 'C:\Users\wyf\.local\bin;C:\Users\wyf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;C:\Users\wyf\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback;' + $env:PATH
```

GitHub CLI 安装在 `C:\Program Files\GitHub CLI\gh.exe`，已有授权。Git 操作前重新核对私有属性、分支与远程，勿输出认证令牌。

## 8. 不能改变的要求

- 用户要的是其他独立教师真正注册使用，并能换电脑登录找回已保存资料，不是仅本机假注册或会话内假数据。
- 密码使用安全不可逆哈希，不可明文保存或可逆“加密”；密钥只能服务端环境变量。
- 教师数据严格隔离，身份来自服务端会话；客户端教师 ID 不是授权依据。
- 保留现有正式学生、文档、数据库卷、密钥与配置；不将真实资料带入 Git、日志、截图或测试。
- AI 草稿必须人工审核再成为正式记录，不未经确认覆盖进度；提示词集中版本化。
- 测试必须从不了解网站的新用户角度，检查空数据、错误、取消/返回、刷新/重试、退出重登与跨账户情境，记录真实困惑再优化；不得仅证明预设成功路径。
- 每阶段 lint、types、test、build；迁移真实 PostgreSQL 往返和一致性检查；实际未运行必须说明。
- 每阶段提交推送已获持续授权，但仍需检查敏感数据和差异，禁止强推；购买外部资源、改变仓库可见性不在此授权内。
- 服务器/域名需要用户亲自购买。用户已要求告知购买地点和流程，参考 `docs/cloud-purchase-guide.md`；先确认主体/备案用途和配置再付款，不收取聊天中的密码或私钥。
- 已按用户明确指示恢复工作；交接文件保存不等于目标完成。

## 9. 后续维护这份文件

每阶段结束、重大决策变更、准备暂停或上下文压缩前，更新日期、Git SHA、未提交范围、实际测试结果和第一条恢复操作。不要复制密钥/学生数据，也不要仅沿用旧状态。事实以当前文件、Git 和运行结果为准。
