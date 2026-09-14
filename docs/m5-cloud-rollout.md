# M5 云端部署与首批教师试用

核实日期：2026-09-12（Asia/Shanghai）。本文件是执行清单；没有真实服务器、域名和跨网络证据时，不得把 M5 标记为完成。

## 上线策略

- 首轮只开放“邀请码注册”，不开放无门槛注册。邀请码只存 SHA-256，可限制次数和有效期，并可在服务器撤销。
- 每名教师默认最多累计上传 512 MB 资料；单文件上限仍为 20 MB。归档文件仍占空间，避免通过归档绕过限制。
- 新账户 AI 默认关闭且额度为 0。管理员单独授予月度次数，教师不会接触平台 API 密钥。
- 首次上线保持 `REGISTRATION_ENABLED=false`。完成迁移、HTTPS、备份和管理员自测后，再改为 `true` 并重新创建服务。

## 用户需要购买和提供的信息

推荐阿里云中国内地轻量应用服务器：Ubuntu 24.04 x86_64、至少 2 核 4 GB、60 GB、公网 IPv4；若在服务器本机构建，优先 4 核 8 GB。再购买一个 `.com` 或 `.cn` 域名。中国内地公开服务须先完成 ICP 备案，服务器购买时长要满足实时备案条件。

购买后只提供地域、规格、公网 IP、域名和备案状态。密码、SSH 私钥、云访问密钥、数据库密码和 API 密钥不得通过聊天发送。

## 服务器基础设置

1. 创建日常管理账户，使用 SSH 密钥；禁用密码登录和 root 远程登录前，先保留一个已验证可用的会话。
2. 按 Docker 官方 Ubuntu 文档安装 Docker Engine 与 Compose 插件，并启用 Docker 自启动。
3. 云防火墙只开放 80/443；22 仅允许管理员固定来源。5432、8000、3000 不向公网开放。
4. 使用 GitHub 私有仓库的只读 deploy key 克隆到 `/opt/teacher-workspace/app`；不要把个人访问令牌写进远程 URL。
5. 在项目根创建权限为 `600` 的 `.env`。至少填写真实域名、真实支持联系方式、两个独立强随机密钥，并保持邀请码模式。当前 Compose 会把 `POSTGRES_PASSWORD` 放入数据库 URL，因此该密码只能使用 URL 安全字符；推荐直接使用小写十六进制，不要使用包含 `/`、`+`、`=`、`@` 或 `:` 的 Base64/普通密码：

资源受限的临时试运行机可先建立 Swap，并在本机或 CI 构建应用镜像后通过加密通道传输，避免在 1 GiB 服务器上执行 Next.js 构建。Swap 只能缓解瞬时内存压力，不能代替升配；必须依据容器内存、可用内存、Swap、磁盘和响应时间决定扩容。前端 Dockerfile 使用多阶段构建，只把 Next.js standalone 产物放入运行镜像。

```bash
openssl rand -hex 48  # 用作 SESSION_SECRET，输出 96 位
openssl rand -hex 32  # 用作 POSTGRES_PASSWORD，输出 64 位
```

两条命令的输出必须分别生成、只粘贴到服务器 `.env`，不要发送到聊天、截图或 GitHub：

```dotenv
APP_ENV=production
APP_DOMAIN=你的已备案域名
SUPPORT_CONTACT=你的真实联系邮箱或其他有效方式
SESSION_COOKIE_SECURE=true
SESSION_SECRET=96位独立小写十六进制随机字符串
POSTGRES_PASSWORD=64位独立小写十六进制随机字符串
TRUSTED_ORIGINS=https://你的已备案域名
TRUSTED_HOSTS=api,localhost,127.0.0.1
REGISTRATION_ENABLED=false
REGISTRATION_INVITE_REQUIRED=true
USER_UPLOAD_QUOTA_BYTES=536870912
```

真实 AI 密钥只填入服务器 `.env`，不要复制进 `.env.example`、GitHub、截图或聊天。

## 首次部署

在服务器仓库根目录执行：

```bash
docker compose -f compose.yaml -f compose.production.yaml config --quiet
docker compose -f compose.yaml -f compose.production.yaml build api worker web
docker compose -f compose.yaml -f compose.production.yaml run --rm --no-deps migrate \
  python -m teacher_workspace.production_check
docker compose -f compose.yaml -f compose.production.yaml up -d --no-build
docker compose -f compose.yaml -f compose.production.yaml ps
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  alembic -c apps/backend/alembic.ini current
```

Caddy 是唯一公网入口并自动申请 HTTPS 证书；数据库、API、Web 不映射宿主机端口。域名解析和备案尚未完成时不要把注册打开。

生产覆盖层会把 Web、API、Worker、迁移和 Caddy 的根文件系统设为只读，移除默认 Linux capabilities，禁止进程通过 `setuid`/`setgid` 获得新权限，并限制每个服务的进程数；只有 `/tmp` 和明确声明的数据卷可写。Caddy 仅恢复绑定 80/443 所需的 `NET_BIND_SERVICE` capability。服务器部署时不得为了省事删掉这些约束。

若迁移容器报告 `Production DATABASE_URL must use a strong non-placeholder password`，先确认密码没有使用占位值、长度足够且没有上述 URL 保留字符；不要通过降低生产检查强度绕过错误。

