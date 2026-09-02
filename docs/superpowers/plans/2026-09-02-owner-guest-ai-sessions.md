# FT-Research Owner / Guest AI Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个主人账号和独立临时游客身份，提供切页不中断、可恢复与可管理的 AI 对话，支持个人使用和公开作品演示。

**Architecture:** React 使用应用级会话客户端；FastAPI 单进程独立运行 GLM 任务，以 SQLite 保存身份、对话、运行状态与增量事件。主人持久登录，游客令牌只保存在页面内存。鉴权、资源归属、额度与取消在后端执行。

**Tech Stack:** 现有 React 19、TypeScript、React Router 7、FastAPI、requests、Python sqlite3 / hashlib.scrypt / secrets；沿用现有 GLM 和 NDJSON，不新增 Redis 或外部账号系统。

**Spec:** `docs/superpowers/specs/2026-09-02-owner-guest-ai-sessions-design.md`。实施前全文阅读；本文件的代码块是要落实的核心合同与测试，不是已经存在的 API。

## Global Constraints

- 一个项目同时满足个人使用、求职演示和开源自部署，不建立注册、邮件验证、组织、付费订阅系统。
- SQLite 位于持久化的 `VR_DATA_DIR`，不位于静态资源目录；开启外键、WAL、busy_timeout 和版本化迁移。
- 单后端 worker，无多实例高可用承诺。进程重启不恢复执行，只恢复已存内容和 interrupted 状态。
- 游客使用服务器生成的独立随机令牌，仅保存在当前页面内存，作为 Bearer 发送；不写 localStorage、sessionStorage 或 URL。服务端只保存令牌摘要。
- 游客刷新即重新开始是本计划的明确默认值，不承诺刷新后保留游客记录。
- API 按 public / authenticated / owner 分类，未分类默认拒绝。
- 订阅断开与取消任务是两个不同操作。
- 发布/部署另行授权。

---

## 追加范围：信源刷新与每日复盘卡片（2026-09-02）

用户要求先保存主计划，将以下局部修复一起纳入。主人的登录/游客/对话计划不变；以下作为独立附加阶段 A，可先实施并单独验收，不需要等待完整账号改造。本次仅排查并保存方案，尚未修改运行代码。

**排查证据：**

- `backend/rss.py` 的 `CACHE_TTL_SECONDS=1800`；`_read_snapshot` 在最后成功抓取超过30分钟或存在抓取错误时返回 `stale=true`。这表示缓存待更新/更新失败，不表示文章不真实或发布日期失效。
- 调度器每轮抓完全部默认信源后再等待1800秒，因此实际间隔是“抓取耗时+30分钟”，存在正常抓取间隙也标过期的窗口。
- `AINews.tsx` 顶部刷新只重新 GET `/api/ai/rss/sources`；后者只读缓存。当前没有单卡片的强制抓取入口，自定义信源也没有纳入 `refresh_builtins`。
- 本次只读检查10个默认信源：9个正常，Solidot返回 `RSS 抓取失败：The read operation timed out`，仍有3条缓存；最后成功时间为2026-09-02 23:08:05（北京时间）。随后直接只读抓取Solidot成功，解析20条，未写缓存。证据支持临时超时，而非永久失效；不保证每次重试都成功。
- `DailyReview.tsx` 涨跌停/成交额外层使用 `grid items-start`，子卡片按各自内容高度显示。
- `MarketReviewModal.tsx` 在 `bg-black/60` 遮罩上使用半透明 `.glass`；`EmotionDetails` 内指标卡使用 `bg-muted/30` 和 `bg-muted/20`，共同造成浅色主题发灰。尚未做浏览器像素/尺寸验收。

### A1. 逐信源刷新与准确状态

**Files:** 修改 `backend/rss.py`、`backend/app.py`、`backend/tests/test_rss.py`、`backend/tests/test_rss_api.py`、`frontend/src/pages/AINews.tsx`、`frontend/src/components/ai/AISubscriptionFeed.tsx`、`frontend/src/lib/rssSubscriptions.ts`；新增 `frontend/src/lib/rssRefresh.ts`、`frontend/tests/rss-refresh.test.mjs`。

**Interfaces:** 新增 `POST /api/ai/rss/refresh`，内置源 body 为 `{sourceId}`，自定义源为 `{sourceId,url}`。内置 URL 仅从服务器白名单取值；自定义 URL 沿用现有 SSRF 校验、重定向检查、大小与超时限制，并核对规范化URL生成的custom id。不新增任意HTTP代理。

返回 `{source: RssSource, outcome: 'updated' | 'cached'}`，更新失败且存在缓存时 `outcome='cached'`；没缓存也返回真实空数据及错误，不能提示刷新成功。未知sourceId404、非法URL400、刷新冷却429（含Retry-After）。`RssSource`增加 `lastAttemptAt`、`staleReason: 'ttl'|'fetch_failed'|null`、`errorCode: 'timeout'|'http'|'parse'|'security'|'unknown'|null`，保留旧字段合同。后端新增 `RssCatalog.refresh_source(source_id, custom_url=None)` 包装已有刷新能力。

- [ ] 先补测试：缓存超时与抓取失败可区分；刷新成功清除旧错误；刷新失败保留原文章和lastSuccessAt。最小刷新恢复用例：

