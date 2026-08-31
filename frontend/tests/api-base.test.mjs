import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");
const llm = await readFile(new URL("../src/lib/llm.ts", import.meta.url), "utf8");

test("API client supports a hosted frontend base URL while preserving the /api prefix", () => {
  assert.match(api, /import\.meta\.env\.VITE_API_URL/);
  assert.match(api, /replace\(/);
  assert.match(api, /normalized\.startsWith\("\/api\/"\)/);
  assert.match(api, /return `\$\{API_BASE\}\$\{apiPath\}`/);
});

test("pages with direct requests use the shared API URL helper", () => {
  assert.match(daily, /import \{ apiUrl, authHeaders \}/);
  assert.match(llm, /import \{ ApiError, apiUrl, authHeaders \}/);
  assert.doesNotMatch(daily, /fetch\((?:`|\")\/api/);
  assert.doesNotMatch(llm, /fetch\((?:`|\")\/api/);
});
