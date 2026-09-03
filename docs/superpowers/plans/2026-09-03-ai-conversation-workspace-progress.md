# AI 对话工作区与工具进度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加快数据工具调用、显示真实阶段进度，并将对话列表和自动命名整合进 AI 对话工作区。

**Architecture:** 后端用并行工具调用、最小查询窗口、TTL 缓存和非阻塞 20 秒截止时间减少等待；同一条 NDJSON 流发送模型/工具 progress 事件。前端将 progress 归并到会话状态，AI 工作区采用左侧会话列表加中间对话的两列布局，右侧栏完全移除；服务端在首次提问时生成默认标题。

**Tech Stack:** FastAPI、SQLite、Python threading/queue、React、TypeScript、React Router、Node test runner、Vite。

**Spec:** `docs/superpowers/specs/2026-09-03-ai-conversation-workspace-progress-design.md`

## Global Constraints

- 工具调用并行上限为 4 个；模型原始调用顺序决定回填顺序。
- 单个工具截止时间为 20 秒；超时转换为结构化数据缺口并继续分析。
- 只显示“模型分析中……”和“正在调用：……”等阶段状态，不展示隐藏思维链。
- AI 工作区删除右侧栏；上下文仍作为请求快照提交给后端。
- `/ai/conversations` 保留并重定向到 `/finance/ai`，不删除已有会话或导出能力。
- 自动标题格式为“入口名称 · 问题摘要”；只有标题为“新对话”时更新。
- 每个实现任务必须先写失败测试、运行确认失败，再写最小生产代码。

---

### Task 1: 工具执行边界和行情请求加速

**Files:**
- Create: `backend/tool_runtime.py`
- Modify: `backend/tools.py`
- Modify: `backend/research_chart.py`
- Modify: `backend/market_chart.py`
- Test: `backend/tests/test_tools.py`
- Test: `backend/tests/test_research_chart.py`
- Test: `backend/tests/test_market_chart.py`

**Interfaces:**
- `run_with_deadline(fn, timeout_seconds) -> ToolOutcome`：返回 `ok`、`timeout` 或 `error`，超时不阻塞 AI worker。
- `execute_scoped_tool(name, args, allowed_tool_names, timeout_seconds=20.0) -> dict`：返回工具结果或 `{status: "unavailable", data_gap: str}`。
- `market_chart.get_chart(asset, code, period, adjust="qfq", count=60)`：保留旧调用兼容，按 count 计算请求窗口。

- [ ] **Step 1: 写失败测试**

```python
def test_slow_tool_times_out_without_blocking_worker(monkeypatch):
    def slow(_args):
        time.sleep(0.2)
        return {"status": "ok"}
    monkeypatch.setitem(tools._HANDLERS, "slow_test", slow)
    started = time.monotonic()
    result = tools.execute_scoped_tool("slow_test", {}, None, timeout_seconds=0.02)
    assert time.monotonic() - started < 0.12
    assert result["status"] == "unavailable"
    assert "超时" in result["data_gap"]
```

在 `test_market_chart.py` 断言 `_fetch_from_akshare` 收到 `count=30`；在 `test_research_chart.py` 断言板块历史请求不再固定从 1095 天前开始。

- [ ] **Step 2: 运行失败测试**

Run: `pytest backend/tests/test_tools.py backend/tests/test_research_chart.py backend/tests/test_market_chart.py -q`

Expected: `execute_scoped_tool` 尚不存在或慢函数超过 0.12 秒，新增测试失败。

- [ ] **Step 3: 实现最小工具边界**

新增 daemon worker + `queue.Queue(maxsize=1)` 的截止执行器；使用有界 semaphore 限制遗留上游调用数量。工具超时统一返回 `{"status":"unavailable","data_gap":"数据源响应超过 20 秒，已跳过"}`，不向上层抛出未处理异常。

- [ ] **Step 4: 缩小窗口并缓存**