若本地密钥可能泄露，先备份，再执行显式确认的轮换命令；`--disable-ai` 会同时清空 DeepSeek/千问密钥并切回 Mock。完成后仍必须到模型提供商后台撤销旧 Key，脚本不能代替服务商侧吊销：

```powershell
pnpm backup:create
pnpm security:rotate-local -- --confirm rotate-local-secrets --disable-ai
```

## 迁移当前本机资料

1. 本机停止录入，创建加密备份并完成恢复演练。
2. 通过 `scp`/SFTP 把整个备份目录传到服务器仅管理员可读目录，不用网盘明文分享。
3. 云端保持注册关闭，先启动空环境；使用现有恢复工具和两份 Compose 文件恢复。
4. 核对迁移号、账户及各业务表数量，不显示学生姓名或正文。确认后，本机改为只读/停止使用，避免形成两个事实源。

加密密码在终端中静默输入，不写命令历史：

```bash
read -s -p "Backup password: " BACKUP_ENCRYPTION_PASSWORD; echo
export BACKUP_ENCRYPTION_PASSWORD
uv run --project apps/backend --no-sync python -m teacher_workspace.backup_restore \
  --compose-file compose.yaml --compose-file compose.production.yaml \
  restore /安全路径/备份目录 --confirm-backup-id 备份ID --replace-current-data
unset BACKUP_ENCRYPTION_PASSWORD
```

## 创建邀请码与开放首批注册

先创建一次性、7 天有效的邀请码：

```bash
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  python -m teacher_workspace.manage_users invite-create \
  --label "首批试用教师" --uses 1 --days 7
```

邀请码只显示一次，通过可信私聊交给目标教师。把 `.env` 中 `REGISTRATION_ENABLED` 改为 `true` 后执行：

```bash
docker compose -f compose.yaml -f compose.production.yaml up -d --no-build --force-recreate migrate api worker
```

查看邀请码元数据或撤销：

```bash
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  python -m teacher_workspace.manage_users invite-list
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  python -m teacher_workspace.manage_users invite-revoke 邀请码ID --confirm 邀请码ID
```

## 公网和新用户验收

从不在服务器内网的电脑执行：

```bash
pnpm production:verify-public -- https://你的域名 --expect-registration invite
```

然后让两位虚构试用教师仅凭页面文字完成：邀请码注册、保存恢复码、登录、创建学生/学科/课程、刷新、退出重登、另一设备重登、错误输入、重复点击、上传额度提示、跨账户访问和资料导出。不得用源码、数据库 ID 或开发者口头提示替代页面可理解性。

## M5 完成门槛

- 真实域名 HTTPS、证书续期路径和安全响应头通过。
- 服务器重启后 Docker 与全部服务自动恢复。
- 加密异地备份与一次隔离恢复演练通过。
- 本机数据迁移完成且不再双写。
- 两位独立教师跨网络、跨设备持久化与隔离验收通过。
- 记录新用户困惑并修复复测；再决定是否扩大邀请码范围。

## 本地预部署证据

- `pnpm check:release` 退出 0：Web 16 项、后端 70 项通过/3 项 PostgreSQL 专用测试跳过；lint、类型检查、OpenAPI、生产构建、静态安全、Node/Python 依赖漏洞和三套 Compose 配置通过。
- `pnpm validate:multitenant` 退出 0：`0010` 迁移 `upgrade → downgrade → upgrade` 与 `alembic check` 通过；双教师全业务隔离、一次性邀请码及 10 个并发上传争抢 15 字节额度（2 成功、8 拒绝）在真实 PostgreSQL 通过。
- Edge 以两位不熟悉系统的虚构教师完成邀请码注册、空数据、持久化、跨账户隔离和多标签换号阻断，页面异常 0；Mock AI 未产生费用。
- 升级前备份 `20260912T023612Z-54cf63c5` 校验及隔离恢复通过：迁移 `0009`、37 张表、2 个存储文件。
- 本地镜像构建及保留卷升级成功；迁移为 `20260912_0010`，Web/API 均返回 200，四个长期服务正常，升级前后关键业务数量一致。
- 使用隔离 Compose 项目和虚构域名 `teacher.localhost` 完成生产模式启动演练：迁移到 `20260912_0010`、生产配置检查、Caddy HTTPS 反向代理、Web/API 健康检查和安全响应头均通过。由于使用本地 CA 和虚构域名，这不替代真实证书、公网 DNS 或跨网络验收。
- 加固后再次以隔离生产栈验证：Web/API/Worker/Caddy 均为只读根文件系统、移除默认 capabilities、禁止权限提升并限制进程数；根文件系统写入被拒绝，`/tmp` 与对象存储卷仍可正常写入，HTTPS 和迁移保持通过。
- Web 多阶段镜像在本机重新构建并真实启动，运行镜像由约 1.72 GB 降至约 383 MB，HTTP 返回 200；该优化不改变应用路由或业务代码。

这些证据只证明本地预部署包可用，不替代真实域名、HTTPS、云端恢复、服务器重启及跨网络试用。

官方参考：[阿里云备案服务器检查](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-server-access-information-check)、[轻量服务器域名与备案](https://help.aliyun.com/zh/simple-application-server/user-guide/register-and-resolve-domain-names/)、[Docker Engine Ubuntu 安装](https://docs.docker.com/engine/install/ubuntu/)。