```python
def test_single_source_recovers_from_timeout(tmp_path):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda url: RSS, validate_dns=False)
    first = catalog.refresh_source('solidot')
    catalog.fetcher = lambda url: (_ for _ in ()).throw(TimeoutError('read timeout'))
    failed = catalog.refresh_source('solidot')
    assert failed['source']['items'] == first['source']['items']
    assert failed['source']['lastSuccessAt'] == first['source']['lastSuccessAt']
    assert failed['source']['staleReason'] == 'fetch_failed'
    catalog.fetcher = lambda url: RSS
    recovered = catalog.refresh_source('solidot')
    assert recovered['outcome'] == 'updated'
    assert recovered['source']['stale'] is False
    assert recovered['source']['error'] is None
```

该单元测试调用catalog底层，不经过HTTP冷却；路由层另用假时钟验证冷却，不能用sleep等待。RED命令：`python -m pytest backend/tests/test_rss.py backend/tests/test_rss_api.py -q`，新增用例应先因合同缺失失败。

- [ ] 同源自动刷新与手动刷新采用按URL的single-flight锁，防止旧失败覆盖新成功；源锁贯穿抓取和缓存结果写入，而不是只保护文件replace。HTTP同源30秒冷却、限制总并发4、使用当前8秒连接/12秒读取及明确的总时限；不能多次点击堆积无限抓取。失败保留旧缓存，不改其成功时间。
- [ ] 自动刷新按每源下一次到期时间调度、忙源不重入；正常30分钟检查不因本轮其它慢源额外推迟。缓存超过30分钟显示“待更新”，有失败显示“更新失败 · 使用缓存”，未成功显示“暂不可用”；不靠扩大TTL隐藏失败。
- [ ] 每张卡片增加带 `aria-label="刷新{媒体名}"` 的刷新按钮；只有本卡转圈和禁用，原3条内容继续可见，不触发全页面骨架或热点榜请求。超时、失败、无新文章与成功分别给可理解提示；成功取得相同文章说明“已检查，暂无新内容”，不谎称新增新闻。
- [ ] `rssRefresh.ts` 提供 `createRssRefresher(request, onSource)`，返回 `refresh(source): Promise<void>`、`isRefreshing(id): boolean`、`dispose(): void`；按sourceId独立AbortController/request序号，同卡重复请求不重入，卸载中止并忽略晚到结果。AINews的整页缓存读取和单卡刷新合并使用lastAttemptAt防旧响应覆盖新结果。自定义源URL取当前浏览器订阅配置，不依赖public snapshot返回URL。
- [ ] 在 `rss-refresh.test.mjs` 使用可控Promise验证A/B两张卡独立、重复点A只有一个请求、失败保留旧列表、dispose之后无回调。接口测试未知ID、内网URL、重定向到内网、并发同源、冷却和旧失败写入竞态。GREEN：上述后端测试、前端 `npm test` 和 `npm run build`。
- [ ] 账号改造接入时，单卡刷新属于主动抓取写操作，限主人；游客可读公共缓存但不触发抓取，按钮禁用并解释。自定义源不因某位游客提交URL加入全局订阅调度。自定义源本轮支持手动刷新，自动订阅调度不扩展为多用户系统。
- [ ] 非刷新可解决的情况：持续超时检查服务端网络/DNS/目标站；403/429遵守源站限制和Retry-After；404核实正式RSS地址并替换；解析错误检查返回是否RSS/Atom或源站结构改变。不绕过访问控制，不把所有404都建议重启后端，不添加未经核实的第三方转发源。
- [ ] 浏览器验收成功源/模拟超时源/空缓存源/自定义源、键盘操作和手机卡片按钮；审查后仅提交本项改动，提交信息 `fix: add per-source RSS refresh and clear cache status`。

### A2. 每日复盘等高与详情白色卡片

**Files:** 修改 `frontend/src/pages/DailyReview.tsx`、`frontend/src/components/market/MarketReviewModal.tsx`；必要时给 `frontend/src/index.css` 添加仅此弹窗的局部样式，不修改全站 `.glass`；新增 `frontend/tests/review-card-layout.test.mjs`。

**Interfaces:** 保持 MarketReviewModal 的 open/title/onClose/children 和全部行情数据合同不变；只改布局与表面颜色。

- [ ] 用现有离线测试方式检查外层从items-start变为items-stretch，两张直接子卡片均h-full；RED：前端 `node --test tests/review-card-layout.test.mjs`。结构测试不作为最终视觉通过证据。
- [ ] 同行桌面布局使用以下结构，不写死像素高度、不隐藏内容撑等高：

```tsx
<div className="mb-6 grid items-stretch gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
  <button className="glass flex h-full w-full flex-col p-4 text-left">{/* 保留涨跌停现有内容 */}</button>
  <GlassCard className="h-full p-4">{/* 保留成交额Top5现有内容 */}</GlassCard>
</div>
```

手机单列时自然高度，不强制两张卡等高；Top5、表头、数据缺失提示和股票跳转全部保留。

- [ ] 弹窗主体去掉半透明glass依赖，使用 `rounded-2xl border border-border bg-card text-card-foreground shadow-2xl`，浅色主题为不透明白色，暗色主题仍用暗色card token；遮罩保持在弹窗外。EmotionDetails的小指标卡改为 `rounded-xl border border-border/60 bg-card p-3 shadow-sm`，保留涨跌红绿语义，不把暗色主题强制白底。
- [ ] GREEN：前端 `npm test`、`npm run build`。浏览器1440px/1024px同行时量测两卡高度差<=1px；390px检查单列、长名字、空数据。打开涨跌停详情检查浅色白底不透黑遮罩、内部指标不再灰块；同时回归共用弹窗的Top20、暗色主题、Esc/关闭与焦点返回。
- [ ] 不修改涨跌家数、封板率、K线、VWAP、AI提示词；审查后仅提交本项布局改动，提交信息 `fix: align review cards and brighten detail surfaces`。

