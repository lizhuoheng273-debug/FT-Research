# 主人 / 游客同源部署

这是一个单进程、自托管演示部署方案，不是高可用或多租户 SaaS。公开演示必须配置 `FT_OWNER_PASSWORD_HASH`（运行 `python scripts/owner_password.py` 生成）、`FT_PUBLIC_DEMO=true`，以及真实 HTTPS 反向代理后的 `FT_AUTH_SECURE_COOKIE=true`。没有 TLS 时只用于本机开发，不能宣称生产就绪。

前端和 `/api` 由同一个 FastAPI 进程提供，SQLite 位于 `/data` 持久卷；只运行一个 uvicorn worker。备份使用 `scripts/owner_backup.py export --db /data/sessions.sqlite3 --out /path/owner.sqlite3`，恢复前必须停止服务且目标文件不存在。备份只包含主人身份、主人对话及其事件，不包含游客、会话令牌或原始 WAL 页面。

游客令牌只存在当前页面内存。站内切换会继续生成；刷新或退出即回到入口。游客最多 5 次体验提问，断开 90 秒后后台取消，闲置或绝对期限到达后清理。模型调用按次数和输入/输出长度限制计费，不等同于人民币封顶。
