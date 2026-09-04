import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const SRC = new URL("../src/components/ui/AskAiButton.tsx", import.meta.url);
const SESSION = new URL("../src/hooks/useAiChatSession.ts", import.meta.url);
const buttonSource = await readFile(SRC, "utf8");
const sessionSource = await readFile(SESSION, "utf8");
const source = `${buttonSource}\n${sessionSource}`;

// 这些断言锁的是 #19 的修复：对话此前只存在组件 useState 里，
// 切页面/刷新就全丢。用户反馈「关闭 AI 就找不回之前的对话」，
// 而每轮对话都花了他自己的 API 额度。

test("Ask AI persists the conversation through the safe storage helper", () => {
  assert.match(source, /from "@\/lib\/storage"/);
  assert.match(source, /storageGet/);
  assert.match(source, /storageSet/);
  // 必须走 storage.ts 的封装：localStorage 在隐私模式/配额写满时会直接抛异常，
  // 裸调会让整个面板崩掉。
  assert.doesNotMatch(source, /(?<!\/\/.*)\blocalStorage\.(get|set|remove)Item\b/);
});

test("conversations are keyed per route, not shared across pages", () => {
  assert.match(buttonSource, /useLocation/);
  assert.match(buttonSource, /conversationKey:\s*pathname \+ \(scopeKey/);
  assert.match(sessionSource, /conversations\.get\(conversationKey\)/);
});

test("persisted history is capped so localStorage cannot be blown out", () => {
  assert.match(source, /MAX_PERSISTED_MSGS\s*=\s*\d+/);
  assert.match(source, /slice\(-MAX_PERSISTED_MSGS\)/);
});

test("malformed stored data is ignored instead of crashing the panel", () => {
  // 存量数据可能来自旧版本或被手工改坏；JSON.parse 必须包 try/catch，
  // 且要校验形状，否则脏数据会让页面白屏。
  assert.match(source, /try\s*\{[\s\S]*JSON\.parse[\s\S]*\}\s*catch/);
  assert.match(source, /Array\.isArray\(parsed\)/);
});

test("there is a way to clear a stored conversation", () => {
  assert.match(source, /storageRemove/);
  assert.match(source, /clearChat/);
});

test("emptying the conversation removes the key rather than storing an empty shell", () => {
  assert.match(source, /if \(!msgs\.length\)\s*\{\s*\n?\s*storageRemove\(key\)/);
});

test("server conversation snapshots and async writes are scoped to the current route", () => {
  assert.match(sessionSource, /useState\(\(\) => client\.snapshot\(id\)\)/);
  assert.match(sessionSource, /epoch\.current === version && scopeRef\.current === scope/);
  assert.match(sessionSource, /if \(!current\(\)\) return;/);
});

test("switching keys detaches the view while leaving the background run alive", () => {
  assert.match(sessionSource, /return \(\) => \{ active = false; detach\(\); \}/);
  assert.match(sessionSource, /if \(active\) setState\(snapshot\)/);
  assert.equal((sessionSource.match(/client\.attach\(/g) || []).length, 1);
});

test("callers can scope a conversation below the route level", () => {
  // 个股页不换路由就能换标的：只按 pathname 分 key 会让 A 股票的历史
  // 作为 history 发给正在问 B 股票的模型。
  assert.match(buttonSource, /scopeKey\?: string/);
  assert.match(buttonSource, /pathname \+ \(scopeKey \? `#\$\{scopeKey\}` : ""\)/);
});

test("the stock page actually passes a per-symbol scope", async () => {
  const page = await readFile(
    new URL("../src/pages/StockData.tsx", import.meta.url), "utf8",
  );
  assert.match(page, /<AskAiButton[\s\S]*?scopeKey=/);
  // 必须用已解析结果的代码，不能用一边打字一边变的输入框 state
  assert.match(page, /scopeKey=\{gstock \? `g:\$\{gstock\.code\}` : val\?\.code\}/);
});

test("aborted-request cleanup is gated by request identity", () => {
  // 换页会中止旧请求，其 catch 可能在用户已于新页面发起提问后才落地。
  // 不校验就会删掉新请求的空气泡，后续 chunk 无处可写、对话残缺。
  const block = source.match(/\} catch \(e\) \{[\s\S]*?\} finally \{/);
  assert.ok(block, "未找到 catch 块");
  // 不能简单用 abortRef.current === ac：close() 会把它置 null，
  // 那种情况下空气泡**仍要清理**，否则会被持久化成一条空回复。
  assert.match(block[0], /const superseded = abortRef\.current !== null && abortRef\.current !== ac;/);
  assert.match(block[0], /if \(!superseded && chatKeyRef\.current === startedKey\)/);
});

test("streaming replies are partial from creation and only cleared on success", () => {
  // 每个 delta 都会触发落盘，所以「中止时再补标记」来不及：
  // 流到一半换页/换标的，存下来的就是一条被当作完整回答的残句，
  // 回到该对话时还会以完整发言的身份进入下一轮 history。
  assert.match(source, /partial\?: boolean/);
  assert.match(source, /role: "assistant", content: "", tools: \[\], partial: true/); // 创建即标
  assert.match(source, /const \{ partial: _drop, \.\.\.rest \} = message;/);        // 成功才摘
  assert.match(source, /const keep = completeTurns\(msgs\)/);                        // 不落盘
  assert.match(source, /boundedCompleteTurns\(msgs, MAX_REQUEST_MSGS\)\.map/);       // 不进 history，且限制成本
});

test("an interrupted turn drops the question too, not just the half answer", () => {
  // 只丢 assistant 会留下孤立的提问，模型在 history 里看到连续两条 user 发言，
  // 会把那个被放弃的问题当成还在等回答，去答错的题。
  assert.match(source, /function completeTurns/);
  assert.match(source, /if \(out\.length && out\[out\.length - 1\]\.role === "user"\) out\.pop\(\);/);
});

test("a request that fails before any content removes its question too", () => {
  // 对称情况：一个字都没收到时删空气泡，若不连提问一起删，
  // 界面和存储里都会留下孤立的 user turn，下一轮就是连续两条 user。
  const block = source.match(/\} catch \(e\) \{[\s\S]*?\} finally \{/);
  assert.ok(block, "未找到 catch 块");
  assert.match(block[0], /const dropUser = current\[current\.length - 2\]\?\.role === "user";/);
  assert.match(block[0], /current\.slice\(0, dropUser \? -2 : -1\)/);
});