让 `_akshare_rows`、`_fetch_from_akshare`、`_fetch_sector_points` 接收 count；日线请求 `count+30` 个交易日，周线请求 `(count+8)*7` 天，月线请求 `(count+3)*31` 天，分时请求最近 10 个交易日。板块目录和成功摘要使用带 TTL 的进程缓存，失败时复用 stale 结果。

- [ ] **Step 5: 运行绿色测试并提交**

Run: `pytest backend/tests/test_tools.py backend/tests/test_research_chart.py backend/tests/test_market_chart.py -q`

Expected: 0 failures；随后执行 `git add backend/tool_runtime.py backend/tools.py backend/research_chart.py backend/market_chart.py backend/tests/test_tools.py backend/tests/test_research_chart.py backend/tests/test_market_chart.py` 和 `git commit -m "perf: bound and optimize AI data tools"`。

### Task 2: 并行工具调用和 progress 事件

**Files:**
- Modify: `backend/chat.py`
- Modify: `backend/ai_jobs.py`
- Test: `backend/tests/test_chat_stream.py`
- Test: `backend/tests/test_ai_jobs.py`

**Interfaces:** `run_chat_stream` 新增 `progress` 事件；payload 必须含 `phase`、`status`、`message`，工具阶段额外含 `tool` 和 `elapsedMs`。

- [ ] **Step 1: 写失败测试**

```python
def test_independent_tools_start_in_parallel_and_emit_progress(monkeypatch):
    starts = []
    barrier = threading.Barrier(2)
    def fake_tool(name, args, allowed, timeout_seconds=20.0):
        starts.append(time.monotonic())
        barrier.wait(timeout=0.5)
        return {"status": "ok", "tool": name}
    monkeypatch.setattr(chat, "execute_scoped_tool", fake_tool)
    monkeypatch.setattr(chat, "_call_llm_stream", fake_two_tool_round_then_answer)
    events = list(chat.run_chat_stream(fake_cfg(), [{"role":"user","content":"测试"}]))
    assert len(starts) == 2 and abs(starts[0] - starts[1]) < 0.05
    assert any(e["type"] == "progress" and e["payload"]["phase"] == "tool" for e in events)
    assert events[-1]["type"] == "done"
```

另加测试：工具返回 timeout 结构时出现 `tool/running`、`tool/timeout`，随后仍出现 delta 和 done。

- [ ] **Step 2: 运行失败测试**

Run: `pytest backend/tests/test_chat_stream.py backend/tests/test_ai_jobs.py -q`

Expected: 当前实现没有 progress，且工具按顺序执行，新增断言失败。

- [ ] **Step 3: 实现事件和并行执行**

每轮模型调用前发送 `model/running`；工具调用开始前按原顺序发送 `tool/running`；使用最多 4 个 worker 并行调用 `execute_scoped_tool`，收集后按原索引回填消息，并发送 completed、timeout 或 unavailable progress；最后保留既有 delta/done。

- [ ] **Step 4: 验证取消和持久化**

确认 `RunManager._execute` 持久化所有 progress payload；工具结果返回后检查 `RunControl.cancelled`，取消时不再发起下一轮模型请求。

- [ ] **Step 5: 运行绿色测试并提交**

Run: `pytest backend/tests/test_chat_stream.py backend/tests/test_ai_jobs.py -q`

Expected: 0 failures；提交 `git commit -m "feat: stream AI tool progress"`。

### Task 3: 结构化入口和自动命名

**Files:**
- Modify: `backend/session_store.py`
- Modify: `backend/conversation_routes.py`
- Test: `backend/tests/test_session_store.py`
- Test: `backend/tests/test_conversation_api.py`

**Interfaces:** `SessionStore.auto_name_conversation(principal, conversation_id, question) -> dict`；只在标题为“新对话”时更新。

- [ ] **Step 1: 写失败测试**

```python
def test_first_turn_auto_name_preserves_manual_title(store, principal):
    item = store.create_conversation(principal, "chat", {"type":"news"})
    named = store.auto_name_conversation(principal, item["id"], "  分析 PCB 板块  ")
    assert named["title"] == "金融资讯 · 分析 PCB 板块"
    store.update_conversation_title(principal, item["id"], "手动标题")
    assert store.auto_name_conversation(principal, item["id"], "第二问")["title"] == "手动标题"
```

