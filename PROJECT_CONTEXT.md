# 项目上下文与续接指南

最后核实：2026-09-14（Asia/Shanghai）。新会话先读根 `AGENTS.md` 和本文件，再核对 Git、代码和服务状态；本文件是快照，不替代真实状态。

## 1. 项目当前状态

- 目录：`C:\Users\wyf\Documents\教培个人工作流`。
- 产品正从单教师本机工作台升级为“多个独立教师各自注册、登录并管理私人教学资料”的在线工作台。
- 原 Phase 0—8 已验收。多教师升级使用 M1—M5：M1—M4 已提交推送；M5 本地预部署开发与验证已完成，真实服务器、域名和跨网络验收仍待用户购买资源。
- 当前分支 `main`，私有远程 `https://github.com/windy-pxy/independent-teacher-workspace.git`。
- `origin/main` 已包含 M5 本地预部署、正式使用文档和官方 Node 24 Actions；精确最新提交始终以 `git status` 与 `git log` 实际结果为准。
- 当前 Compose 已运行 M5 本地预部署版本：邀请码注册、单教师上传额度和公网检查工具已部署；Web/API/数据库健康，Worker 运行，迁移头为 `20260912_0010`。升级前后账户、学生、学科、课程和资料数量一致，过程中未删除卷。真实公网仍未部署。
- 用户已于 2026-09-13 购买北京地域 Ubuntu 24.04 轻量应用服务器（2 vCPU、1 GiB、30 GiB），用于低并发试运行；实例标识和公网 IP 不写入仓库。服务器已绑定本机专用 SSH 公钥，创建 `teacheradmin` 日常账户，禁用密码和 root 远程登录，启用 2 GiB Swap、UFW 22/80/443、自动安全更新、Docker Engine/Compose 自启及受限日志。GitHub 私有仓库通过只读 deploy key 克隆。
- 云端已启动仅绑定 `127.0.0.1` 的私有测试栈，注册关闭，迁移为 `20260912_0010`，Web/API/数据库健康；通过 SSH 隧道访问返回 HTTP 200。四个容器空闲内存合计约 277 MiB，宿主机尚余约 173 MiB、Swap 未使用，磁盘使用约 24%。这只证明低并发空载可运行，不代表多人容量验收。真实域名、生产 HTTPS、正式数据迁移、异地恢复和跨网络多人验收仍未完成。
- `.env` 含实际服务配置，禁止打印、提交、截图或写入本文。
- 2026-09-12 一次生产 Compose 诊断错误地展开了本地环境变量。已立即创建并校验备份、轮换数据库密码和会话密钥、清空本地 DeepSeek/千问 Key，并把文本/视觉 Provider 切回 Mock；服务和迁移恢复健康。用户于 2026-09-13 确认已在 DeepSeek 与阿里云百炼撤销旧 Key，并已在本机 `.env` 写入新 Key；最小真实调用验证 DeepSeek 文本与千问视觉均成功。密钥值未写入本文，也不得通过聊天传递。
- “正式使用准备与首次使用清单”已按当前本机/云端双路径更新；提交状态以 Git 为准。
- M4 备份 `var/backups/20260912T015023Z-4cc68076` 已创建、校验并在一次性 PostgreSQL 中恢复成功；它未加密、位于 Git 忽略目录、不得上传。

## 2. 已完成内容

### 原 Phase 0—8

学生/学科、计划、课程与仪表盘；AI 教案、版本与 DOCX；反馈审核和进度闭环；错题、视觉识别与练习；课时收费；资料库；Obsidian 单向快照；本地部署、备份和安全检查。文本 AI 支持 Mock/OpenAI/DeepSeek，视觉支持 Mock/OpenAI/Qwen；测试只用 Mock。

### M1：会话与缓存边界

- 登录/退出取消旧请求、清理浏览器缓存；退出失败可重试。
- 保存资料后退出再登录仍可读取，浏览器后退不泄露旧页面。
- 首次使用者验收准则写入 `AGENTS.md`。

### M2：注册与账户安全

- 真实教师注册、Argon2id 密码哈希、持久化限流、离线恢复码、改密、会话查看与撤销。
- 多启用用户迁移；新账户 AI 默认关闭。
- 注册默认关闭，生产环境未验收前不能公开。

### M3：全业务隔离与持久化

- 全业务所有权校验、路径/请求体 ID 替换防护、跨账户下载与导出隔离。
- 同账户并发修改冲突、未保存离开提醒、多标签换号阻断。
- 两名虚构教师在真实 PostgreSQL 与 Edge 中通过注册、重启持久化和跨账户验证。
- 提交 `9cbef84` 已推送并在本地保留卷部署。

### M4：公网运行前应用准备（代码与自动验收已完成）