**排期：** 将 A1/A2 与主计划一起跟踪，推荐先交付这两个局部修复，再执行下方 Task1–8；可分开验收和回滚。本轮未运行功能测试、未重启服务、未提交推送。

## 工作区与文件地图

项目根目录：`C:/Users/Vincent/Documents/ChatGPT/咨询平台/FT-Research`。本计划只写文件，没有执行代码修改、测试或部署。

当前分支 `codex/ft-research-v1-v2`，记录基点 `28049a5aee7ed1357ea6efe6186d9350b7bf9818`。存在大量未提交的资讯、RSS、复盘、多空辩论改动。实施前先 `git status --short` 与 `git diff --stat`，确认这些改动如何作为基线保留；不能直接从 HEAD 创建工作树就假定有全部新功能。不能 reset、覆盖、整批 stash 或 `git add .`。如需将旧改动提交/迁移，先取得其明确范围授权。执行工作树使用 using-git-worktrees 技能；后续每项只提交本项文件/已审核的改动块。

| 文件 | 责任 |
| --- | --- |
| 新增 backend/session_store.py | SQLite schema、身份归属、对话/任务/事件事务、迁移与过期删除 |
| 新增 backend/auth.py、backend/auth_routes.py | 密码哈希、令牌会话、Owner/Guest 入口、鉴权依赖与 Origin 校验 |
| 新增 backend/route_policy.py | 路由权限清单，禁止旧接口绕过 |
| 新增 backend/conversation_routes.py | 会话 CRUD、导入、导出、提交/订阅/取消 |
| 新增 backend/ai_jobs.py、backend/ai_limits.py | 有界任务执行、取消、原子预算、超时与恢复 |
| 修改 backend/app.py、chat.py、debate.py、tools.py | lifespan 接线、模型执行适配、工具权限；不复制模型客户端 |
| 新增 frontend/src/lib/authClient.ts、privateStorage.ts、conversationApi.ts、conversationClient.ts | 身份、私人浏览器状态、类型化 API、应用级任务与重连 |
| 新增 frontend/src/components/auth/AuthProvider.tsx、AuthGate.tsx | 登录入口、身份切换与页面门禁 |
| 修改 frontend/src/hooks/useAiChatSession.ts | 保持展示 API，委托全局客户端，不再管理模型生命周期 |
| 修改 frontend/src/components/ai/AiConversation.tsx、ui/AskAiButton.tsx | 状态、新对话/历史操作，关抽屉只取消订阅 |
| 新增 frontend/src/pages/AiHistory.tsx | 本人会话列表、搜索、改名、导出、删除 |
| 修改 frontend/src/pages/FinanceAiWorkspace.tsx、Debate.tsx、router.tsx、main.tsx、components/layout/Layout.tsx | 既有各类视图接入全局会话；历史入口与刷新恢复 |
| 修改 frontend/src/lib/api.ts、llm.ts、ndjson.ts、agents.ts | 统一身份与流式传输；不再用旧直连生成路径 |
| 修改 frontend/src/lib/watchlist.ts、notes.ts、rssSubscriptions.ts、pages/AINewsDetail.tsx、IndexDetail.tsx、Watchlist.tsx | 私人键隔离；主题等非敏感偏好不受影响 |
| 新增 backend/tests/test_session_store.py、test_auth_sessions.py、test_route_policy.py、test_conversation_api.py、test_ai_jobs.py、test_ai_limits.py | 隔离、状态机、重放、清理、配额测试 |
| 新增 frontend/tests/private-storage.test.mjs、conversation-client.test.mjs、auth-session.test.mjs、ai-history.test.mjs | 真实行为测试，不只检查源码字符串 |
| 新增 scripts/owner_password.py、scripts/owner_backup.py、Dockerfile、.dockerignore、compose.yaml、docs/OWNER_GUEST_DEPLOYMENT.md | 安全初始化、仅主人数据备份、同源单容器、数据卷与运维说明 |
| 修改 backend/.env.example、.gitignore、README.md、README_en.md | 配置、忽略私人文件、开源使用说明 |

测试命令在项目根运行，前端命令进入 `frontend`。Windows 可用 `C:/Users/Vincent/AppData/Local/Programs/Python/Python312/python.exe` 替代 `python`，设置 `PYTHONIOENCODING=utf-8`。以下测试依赖只使用临时目录、假时钟、假模型，不自动发起真实收费请求。

## Task 1: SQLite 资源归属与运行状态存储

**Files:** 新增 `backend/session_store.py`、`backend/tests/test_session_store.py`。

**Interfaces:**
- `Principal(id: str, kind: Literal['owner','guest'])` 不可变 dataclass。
- `SessionStore(path: Path, clock: Callable[[], float] = time.time)`；`create_principal(kind) -> Principal`；`create_conversation(principal, kind, source) -> dict`；`get_conversation(principal, conversation_id) -> dict`；`list_conversations(principal, query='', limit=30, cursor=None) -> dict`。
- `create_run(principal, conversation_id, client_request_id, question, context) -> dict`，返回 `{id,status,created}`；相同 requestId 返回原任务，换对话/问题复用同 key 返回 409。
- `append_event(run_id, event_type, payload) -> dict | None`；`events_after(principal, run_id, after) -> list[dict]`；`transition_run(run_id, expected, target) -> bool`。
- `history_for_model(principal, conversation_id, limit=20) -> list[dict]`；`recover_interrupted() -> int`；`delete_conversation(principal, id)`；`purge_guest(principal_id)`；`NotFound` 映射 404。