另加未知旧 source 回退为 `AI 对话 · 问题摘要`，并在 conversation API 测试首次 turn 后读取列表标题。

- [ ] **Step 2: 运行失败测试**

Run: `pytest backend/tests/test_session_store.py backend/tests/test_conversation_api.py -q`

Expected: `auto_name_conversation` 尚不存在，新增测试失败。

- [ ] **Step 3: 实现命名**

增加入口映射：review=每日复盘、news=金融资讯、news-story=资讯事件、watchlist=自选股、index=指数研究、stock/stock-panel=个股研究。问题做空白归一化并截取 60 个 Unicode 字符；`start_turn` 在提交任务前调用，重复请求和手动标题不覆盖。

- [ ] **Step 4: 运行绿色测试并提交**

Run: `pytest backend/tests/test_session_store.py backend/tests/test_conversation_api.py -q`

Expected: 0 failures；提交 `git commit -m "feat: auto-name conversations by entry"`。

### Task 4: 前端会话状态接收 progress 和工具记录

**Files:**
- Modify: `frontend/src/lib/conversationClient.ts`
- Modify: `frontend/src/hooks/useAiChatSession.ts`
- Test: `frontend/tests/conversation-client.test.mjs`
- Test: `frontend/tests/ai-progress.test.mjs`

**Interfaces:** `client.snapshot(id)` 增加 `progress`、`toolUses`；Hook 返回同名状态，并保证每次事件发布新引用。

- [ ] **Step 1: 写失败测试**

```javascript
test('progress events update active tool state', async () => {
  const api = createFakeApi();
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', {clientRequestId:'r1', question:'分析', context:{}});
  api.emit({runId:'run1', seq:1, type:'progress', payload:{phase:'tool', status:'running', tool:'query_market_chart', message:'正在调用板块行情'}});
  assert.equal(client.snapshot('c1').progress.message, '正在调用板块行情');
  assert.equal(client.snapshot('c1').toolUses[0].status, 'running');
  api.emit({runId:'run1', seq:2, type:'progress', payload:{phase:'tool', status:'timeout', tool:'query_market_chart', message:'板块行情超时'}});
  assert.equal(client.snapshot('c1').toolUses[0].status, 'timeout');
});
```

- [ ] **Step 2: 运行失败测试**

Run: `npm test -- --runInBand frontend/tests/conversation-client.test.mjs frontend/tests/ai-progress.test.mjs`

Expected: 当前客户端没有 progress/toolUses 归并，测试失败。

- [ ] **Step 3: 实现状态归并和计时**

为 client state 增加 progress、toolUses；progress 事件按工具名更新记录，delta 切换到模型阶段，terminal 清空 active 状态。Hook 每秒更新 elapsedMs，停止或卸载时清理计时器；新建会话传递结构化 source。

- [ ] **Step 4: 运行绿色测试并提交**

Run: `npm test -- --runInBand frontend/tests/conversation-client.test.mjs frontend/tests/ai-progress.test.mjs`

Expected: 0 failures；提交 `git commit -m "feat: expose AI tool progress in conversation state"`。

### Task 5: 两列 AI 工作区、左侧会话列表和兼容导航

**Files:**
- Create: `frontend/src/components/ai/ConversationRail.tsx`
- Modify: `frontend/src/pages/FinanceAiWorkspace.tsx`
- Modify: `frontend/src/components/ai/AiConversation.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/lib/conversationDestination.ts`
- Delete: `frontend/src/pages/AiHistory.tsx`
- Test: `frontend/tests/finance-ai-workspace.test.mjs`
- Test: `frontend/tests/ai-history.test.mjs`

**Interfaces:** `ConversationRail({activeId,onSelect,onNew})` 使用会话列表 API；`AiConversation` 使用 `session.progress` 在消息底部渲染阶段状态。