- 新账户 AI 默认拒绝；平台按教师配置月度生成次数，10 个并发请求争抢 3 次额度时仅 3 次成功。
- 业务和归属校验成功、任务即将排队时才占用额度；错误输入不扣次数。Worker 在调用模型前再次检查账户、额度权限和删除状态。
- “模板与 AI”显示本月已用、上限与剩余；服务器 CLI 支持额度、启停和到期清理。
- 注册必须接受版本化隐私说明；生产开放注册必须配置真实 `SUPPORT_CONTACT`。
- 账户页支持 ZIP 全量导出，不包含密码哈希、恢复码、会话或他人资料。
- 删除账户需当前密码和完整账户名，默认 7 天撤销期；其他会话和未开始 AI 任务被撤销，到期清除数据库及对象文件。
- 迁移 `20260911_0009` 添加隐私接受、删除计划、AI 月度上限和 `ai_usage_months`。
- 详细设计与证据：`docs/m4-public-readiness.md`。

## 3. 文件结构

```text
/
├─ AGENTS.md / PROJECT_CONTEXT.md / README.md
├─ apps/
│  ├─ web/                         Next.js 16、账户/隐私/业务页面
│  └─ backend/
│     ├─ alembic/versions/         当前迁移 20260912_0010
│     ├─ src/teacher_workspace/
│     │  ├─ auth.py                会话、注册、隐私、导出/删除、AI 额度
│     │  ├─ account_export.py      当前教师安全 ZIP 导出
│     │  ├─ account_deletion.py    到期清除与文件删除
│     │  ├─ manage_users.py        服务器账户/额度 CLI
│     │  ├─ models.py / config.py
│     │  ├─ phase1.py … phase8.py
│     │  ├─ worker.py / queue.py
│     │  └─ providers/             AI 和存储抽象
│     └─ tests/
├─ packages/api-client/            OpenAPI 生成契约
├─ scripts/
│  ├─ validate_multitenant_postgres.py
│  └─ validate_multitenant_browser.cjs
├─ docs/
│  ├─ multi-teacher-roadmap.md
│  ├─ m3-isolation-verification.md
│  ├─ m4-public-readiness.md
│  ├─ m5-cloud-rollout.md
│  ├─ go-live-checklist.md
│  └─ cloud-purchase-guide.md
├─ compose.yaml / compose.production.yaml / compose.validation.yaml
└─ var/                             存储、导出、验证证据和备份；全部忽略
```

## 4. 技术决策

- Next.js 同源 `/api/v1` 代理到 FastAPI；FastAPI 是唯一业务规则和数据库写入边界。
- PostgreSQL 和持久文件存储是事实源；退出只撤销会话。每名教师继续以服务端会话 `User.id` 为所有权边界，不提前引入团队 Workspace。
- 密码 Argon2id；会话和恢复码只存哈希；生产 Cookie 必须 Secure/HttpOnly/SameSite，写操作验证 Origin/CSRF 和标签页账户。
- AI 密钥是部署级服务器配置。教师不能看到密钥；新账户无额度，管理员通过终端按月授权。正式 AI 内容仍需人工审核。
- 无邮件服务时继续采用只展示一次的离线恢复码，不伪造邮件找回流程。
- 教师申请删除后保留默认 7 天撤销期；到期清除在线主库和文件。备份按独立轮换策略过期，不把备份当在线业务源。
- 公共注册继续默认关闭。只有云端 HTTPS、运营者联系方式、备份、自启和跨设备试用通过后才小范围开放。
- 生产开放注册必须使用限次、限时的邀请码；默认每教师累计上传额度为 512 MB，归档资料仍计入额度。
- Obsidian 仅为主动触发的单向只读快照；PostgreSQL 始终是唯一正式数据源。

## 5. 最近验证证据

