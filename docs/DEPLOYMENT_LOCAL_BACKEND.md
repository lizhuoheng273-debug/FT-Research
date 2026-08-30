# FT-Research：前端托管、后端本机启动

本项目可以把 React/Vite 前端部署到 Cloudflare Pages，同时让 FastAPI 和 GLM 配置留在自己的 Windows 电脑上运行。

## 先理解使用边界

生产前端通过 `VITE_API_URL` 调用后端。当前方案的地址是 `http://127.0.0.1:8900`，因此它只对“运行后端的这台电脑上的浏览器”有效：

- 你在自己的电脑打开托管前端：可以调用本机行情、日报、GLM 等接口。
- 其他人打开同一个网址：`127.0.0.1` 会指向他们自己的电脑，不能访问你的本机后端。
- 如果将来需要多人共享，需要把后端迁移到受保护的公网服务，或使用带鉴权和访问控制的安全隧道；不能直接把本机端口暴露到公网。

## Cloudflare Pages 设置

在 Cloudflare Pages 中连接 `FT-Research` 仓库：

| 设置项 | 值 |
| --- | --- |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | 使用 Cloudflare 当前 LTS 版本 |
| 环境变量 | `VITE_API_URL=http://127.0.0.1:8900` |

`frontend/public/_redirects` 会被复制到构建产物，让 `/ai/news`、`/finance/review` 等 React 深层路由在刷新时仍回到 `index.html`。

若使用 Vercel，Root Directory、Build Command 和 Output Directory 使用同样的值；需要在 Vercel 控制台增加等价的 SPA rewrite 配置。

## 本机后端首次准备

在 PowerShell 中执行：

```powershell
cd "C:\Users\Vincent\Documents\ChatGPT\咨询平台\FT-Research"
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

编辑 `backend/.env`，至少填入本机的 `GLM_API_KEY`。这个文件已被 `.gitignore` 排除，不能提交到 GitHub。

启动后端：

```powershell
.\scripts\start-backend.ps1
```

验证：浏览器打开 `http://127.0.0.1:8900/api/health`，应返回健康状态 JSON。停止服务可在运行窗口按 `Ctrl+C`。

## 登录 Windows 后自动启动

这是用户主动执行的系统任务，不会在安装依赖或构建时自动创建：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register-backend-task.ps1
```

任务名为 `FT-Research Backend`，仅在当前用户登录时启动，运行级别为普通用户。移除任务：

```powershell
.\scripts\unregister-backend-task.ps1
```

如果后端依赖尚未安装，任务会启动失败；先完成首次准备再注册任务。

## 本地开发与托管前端的区别

- `npm run dev`：`VITE_API_URL` 留空时，Vite 将 `/api` 代理到 `127.0.0.1:8900`。
- Cloudflare Pages：构建时设置 `VITE_API_URL`，前端直接请求该地址。
- `backend/.env` 只放 GLM Key、访问密钥和本地数据源配置；前端环境变量不放任何模型 Key。

如果浏览器因网络策略拒绝 HTTPS 页面访问本机 HTTP 接口，可先使用本地 `npm run dev` 验证，或后续为后端配置 HTTPS 的本机/安全隧道入口。不要为了绕过限制而关闭浏览器安全策略。

## 发布前检查

```powershell
git status --short
```

确认输出中没有 `backend/.env`、`backend/.cache`、`portfolio.json`、`my-watchlist.json` 或其他本地数据。Cloudflare Pages 只托管前端静态文件，不会获得 GLM Key。