- [ ] 编写最小隔离与幂等测试，再增加终态/级联删除/未完成轮次排除测试：

```python
from session_store import SessionStore, NotFound
import pytest

def test_isolation_and_retry(tmp_path):
    store = SessionStore(tmp_path / 'sessions.sqlite3')
    a = store.create_principal('guest')
    b = store.create_principal('guest')
    c = store.create_conversation(a, 'chat', {'type': 'watchlist'})
    with pytest.raises(NotFound):
        store.get_conversation(b, c['id'])
    one = store.create_run(a, c['id'], 'request-1', '分析', {})
    two = store.create_run(a, c['id'], 'request-1', '分析', {})
    assert one['id'] == two['id']
    assert one['created'] is True and two['created'] is False
```

- [ ] RED：`python -m pytest backend/tests/test_session_store.py -q`，应因模块/合同缺失失败。
- [ ] 建表：principal、auth_session、conversation、message、run、run_event、usage_counter、legacy_import；全部私人行有可追溯归属，ID 使用随机 UUID，时间存 UTC。`create_principal('owner')` 返回唯一固定主人，guest 每次新建；用仅针对 kind='owner' 的唯一索引防止重复主人。每个线程独立连接；关键事务使用 `BEGIN IMMEDIATE`。核心约束：

```sql
CREATE UNIQUE INDEX run_request_identity ON run(principal_id, client_request_id);
CREATE UNIQUE INDEX event_sequence ON run_event(run_id, seq);
CREATE UNIQUE INDEX active_conversation ON run(conversation_id)
  WHERE status IN ('queued', 'running');
```

- [ ] 归属查询写成 `WHERE id=? AND principal_id=?`；删除先将活动 run 置 stopped 并墓碑标记，再清理 message/event；`append_event` 在事务中检查终态/墓碑，不接受晚到 delta。`recover_interrupted` 只改变 queued/running，不启动模型。
- [ ] GREEN：运行同一测试文件；增加两线程同 key 提交只创建一次，以及另一身份读事件/删对话失败的断言并通过。
- [ ] 审阅仅本项变更后提交：`git add backend/session_store.py backend/tests/test_session_store.py`；`git commit -m "feat: add scoped conversation storage"`。

## Task 2: 主人登录、独立游客与会话过期

**Files:** 新增 `backend/auth.py`、`auth_routes.py`、`tests/test_auth_sessions.py`、`scripts/owner_password.py`；修改 `backend/.env.example`。

**Interfaces:** 消费 Task 1 的 Principal / SessionStore。产生 `AuthService(store, owner_password_hash, clock)`，`login(password) -> (Principal, token)`、`start_guest() -> (Principal, token)`、`authenticate(token, mode) -> Principal`、`heartbeat(token)`、`logout(token) -> Principal`、`expired_guests() -> list[str]`；`require_principal(request)` 与 `require_owner(request)` 用于后续路由。`hash_password(password) -> str`、`verify_password(password, encoded) -> bool`。

- [ ] 编写测试：

```python
from auth import AuthService, hash_password, verify_password, Unauthorized
from session_store import SessionStore
import pytest

def test_guest_is_unique_and_expiration_is_server_side(tmp_path):
    now = [0.0]
    store = SessionStore(tmp_path / 'test.db', clock=lambda: now[0])
    auth = AuthService(store, hash_password('a-long-test-password'), clock=lambda: now[0])
    a, token_a = auth.start_guest()
    b, token_b = auth.start_guest()
    assert a.id != b.id and token_a != token_b
    assert verify_password('wrong', hash_password('correct')) is False
    now[0] = 1801
    with pytest.raises(Unauthorized):
        auth.authenticate(token_a, 'guest')
```

- [ ] RED：`python -m pytest backend/tests/test_auth_sessions.py -q`。
- [ ] 实现 stdlib scrypt 格式 `scrypt$n$r$p$salt$derivedKey`，默认 n=32768/r=8/p=1、32 字节盐、64 字节结果、明确 maxmem=128MiB；常量时间比较。令牌 `secrets.token_urlsafe(32)`，只将 SHA256 摘要入库。主人 12 小时登录有效期，密码错误同文案返回，IP+全局登录限速；生产缺少哈希直接拒绝启动。
- [ ] 实现 spec 的 auth 路由；主人 HttpOnly Cookie，生产 Secure；写请求限制可信 Origin，Cookie 写请求要求 CSRF token；guest Bearer 不兼作 owner key；拒绝同时混用两种身份凭据。心跳仅延长 idle，不延长 2 小时上限；logout 返回被注销的 principal，取消/删除由 Task 4 的生命周期服务执行。
- [ ] `scripts/owner_password.py` 用 getpass 输入并二次确认，输出哈希，不输出密码、不自动写 .env。初始化环境键：`FT_OWNER_PASSWORD_HASH`、`FT_AUTH_SECURE_COOKIE`、`FT_ALLOWED_ORIGINS`、`FT_PUBLIC_DEMO`；不提供可用默认密码。
- [ ] GREEN：同一测试命令；覆盖登录响应不含哈希、令牌数据库不含明文、过期/撤销拒绝、CSRF/Origin 拒绝、主人/游客混用拒绝、暴力尝试429。
- [ ] 逐文件提交本项：`git add backend/auth.py backend/auth_routes.py backend/tests/test_auth_sessions.py scripts/owner_password.py backend/.env.example`；`git commit -m "feat: add owner and temporary guest authentication"`。

