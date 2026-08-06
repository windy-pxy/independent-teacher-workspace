# Phase 6：部署与远程访问

## 部署模式

系统保留两种部署方式，二者不要同时启用：

1. **本机 + NATAPP**：适合当前个人使用。PostgreSQL、API 和 Web 仍只监听本机，NATAPP 把公网 HTTPS 请求转发到 `127.0.0.1:3000`。
2. **私有云 + Caddy**：适合以后把整套 Compose 搬到长期在线服务器。Caddy 是唯一公网入口，自动申请并续期 TLS 证书；数据库、API 和 Web 不映射宿主机端口。

无论使用哪种方式，浏览器始终只访问 Web，同源 `/api/*` 再转发到 FastAPI。不得直接把 PostgreSQL 或 FastAPI 暴露到公网。

## 生产环境变量

复制 `.env.example` 为被 Git 忽略的 `.env`，至少修改：

```dotenv
APP_ENV=production
APP_DOMAIN=teacher.example.com
TRUSTED_ORIGINS=https://teacher.example.com
TRUSTED_HOSTS=api,localhost,127.0.0.1
SESSION_COOKIE_SECURE=true
SESSION_SECRET=至少48位密码学随机字符串
POSTGRES_PASSWORD=至少16位随机字符串
```

生成随机值时可在 PowerShell 使用：

```powershell
$bytes = New-Object byte[] 48
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
$rng.Dispose()
```

也可以使用密码管理器生成 64 位随机密码。不要把生成结果发到聊天、截图或 GitHub。

启动前必须执行：

```powershell
pnpm production:check
```

检查只输出域名、存储驱动等非敏感摘要。生产配置会拒绝默认密钥、短数据库密码、非 HTTPS Origin、不安全 Cookie、通配 Host、IP 地址及占位域名。

## 本机通过 NATAPP 访问

根据 NATAPP 当前官方说明，付费 Web 隧道需要绑定域名；可以购买 NATAPP 二级域名，也可绑定自己的域名。对本系统，优先选择支持 HTTPS 的年付 Web 隧道和固定二级域名，不需要购买 TCP 隧道。

操作顺序：

1. 在 NATAPP 注册并进入“购买隧道”，选择 Web 隧道（VIP_1/VIP_2 或合适的香港线路）。
2. 购买并绑定一个固定 NATAPP 二级域名；把最终域名写入 `APP_DOMAIN` 和 `TRUSTED_ORIGINS`。
3. 在隧道配置中启用公网 HTTPS。本地协议保持 HTTP，不要打开“本地 HTTPS”。
4. NATAPP 原生 Windows 客户端把本地 IP 设置为 `127.0.0.1`、端口设置为 `3000`；若 NATAPP 运行在 Docker 中，本地 IP 使用 `host.docker.internal`。
5. 将 authtoken 写入仓库外的 NATAPP `config.ini`，或安装为 Windows 服务；authtoken 不得放入本项目 `.env`。
6. 启动应用：`docker compose up --build -d`；再启动 NATAPP 客户端。
7. 只通过最终 `https://域名` 登录，确认 Cookie 带 `Secure`，HTTP 会跳转或不可用。

建议在 NATAPP“安全设置”中再启用独立的 HTTP Basic Auth、访问令牌或固定 IP 白名单。不要开启本地流量监控控制台；它能读取请求细节，不适合包含学生资料的正式环境。

NATAPP 在公网边缘终止 HTTPS，再通过其加密隧道发送到本机客户端；本机端口仍绑定 `127.0.0.1`。若以后需要完全自主控制 TLS、日志和可用性，应迁移到私有云 + Caddy。

## 私有云 + Caddy

前提：域名 A/AAAA 记录已指向服务器，防火墙只开放 80/443，Docker 和 `.env` 已配置。执行：

```powershell
pnpm production:check
docker compose -f compose.yaml -f compose.production.yaml config --quiet
docker compose -f compose.yaml -f compose.production.yaml up --build -d
docker compose -f compose.yaml -f compose.production.yaml ps
```

Caddy 使用固定的 `2.11.4-alpine` 镜像、自动 HTTPS、HSTS、安全响应头和压缩。生产覆盖文件会移除 PostgreSQL、API、Web 的宿主机端口，只保留 Caddy 的 80/443。

## Supabase 可选模式

- PostgreSQL：把 `DATABASE_URL` 换成 Supabase 提供的私有连接或连接池地址；数据库迁移仍由 Alembic 执行。
- Storage：设置 `STORAGE_BACKEND=supabase`、`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY` 和私有 bucket 名称。
- service-role key 只允许存在于 API/Worker 环境。适配器只把它放在认证请求头，不写入 URL、数据库、浏览器或错误正文。
- bucket 必须是私有 bucket；下载通过短时签名 URL。Supabase 官方说明 service key 会绕过 RLS，因此应使用独立项目、启用平台 MFA，并把密钥当作最高权限凭证。

Supabase 适配器有 Mock HTTP 自动测试，但没有真实项目密钥，因此 Phase 6 不会宣称完成了真实 Supabase 联调。

## 更新与回退

更新前先执行加密备份和恢复演练。然后拉取明确提交、重建镜像并检查迁移：

```powershell
pnpm backup:create -- --encrypt
pnpm backup:drill -- <备份目录>
git pull --ff-only
docker compose up --build -d
docker compose ps
```

禁止 `git reset --hard`、强推和 `docker compose down -v`。若新迁移不兼容旧程序，不能只回退镜像；应使用已验证备份执行完整恢复。

## 参考

- NATAPP 官方购买和价格页：<https://natapp.cn/>
- NATAPP HTTPS 说明：<https://natapp.cn/article/https>
- NATAPP 安全设置：<https://natapp.cn/article/whitelist>
- Caddy 自动 HTTPS 与反向代理：<https://caddyserver.com/docs/>
- Supabase Storage 访问控制：<https://supabase.com/docs/guides/storage/security/access-control>