- [ ] **Step 1: 写失败测试**

```javascript
test('workspace uses a conversation rail and removes the right sidebar', () => {
  const source = read('src/pages/FinanceAiWorkspace.tsx');
  assert.match(source, /ConversationRail/);
  assert.doesNotMatch(source, /已带入上下文/);
  assert.doesNotMatch(source, /工具调用记录/);
});
```

另加测试要求 `AiConversation.tsx` 包含 `模型分析中`、`正在调用`、`progress`，路由测试要求 `/ai/conversations` 重定向到 `/finance/ai`。

- [ ] **Step 2: 运行失败测试**

Run: `npm test -- --runInBand frontend/tests/finance-ai-workspace.test.mjs frontend/tests/ai-history.test.mjs`

Expected: 当前页面没有 ConversationRail，且包含右侧卡片，测试失败。

- [ ] **Step 3: 实现列表和两列布局**

创建会话列表，支持加载、搜索、新对话、选择和失败重试；在列表项操作菜单中保留已有的重命名、删除、导出能力。桌面布局使用 `15rem + minmax(0,1fr)`，窄屏改为顶部可展开列表。移除工作区右侧 aside 和上下文/工具卡片；消息区用灰色状态行显示模型分析、当前工具、等待秒数、超时继续分析。

- [ ] **Step 4: 调整导航和 URL**

从 Layout NAV 删除 AI 对话记录；router 将旧地址 Navigate 到 `/finance/ai`；`conversationDestination` 编码 source、code、panel、eventId、date，旧 source 回退到 conversationId-only URL；删除独立 AiHistory 页面，但将其操作能力迁移到 ConversationRail。

- [ ] **Step 5: 运行绿色测试并提交**

Run: `npm test -- --runInBand frontend/tests/finance-ai-workspace.test.mjs frontend/tests/ai-history.test.mjs frontend/tests/stock-ai-workspace.test.mjs`

Expected: 0 failures；提交 `git commit -m "feat: move conversation records into AI workspace"`。

### Task 6: 集成、全量验证和 8911 更新

**Files:**
- Create: `backend/tests/test_progress_integration.py`
- Create: `frontend/tests/conversation-rail.test.mjs`
- Modify: `backend/tests/test_conversation_api.py`
- Modify: `frontend/tests/ai-history.test.mjs`

- [ ] **Step 1: 写集成测试**

后端 fake runner 必须生成 `progress → tool → progress → delta → done`，断言 events endpoint 顺序和自动标题；前端断言 source-aware destination 包含 `source=news` 与 `conversationId`。

- [ ] **Step 2: 运行集成测试并修复接口缺口**

Run: `pytest backend/tests/test_progress_integration.py backend/tests/test_conversation_api.py -q` and `npm test -- --runInBand frontend/tests/conversation-rail.test.mjs frontend/tests/ai-history.test.mjs`

Expected: 若失败，只补齐 progress 持久化、命名或 source URL 的接口，不扩大功能范围。

- [ ] **Step 3: 全量验证**

Run: `pytest backend/tests -m "not live" -q --basetemp=C:/Users/Vincent/AppData/Local/Temp/ft-research-pytest`; `npm test`; `npx tsc --noEmit --incremental --tsBuildInfoFile C:/Users/Vincent/AppData/Local/Temp/ft-research-tsconfig.tsbuildinfo`; `npm run build`。

Expected: 后端、前端和 TypeScript 0 failures，Vite 退出码为 0；允许已有 bundle 大小 warning。

- [ ] **Step 4: 运行态验证**

确认 `GET /`、`GET /finance/ai` 和新 JS 资源均为 200；发送新问题时依次看到工具/模型灰色状态、增量回答和结束状态；切换左侧会话后 URL、标题和入口匹配。

- [ ] **Step 5: 检查差异并提交最终变更**

Run: `git diff --check` and `git status --short`。

Expected: 无空白错误；只保留本任务和既有用户改动。最后执行 `git add backend frontend; git commit -m "feat: complete AI conversation workspace"`。
