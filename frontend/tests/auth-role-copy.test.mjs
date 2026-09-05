import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const gate = await readFile(new URL("../src/components/auth/AuthGate.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/components/layout/Layout.tsx", import.meta.url), "utf8");

test("authentication UI consistently names the roles 管理员 and 访客", () => {
  const visibleCopy = `${gate}\n${layout}`;
  assert.match(visibleCopy, /管理员登录/);
  assert.match(visibleCopy, /访客体验/);
  assert.doesNotMatch(visibleCopy, /主人|游客/);
});