## Task 3: 路由门禁与私人浏览器数据隔离

**Files:** 新增 `backend/route_policy.py`、`tests/test_route_policy.py`、`frontend/src/lib/privateStorage.ts`、`frontend/tests/private-storage.test.mjs`；修改 `backend/app.py`、`tools.py` 与文件地图列出的私人存储使用者。

**Interfaces:** 消费 `require_principal/require_owner`。产生 `policy_for(method, path) -> Literal['public','authenticated','owner','deny']`，模板化匹配带参数路径；`allowed_tools(principal) -> set[str]`。前端 `createPrivateStorage(identity, ownerStorage)` 返回 `get(key): string|null`、`set(key,value):void`、`remove(key):void`、`clearMemory():void`；owner 键前缀 `ft:owner:`，guest 仅 Map。

- [ ] 后端新测试枚举注册的全部 `/api` 路由，每条必须显式分类。未知路由 deny；以下行为测试不能只检查源码：

```python
from route_policy import policy_for

def test_private_legacy_endpoints_are_owner_only():
    for method, path in [('GET', '/api/portfolio'), ('POST', '/api/reflect'),
                         ('GET', '/api/myreports/file/report-id')]:
        assert policy_for(method, path) == 'owner'
    assert policy_for('POST', '/api/not-registered') == 'deny'
```

前端测试使用现有 TypeScript transpile + vm loader，导出纯函数；提供内存 ownerStorage，确认 guest 不读写旧主人键：

```javascript
const storage = new Map([['vr-watchlist', '["600519"]']]);
const disk = {getItem:k=>storage.get(k) ?? null, setItem:(k,v)=>storage.set(k,v), removeItem:k=>storage.delete(k)};
const guest = createPrivateStorage({id:'guest-a', kind:'guest'}, disk);
assert.equal(guest.get('watchlist'), null);
guest.set('watchlist', '["000001"]');
assert.equal(storage.has('ft:owner:watchlist'), false);
assert.equal(createPrivateStorage({id:'guest-b',kind:'guest'}, disk).get('watchlist'), null);
```

- [ ] RED：`python -m pytest backend/tests/test_route_policy.py -q`；前端 `node --test tests/private-storage.test.mjs`。
- [ ] 给全部现有 API 分级；公共登录/健康，市场读需认证，持仓/研报/CLI/配置/主动爬取写操作限 owner。替换全局 VR_API_KEY 门禁，不能保留备用绕过。查询参数和请求 body 的 principalId 不参与授权。对工具定义和 dispatch 都应用允许列表，越权工具返回拒绝且不执行。
- [ ] 将 watchlist/notes/RSS/收藏/指数关注读写委托给 privateStorage，保留现有同步业务 API；认证完成后才初始化。owner 旧键迁移需要显式确认，guest 永不读取旧键。主题、布局宽度可仍全局保存。全项目 `rg 'localStorage|sessionStorage|VR_API_KEY' frontend/src backend` 检查无漏网私人读写。
- [ ] GREEN：上述测试 + 后端使用主人/游客 TestClient 验证上传、下载、CLI、配置、隐藏私有页面 API 都不泄露；guest不能借工具绕过。
- [ ] 只暂存本项文件和共享文件的审核块后提交，提交信息 `feat: enforce owner guest data boundaries`，不得一并提交已有资讯/辩论业务改动。

## Task 4: 独立生成任务、额度、清理与断线重放

**Files:** 新增 `backend/ai_jobs.py`、`ai_limits.py`、`tests/test_ai_jobs.py`、`test_ai_limits.py`；修改 `backend/chat.py`、`debate.py`、`app.py`、`backend/.env.example`。

**Interfaces:** 消费 SessionStore、AuthService、allowed_tools。产生 `RunManager(store, runner, limits, clock)`；`submit(principal, conversation_id, request_id, question, context) -> dict`；`cancel(principal, run_id)`；`tick()`；`shutdown()`。注入 `runner(run, control)` 为事件迭代器，control 支持 `cancelled` 和非阻塞取消/关闭活动响应。`Limits.reserve(principal, ip, run_id)` 在每次实际模型调用前执行。事件始终使用 spec envelope。

- [ ] 假模型分两次生成，中间用 threading.Event 阻塞，证明读者离开不取消，并以同 requestId 重试不执行两次：

```python
from threading import Event
from ai_jobs import RunManager
from ai_limits import Limits
from session_store import SessionStore

def test_disconnect_does_not_restart_model(tmp_path):
    release, first_saved = Event(), Event()
    calls = []
    def runner(run, control):
        calls.append(run['id'])
        yield {'type':'delta', 'payload':{'text':'第一段'}}
        first_saved.set()
        assert release.wait(2)
        yield {'type':'done', 'payload':{}}
    store = SessionStore(tmp_path / 'test.db')
    principal = store.create_principal('owner')
    c = store.create_conversation(principal, 'chat', {'type':'review'})
    jobs = RunManager(store, runner, Limits(store), clock=store.clock)
    run = jobs.submit(principal, c['id'], 'r1', '复盘', {})
    try:
        assert first_saved.wait(2)
        events = store.events_after(principal, run['id'], 0)
        assert events[0]['payload']['text'] == '第一段'
        retry = jobs.submit(principal, c['id'], 'r1', '复盘', {})
        assert retry['id'] == run['id'] and len(calls) == 1
    finally:
        release.set()
        jobs.shutdown()
```

