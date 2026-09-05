# 腾讯云香港 Lighthouse 部署

本目录用于一台 Ubuntu 22.04/24.04、2 核 2GB 的腾讯云香港轻量应用服务器。Caddy 是唯一公网入口，自动签发和续期 HTTPS 证书；FastAPI 只在 Docker 内网暴露 8000。应用、SQLite、对话、RSS、金融资讯和复盘缓存使用同一个 `/data` 持久卷，保持单实例、单 worker。

本方案面向一台全新的服务器。不要先运行仓库根目录的旧 `compose.yaml`，也不要把旧 Compose 项目直接切换到本目录；旧项目的卷名和公网端口不同。如服务器已经运行过旧方案，先停机、导出数据并确认卷名，再单独制定迁移步骤。

## 1. 购买与防火墙

在腾讯云购买页选择：中国香港、Ubuntu 24.04 LTS 64 位（没有则 22.04）、2 核 2GB、SSD 40GB 或以上。服务器防火墙只开放：

- TCP 22：优先限制为自己的固定公网 IP；需要移动网络登录时再临时放宽。
- TCP 80：`0.0.0.0/0`，用于 HTTP 跳转和证书签发。
- TCP 443：`0.0.0.0/0`，用于正式 HTTPS 访问。
- 不开放 8000、数据库端口或 Docker API 端口。

## 2. 域名

在域名 DNS 中增加一条 A 记录，例如：

```text
主机记录: research
记录值:   服务器公网 IP
```

等待 `research.vincentli-website.com` 解析到服务器公网 IP 后再启动 Caddy。不要先开启严格 HSTS 或删除旧站点，临时验收通过后再切换正式域名。

## 3. 安装 Docker 与 Git

SSH 登录服务器后，按 Docker 官方 Ubuntu 安装文档安装 Docker Engine 和 Compose 插件，并安装 Git。确认以下命令都成功：

```bash
docker version
docker compose version
git --version
```

仓库是私有仓库。推荐在服务器生成一把只读 SSH key，并将公钥添加到 GitHub 仓库的 Deploy keys；不要把个人 GitHub 密码或长期访问令牌写在服务器命令历史中。

```bash
sudo mkdir -p /opt/ft-research
sudo chown "$USER":"$USER" /opt/ft-research
git clone git@github.com:lizhuoheng273-debug/FT-Research.git /opt/ft-research/app
cd /opt/ft-research/app
git switch main
```

## 4. 设置密码与环境变量

复制模板：

```bash
cd /opt/ft-research/app/deploy/tencent-lighthouse
cp .env.example .env
```

生成管理员密码哈希。密码输入时终端不会显示字符，这是正常的：

```bash
cd /opt/ft-research/app
python3 scripts/owner_password.py
```

编辑 `deploy/tencent-lighthouse/.env`：

- `DOMAIN` 填域名，不带 `https://`。
- `GLM_API_KEY` 填真实密钥。
- `FT_OWNER_PASSWORD_HASH` 填刚生成的完整结果；建议用单引号包住，避免 `$` 被 Compose 展开。
- `FT_ALLOWED_ORIGINS`、`VR_ALLOW_ORIGINS` 都填 `https://你的域名`。
- `VR_API_KEY` 保持为空。公开访客由管理员/访客会话、逐路由权限和限额保护；设置共享 key 会让面试官无法直接进入访客体验。
- 访客会话创建也按 IP 和全站每小时限流，过期访客会由后台定期清理；通常保留模板默认值即可。
- `.env` 不得提交到 Git。

在启动前运行强制检查：

```bash
cd /opt/ft-research/app
python3 scripts/production_preflight.py deploy/tencent-lighthouse/.env
```

只有看到 `production environment is ready` 才继续。

## 5. 首次部署

```bash
cd /opt/ft-research/app
python3 scripts/lighthouse_ops.py deploy
```

查看状态和日志：

```bash
cd /opt/ft-research/app/deploy/tencent-lighthouse
docker compose ps
docker compose logs --tail=200 ft-research
docker compose logs --tail=100 caddy
curl -fsS https://research.vincentli-website.com/api/health
```

健康接口应返回 `ok: true`。部署命令最多等待 180 秒确认应用健康；Caddy 对流式响应使用立即刷新模式，AI 对话不会被代理层缓冲。两个容器都启用了日志轮转，避免长期运行挤满系统盘。首次上线只发送 1 天有效且不包含子域名的 HSTS；连续稳定运行后再评估延长时间。

## 6. 更新

先备份，再从 `main` 快进更新并重新构建：

```bash
cd /opt/ft-research/app
python3 scripts/lighthouse_ops.py backup
python3 scripts/lighthouse_ops.py update
```

更新前会确认服务器处于 `main` 且工作目录完全干净，再执行 `git pull --ff-only origin main`；存在分叉、手工代码改动或意外文件时都会停止，不会强行覆盖或把它们打入镜像。部署工具会移除终端中所有可能覆盖部署配置的同名变量，只采用已通过检查的文件值。

## 7. 备份与恢复

备份命令会把管理员身份、管理员对话和事件导出到持久卷，并复制一份到：

```text
deploy/tencent-lighthouse/backups/owner-YYYYMMDD-HHMMSS.sqlite3
```

该备份不包含访客、会话令牌或原始 WAL 页面，也不是完整 `/data` 备份。应定期把备份下载到本机；仅留在同一台服务器不算灾难恢复。首次上线后、每次大版本更新前，必须在腾讯云控制台创建系统盘快照，并至少做一次从快照创建临时实例的恢复验证；系统盘快照负责覆盖上传研报、持仓、缓存和 Docker 数据卷。

恢复前必须停止应用，且目标数据库必须不存在。参考项目根目录 `docs/OWNER_GUEST_DEPLOYMENT.md`，不要直接覆盖运行中的 SQLite。

## 8. 上线验收

依次验证：

1. `/api/health` 返回 200，页面刷新不会 404。
2. 管理员登录、退出和 HTTPS Cookie 正常。
3. 访客无需共享 API key，且管理员/访客自选股和对话隔离。
4. AI 首字输出、工具进度、停止和断线恢复正常。
5. RSS、金融资讯、日程和每日复盘可以手动刷新并在后台自动更新。
6. 股票搜索、个股新闻、指数 K 线和备用数据源正常。
7. `docker compose restart ft-research` 后管理员对话、缓存和研报仍存在。
8. 浏览器控制台没有持续报错，服务器没有 OOM 或反复重启。

## 9. 运维约束

- 保持一个 `ft-research` 实例和一个 uvicorn worker；SQLite 不支持本项目直接横向扩容。
- 不将 `.env`、备份、SQLite、上传研报或 `/data` 提交到 GitHub。
- 每周检查磁盘、内存、容器状态、GLM 余额和数据源状态；每次更新前确认最新系统盘快照可用。
- 域名切换、服务器销毁、磁盘重置和恢复备份前先创建腾讯云快照。
