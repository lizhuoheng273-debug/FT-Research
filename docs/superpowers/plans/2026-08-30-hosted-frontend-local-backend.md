# FT-Research 前端托管与后端本机启动实施计划

## 目标

让 FT-Research 前端可以部署到 Cloudflare Pages（或其他静态托管），同时由用户自己的 Windows 电脑运行 FastAPI 后端。生产构建通过 `VITE_API_URL` 指向本机后端，开发环境继续使用 Vite `/api` 代理。

## 约束与边界

- 只改 FT-Research，不修改上游 Vibe-Research。
- 不上传 `backend/.env`、GLM Key、持仓、自选股或缓存。
- 本方案适用于用户本人在运行后端的同一台电脑上使用托管前端；其他访客的浏览器访问 `127.0.0.1` 会指向访客自己的电脑，不能共享本机后端。
- Cloudflare/Vercel 的账号登录、项目创建和域名绑定由用户手动完成；仓库只提供可复用配置和启动脚本。

## 实施任务

### 1. 统一前端 API 基地址

- 在 `frontend/src/lib/api.ts` 增加基于 `VITE_API_URL` 的 URL 生成函数。
- 将 API 客户端中直接写死的 `/api` 请求改为统一函数。
- 空值时保持开发代理行为；生产构建可以生成 `http://127.0.0.1:8900/api/...` 请求。
- 同步处理 AI 日报、AI 热点、GLM、详情页和设置页中的直接 `fetch`。

验收：源码不再散落硬编码 API 主机；`VITE_API_URL` 为空和设置为本机地址时均能构建。

### 2. 静态托管配置

- 新增 `frontend/public/_redirects`，让 Cloudflare Pages 的任意前端路由回退到 `index.html`。
- 新增可提交的 `frontend/.env.example`，记录生产前端应设置的 `VITE_API_URL`。
- 不提交真正的 `.env.production`。

验收：生产构建产物包含 `_redirects`，刷新 `/ai/news`、`/finance/review` 等深层路由不会 404。

### 3. Windows 本机后端启动

- 新增 `scripts/start-backend.ps1`：优先使用 `backend/.venv/Scripts/python.exe`，否则使用系统 Python，在 `127.0.0.1:8900` 启动 FastAPI。
- 新增 `scripts/register-backend-task.ps1`：提供用户主动执行的“当前用户登录时启动”计划任务注册脚本，避免把系统任务创建作为隐式副作用。
- 新增 `scripts/unregister-backend-task.ps1`：可移除上述任务，保证可逆。

验收：脚本可被 PowerShell 解析；启动命令和项目路径不依赖当前工作目录；任务注册/移除命令仅作用于 `FT-Research Backend`。

### 4. 部署与安全说明

- 新增 `docs/DEPLOYMENT_LOCAL_BACKEND.md`，记录 Cloudflare Pages 构建设置、本机 Python 环境、`.env` 配置、启动/自启动命令和 localhost 限制。
- 明确说明：如果未来要给其他用户使用，需要把后端迁移到公网服务或通过经过认证的隧道暴露，不能把 `127.0.0.1` 当作公共 API。

### 5. 验证

- 运行前端现有测试。
- 运行一次带 `VITE_API_URL` 的生产构建。
- 运行后端离线测试（若当前 Python 环境可用）。
- 对 PowerShell 脚本做语法解析并执行 `git diff --check`。