- [ ] RED：`python -m pytest backend/tests/test_ai_jobs.py backend/tests/test_ai_limits.py -q`。
- [ ] 实现受限 executor + 有界队列；提交事务先原子检查 requestId、活动任务和预算，再启动工作线程。事件先存储再供订阅，删除/终态拒绝 late writes。requests.Response.close 不能阻塞 FastAPI 事件循环；沿用 debate 的异步取消方式并在各工具/模型阶段间检查 control。
- [ ] chat 严格区分 delta/tool/真实完成/error/EOF，不能 EOF 即完成；工具循环前逐次 `limits.reserve`。达到轮数但无完整答案标失败或明确限制状态，不伪造完成。debate 保留 stage 事件和原角色 UI 合同，将其现有断开即 cancel 改为显式 cancel。
- [ ] 实现 spec 的 5 问/1 次辩论、并发 2、队列 8、8 分钟、4096 输出、4 次模型调用、IP30/全站100 调用预算。4000/24000/20 输入限制在服务端执行；裁剪工具返回与历史后再调用模型。限制错误返回 429/413，不创建空回答。定时收费任务公开部署默认关闭，显式开关并在说明列明另占主人预算。
- [ ] `tick`：guest90秒无心跳取消任务、1800秒闲置或7200秒总时长撤销并删除；Auth logout guest 立即执行 purge。启动 recover_interrupted；每60秒 tick，测试用假时钟不 sleep；日志仅运行ID/状态/错误码，不含正文和令牌。
- [ ] GREEN：同一命令，补齐队列满、两个并发同 requestId、同IP换guest预算不重置、工具循环预算耗尽、停止时其他API仍快速响应、删除后迟到event、restart不再次计费、guestlogout/过期以及ownerlogout任务继续。
- [ ] 仅审核本项块后提交，提交信息 `feat: persist bounded background AI runs`。

## Task 5: 对话 API、历史管理与兼容迁移

**Files:** 新增 `backend/conversation_routes.py`、`tests/test_conversation_api.py`；修改 `backend/session_store.py`、`app.py`、`route_policy.py`。

**Interfaces:** 实现 spec 全部 conversations/runs 路径。列表 `{items: ConversationSummary[], nextCursor: string|null}`；详情 `{conversation, messages, activeRunId}`。`ConversationSummary={id,kind,title,source,updatedAt,status}`。提交 `{clientRequestId, question, context}`，debate 的 code/rounds 通过 context 白名单验证。导入 `{sourceKey, messages}` 返回 `{conversationId, imported}`，按主人和 sourceKey+内容哈希幂等。

- [ ] 在临时库和假 runner 的 TestClient fixture（在本测试文件创建并注入 app.state.services）测试真实 HTTP 生命周期：

```python
def test_another_guest_cannot_read_or_cancel(client, guest_a_headers, guest_b_headers):
    created = client.post('/api/conversations', headers=guest_a_headers,
                          json={'kind':'chat','source':{'type':'watchlist'}}).json()
    cid = created['id']
    for path in [f'/api/conversations/{cid}', f'/api/conversations/{cid}/export']:
        assert client.get(path, headers=guest_b_headers).status_code == 404
    assert client.delete(f'/api/conversations/{cid}', headers=guest_b_headers).status_code == 404
```

- [ ] RED：`python -m pytest backend/tests/test_conversation_api.py -q`。
- [ ] 实现归属检查、分页最大100条、重命名长度1–100字符、导出安全文件名、参数大小限制。run events 在发送任何字节前验证 principal；轮询存储或通知队列合流，按 after+seq 重放；断开只停止消费者。保活使用空行，不产生助手内容。每次循环检查认证有效性，游客logout不能通过旧流继续读。
- [ ] 导入仅 owner：最多每批20会话/每会话40消息、总大小1MB；接受 user/assistant 与白名单工具字段，去除 partial 及未完成成对问题，不接收 system角色。UI用户确认后发送，返回幂等结果再标本地已迁移。失败保留原浏览器副本不覆盖。
- [ ] 旧 `/api/chat`、`/api/debate` 包成鉴权后的同一 manager adapter，禁止新接口已有预算而旧接口无限制；旧 `/api/reflect` 继续 owner-only，禁用公开模式CLI/client自带baseURL。健康API不返回数据路径/私人内容。
- [ ] GREEN：同一测试；覆盖相同requestId重试、别人的run事件/stop404、guest导入403、非法after400、删除活动会话、分页不跨身份、原文中的Markdown/HTML仅作为文本数据不执行。
- [ ] 审核并提交本项块，提交信息 `feat: expose scoped AI history and resumable streams`。

## Task 6: 应用级身份与会话客户端

**Files:** 新增 `frontend/src/lib/authClient.ts`、`conversationApi.ts`、`conversationClient.ts`、`components/auth/AuthProvider.tsx`、`AuthGate.tsx`、`tests/auth-session.test.mjs`、`conversation-client.test.mjs`；修改 `main.tsx`、`lib/api.ts`、`ndjson.ts`、`hooks/useAiChatSession.ts`。