- `pnpm check:release` 退出 0：Web/Backend lint、全栈类型检查、Web 16 项、Backend 65 项通过/2 项专用 PostgreSQL 跳过、OpenAPI 生成、Next/Python 构建、静态安全、Node/Python 依赖漏洞扫描、三套 Compose 配置通过。
- `pnpm validate:multitenant` 退出 0：独立 PostgreSQL `upgrade → downgrade → upgrade`、`alembic check`、2 项真实 PostgreSQL 测试通过。
- PostgreSQL 测试覆盖全业务双教师隔离、账户导出隔离、到期账户与文件清除、另一教师资料保持、10 并发/3 额度原子限制。
- Edge 新手流程通过：隐私勾选、空数据、保存、服务重启持久化、AI 未开通提示、ZIP 下载、错误删除确认、申请/撤销、并发冲突、多标签换号阻断；页面异常 0。
- 备份 `20260912T015023Z-4cc68076`：校验通过；隔离恢复迁移 `20260910_0008`、36 张表、2 个存储文件，状态 `ok`。
- 所有验证只使用虚构教师/学生和 Mock AI，没有调用真实付费模型，也没有替换现有资料库。
- M5 本地预部署：`pnpm check:release` 退出 0（Web 16、Backend 70 通过/3 个 PG 专用跳过）；`pnpm validate:multitenant` 退出 0，真实 PostgreSQL 覆盖 `0010` 往返、一次性邀请码及并发上传额度，Edge 两教师邀请码流程通过。
- M5 升级前备份 `20260912T023612Z-54cf63c5` 校验及隔离恢复通过；本机保留卷升级至 `0010` 后 Web/API 200、服务健康、关键数据计数不变。
- M5 预部署提交 `c6f40ca`、使用清单提交 `cbe9f37` 和 Node 24 Actions 提交 `6739ad3` 的 GitHub Actions 全部通过。
- 使用独立 Compose 项目、独立卷和虚构域名 `teacher.localhost` 进行了生产模式启动演练：安全配置检查、迁移 `0010`、Caddy HTTPS 入口、Web/API 健康检查及安全响应头通过。首次用含 URL 保留字符的 Base64 数据库密码时连接串检查正确失败；改用 64 位随机十六进制密码后通过，部署文档已补充该约束。此演练使用本地 CA，不证明真实公网证书或跨网络可用。
- 安全事件前备份 `var/backups/20260912T082739Z-a942ee9d` 已创建并通过校验；它位于 Git 忽略目录且未加密，不得上传。轮换后 API/Web 健康、迁移仍为 `0010`；旧会话因会话密钥轮换而失效属于预期行为。
- 生产 Compose 已为 Web/API/Worker/迁移/Caddy 启用只读根文件系统、移除默认 capabilities、`no-new-privileges` 和每服务 256 进程上限；Caddy 仅恢复 `NET_BIND_SERVICE`。隔离栈验证根目录写入被拒绝、`/tmp` 与对象存储卷可写、HTTPS/API/迁移正常。

## 6. 待办事项

### M5 云部署与首次多人试用

1. 用户按 `docs/cloud-purchase-guide.md` 购买合适服务器和域名；购买、备案和提供真实支持联系方式必须由用户完成。
2. 云端部署时将已验证的新 DeepSeek/千问 Key 仅写入服务器 `.env`，不得通过聊天发送；不得复用已撤销的旧 Key。
3. 配置 Ubuntu、SSH 最小权限、防火墙、Docker、HTTPS、生产密钥和异地加密备份。
4. 把本机正式 PostgreSQL/Storage 迁移到唯一云端主库，迁移前后核对并避免双写。
5. 验证云服务器重启自启、备份恢复、另一电脑/手机通过真实域名登录和持久化。
6. 先邀请少量独立教师，以新用户视角记录困惑并修复，再决定是否扩大开放。
7. 备案前如实向阿里云确认主体资格：个人备案不得用于行业服务或面向公众的公共服务系统；多教师工作台可能需要单位主体，且教育类内容可能涉及前置审批。当前服务器仅购买 1 个月，尚不满足内地备案累计至少 3 个月的条件。

## 7. 下一步操作

恢复工作先执行：

```powershell
git status --short --branch
git log -3 --oneline
docker compose ps
docker compose exec -T api alembic -c apps/backend/alembic.ini current
git diff --check
```

若 M5 本地预部署尚未提交，先核对差异、敏感文件并提交推送。若已推送且本地迁移为 `20260912_0010`，等待用户购买/提供云服务器、域名和真实支持联系方式；不要擅自购买外部资源。

## 8. 不能改变的要求

- 最终必须让其他独立教师真正注册、登录，并能从其他电脑找回持久化资料；不能用静态页面、内存数据或本机端口冒充公网完成。
- 教师身份只取已验证服务端会话；客户端教师 ID 不可信。账户切换必须清缓存并阻断旧标签页写入。
- 密码必须安全不可逆哈希，密钥只在服务端环境变量；不得提交、记录或回显密钥、密码和真实学生资料。
- 所有业务域、关联、文件、AI 任务和导出必须按教师隔离；公共注册前必须做双教师真实 PostgreSQL 与浏览器验收。
- AI 草稿须经教师审核后才更新正式进度、掌握度或文档；提示词集中并版本化。
- 每次功能验证都要从不熟悉网站的普通用户角度检查入口文字、空数据、错误、取消、刷新、重复点击、退出重登、跨账户和必要的新浏览器会话；不能只验证开发者预设成功路径。
- 每阶段运行 lint、类型检查、测试和生产构建；迁移须真实 PostgreSQL 往返和 `alembic check`。未运行的检查不得声称通过。
- 每阶段提交推送已有持续授权，但仍须核对差异、敏感内容、分支与远程；禁止强推。购买资源、改变仓库可见性不在授权内。
- 保留现有资料、密钥、数据库卷和文件卷；禁止 `docker compose down -v`。测试与截图只用明确虚构数据。
- 云服务器和域名由用户亲自购买；不要在聊天接收密码、私钥或云访问密钥。