**Interfaces:** `AuthIdentity={id:string,kind:'owner'|'guest',expiresAt:string}`。`ConversationApi` 包含 create/list/get/update/remove/export/import/start/events/cancel，对应 Task5路由；客户端运行相关合同为 `get(id): Promise<ConversationDetail>`、`start(id,input): Promise<{runId,status}>`、`events(runId,after,onEvent,signal): Promise<void>`、`cancel(runId): Promise<void>`。`createConversationClient(api)` 暴露 `attach(conversationId, listener) -> detach`、`send(conversationId, input)`、`stop(conversationId)`、`resetIdentity()`、`snapshot(conversationId)`；attach/detach只管理UI监听，resetIdentity只断开订阅不冒充服务器注销。send Promise 在任务创建并开启订阅后返回，不等待模型生成完毕。

- [ ] 按现有 node:test+TypeScript转译模式加载纯客户端，用注入API发送可控事件；最小测试如下：

```javascript
function createFakeApi() {
  let sink;
  return {
    startCount: 0,
    cancelCount: 0,
    async get(id) {
      return {conversation:{id,kind:'chat',title:'测试',source:{type:'review'},status:'idle'},
              messages:[],activeRunId:null};
    },
    async start() { this.startCount++; return {runId:'run1',status:'running'}; },
    events(runId, after, onEvent, signal) {
      sink = onEvent;
      return new Promise(resolve => signal.addEventListener('abort', () => resolve(), {once:true}));
    },
    async cancel() { this.cancelCount++; },
    emit(event) { assert.ok(sink, 'subscription started'); sink(event); }
  };
}
const api = createFakeApi();
const client = createConversationClient(api);
const detach = client.attach('c1', () => {});
await client.send('c1', {clientRequestId:'r1',question:'复盘',context:{}});
api.emit({runId:'run1',seq:1,type:'delta',payload:{text:'第一段'}});
detach();
api.emit({runId:'run1',seq:2,type:'delta',payload:{text:'第二段'}});
assert.equal(client.snapshot('c1').messages.at(-1).content, '第一段第二段');
assert.equal(api.cancelCount, 0);
assert.equal(api.startCount, 1);
client.resetIdentity();
```

- [ ] RED：前端 `node --test tests/conversation-client.test.mjs tests/auth-session.test.mjs`。
- [ ] 在Router上方放 AuthProvider：启动只检查主人cookie；guesttoken仅内存，guest入口先退出旧身份。主人Cookie请求带credentials与CSRF、游客用Bearer；统一401返回入口并清除私人查询状态。退出先完成服务端撤销，再清内存；网络失败仍清本地并提示服务器将按超时清理。BroadcastChannel只发“身份失效”，不传播令牌。
- [ ] 纯客户端用 Map<conversationId,state> 保存页面外状态；每个流按runId+seq去重，重连 after=lastSeq；重复/乱序不得重复追加，缺口从最后连续seq重放。断线指数退避上限10秒，仅重订阅不重新POST问题；done/error/stop后刷新详情。StrictMode挂载不重复创建/发送问题，send只由用户事件触发。
- [ ] useAiChatSession 委托客户端并保留 msgs/input/loading/error/send/stop 展示接口；卸载仅detach。key变更切订阅而不stop，新股票的context异步加载用身份/股票epoch校验，旧结果不得覆盖；submit前冻结context。保留部分回答可读但不由客户端组装后端历史。
- [ ] 游客心跳每15秒由应用层发送；页面内部路由切换不重建。明确停止调用cancel，离开路由不调用cancel。身份切换旧响应即使晚到也被epoch丢弃。
- [ ] GREEN：同一测试；增加UTF8分块立即显示、未收到done断线重连不标完成、重复seq、快速切股票、guest刷新初始化无token、跨tab注销、仅显式stop调用cancel断言；前端 `npm run build`。
- [ ] 审核仅本项改动后提交，提交信息 `feat: keep AI sessions alive across navigation`。

## Task 7: 统一历史与现有聊天/辩论界面接线

**Files:** 新增 `frontend/src/pages/AiHistory.tsx`、`frontend/tests/ai-history.test.mjs`；修改文件地图的 AiConversation / AskAiButton / FinanceAiWorkspace / Debate / Layout / router / llm / agents 及现有相关测试。

**Interfaces:** 消费 ConversationSummary、createConversationClient、AuthProvider身份。新增 `/ai/conversations` 历史页；打开chat根据source前往既有工作台或共享对话视图并带 `conversationId`，打开debate前往 `/finance/debate?conversationId=...`。旧股票/分类source仍隔离，不再用URL作为唯一历史主键。

- [ ] 提取 `conversationDestination(summary) -> string` 到 conversationApi 并编写路由行为测试：

```javascript
assert.equal(conversationDestination({id:'abc',kind:'debate',source:{type:'debate'}}),
             '/finance/debate?conversationId=abc');
assert.match(conversationDestination({id:'xyz',kind:'chat',source:{type:'stock',code:'600183'}}),
             /conversationId=xyz/);
```

- [ ] RED：前端 `node --test tests/ai-history.test.mjs`。
- [ ] 新增列表/搜索/空状态/改名/删除确认/导出/新对话；标题默认第一条问题截取30字，不额外调用GLM。guest显示“仅本次体验”与剩余额度。主侧栏新增AI对话；私人隐藏页面guest禁用，访问直接URL也有门禁而非只隐藏菜单。
- [ ] 抽屉close/Esc/backdrop和工作台返回删除 `session.stop()`；生成中导航展示“后台生成中”状态，可从历史重新进入。清空按钮改为“新对话”，删除在历史确认。workspace刷新携带conversationId恢复，未带ID可以新建但不自动发送模型请求。
- [ ] 辩论通过同一client保存bull/bear/referee阶段，loading由run状态派生，停止保留半截阶段；仅完整结果启用原笔记保存。替换旧的“unmount必须abort生成”测试为“卸载只detach”，保留显式停止验证。
- [ ] 主人首次见到旧本地历史显示数量和迁移确认；导入成功保留本地只读备份直至用户确认清理；guest不扫描或展示数量。owner旧自选/笔记/收藏迁移也必须确认，不把已在guest体验中的内存内容导入owner。
- [ ] GREEN：`npm test`、`npm run build`；使用浏览器技能做桌面/移动端验收：两个guest独立环境+owner，发送假模型分块流，切页返回、历史继续、键盘Enter/Shift+Enter、stop、partial提示、刷新和退出。截图不得包含Key或私人旧记录；真实模型仅在授权后做一轮小样本。
- [ ] 审核仅本项改动后提交，提交信息 `feat: add unified AI conversation history`。

## Task 8: 同源部署、开源卫生与完整验收

**Files:** 新增 `Dockerfile`、`.dockerignore`、`compose.yaml`、`scripts/owner_backup.py`、`docs/OWNER_GUEST_DEPLOYMENT.md`、`backend/tests/test_demo_deployment.py`；修改 `.gitignore`、`backend/.env.example`、`backend/app.py`、`README.md`、`README_en.md`。

**Interfaces:** 消费所有前序模块。部署只运行一个 `uvicorn app:app` worker，`VR_DATA_DIR=/data` 绑定持久卷；`FT_PUBLIC_DEMO=true` 启用鉴权与guest预算。同源静态站SPA fallback不覆盖未知`/api`，所有私人数据目录不挂载为静态目录。

- [ ] 编写静态与API边界测试，测试fixture使用临时frontend dist和data目录：

```python
def test_spa_does_not_expose_database(deployed_client):
    assert deployed_client.get('/finance/watchlist').status_code == 200
    response = deployed_client.get('/api/unknown-endpoint')
    assert response.status_code in (401, 404)
    assert 'text/html' not in response.headers.get('content-type', '')
    assert deployed_client.get('/data/sessions.sqlite3').status_code == 404
    assert deployed_client.get('/.env').status_code == 404
```

- [ ] RED：`python -m pytest backend/tests/test_demo_deployment.py -q`。
- [ ] Docker用前端build阶段生成dist，Python阶段安装现有requirements，非root运行，固定单worker，数据目录权限仅服务账号。compose只暴露一个服务端口、挂载/data，读取服务器.env。生产TLS由平台/reverseproxy负责；未配置TLS不得关闭Secure Cookie冒充生产就绪。本机开发绑定127.0.0.1并允许本机HTTP。
- [ ] .gitignore与.dockerignore排除.env、密钥、*.sqlite*、*-wal、*-shm、.cache、个人data/portfolio/myreports、浏览器认证状态、旧备份；允许.env.example。README写明主人哈希初始化、guest限制、刷新规则、SQLite持久盘/单worker、模型成本、服务离线影响。
- [ ] `scripts/owner_backup.py export --db PATH --out PATH` 在一致性读事务内逻辑导出 owner 及其 conversation/message/run/run_event/legacy_import 到一个新数据库，不复制 guest、auth_session 或原始数据库/WAL页面。`restore --from PATH --db PATH` 要求服务停止、目标不存在，验证schema及owner归属后创建目标；恢复的活动run转interrupted。不能先复制全库再DELETE游客就声称备份没有游客数据。补测备份只含主人、无令牌、外键正确、目标存在则拒绝覆盖。
- [ ] 游客行清理不承诺磁盘安全擦除。发布前扫描当前文件和git历史的secret；发现泄露先报告并轮换，未经授权不改写历史。
- [ ] 公开模式禁用未授权私有抓取展示和自动付费定时任务，保留许可说明。市场公共缓存与聊天数据库分别存放，不把上游全文/个人研报打包开源。文档分别描述本机开发和公开演示，不自动改动现有Cloudflare项目。
- [ ] GREEN：`python -m pytest backend/tests -m "not live" -q`；前端 `npm test`、`npm run build`。执行新部署测试、接口权限枚举测试、两个guest+owner浏览器隔离矩阵；无Docker时明确记录容器验收未完成，不能声明生产就绪。
- [ ] 独立审查授权、取消/清理、重复收费、历史迁移与日志五方面；用 requesting-code-review 技能。仅实际证据通过后提交本项，提交信息 `docs: prepare secure owner guest demo deployment`。推送公开仓库、部署或清理旧数据仍需单独授权。

## 自审覆盖与交付检查

| 规格 | 落地任务 |
| --- | --- |
| 主人持久历史、独立游客、退出与超时 | 1、2、4、6 |
| 切页继续、增量重放、停止、重启中断、避免重复计费 | 1、4、5、6 |
| 历史列表/搜索/新建/改名/删除/导出 | 5、7 |
| 股票/页面/日期上下文、旧记录迁移、debate阶段 | 5、6、7 |
| 私有文件API/工具/浏览器数据隔离 | 2、3、5、6 |
| 限额、IP防绕过、输入/工具/输出边界 | 4 |
| 同源、Windows、持久盘、开源许可与密钥检查 | 2、8 |

验收不能用“UI隐藏了”“localStorage换了key”代替服务端隔离，不能用“HTTP返回200”代替真正分块到达，不能用“页面离开后不报错”代替后端继续运行。

本计划完成后可选择在当前任务分阶段实施，或交给子任务逐项执行并在阶段间审查。当前尚未选择执行方式，不派发工作、不调用付费模型、不改运行网站。
