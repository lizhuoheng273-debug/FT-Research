import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

test("the existing markdown stack renders common AI response formatting", () => {
  const markdown = "## Risk\n\n- **High volatility**\n\n> Verify independently";
  const html = renderToStaticMarkup(
    React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, markdown),
  );

  assert.match(html, /<h2>Risk<\/h2>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<strong>High volatility<\/strong>/);
  assert.match(html, /<blockquote>/);
});

test("Ask AI renders Markdown and a visible working status without a premature save button", async () => {
  const compiled = await build({
    absWorkingDir: fileURLToPath(new URL('..', import.meta.url)).replaceAll('\\', '/'),
    entryPoints: ['src/components/ai/AiConversation.tsx'],
    tsconfigRaw: { compilerOptions: { jsx: 'react-jsx' } },
    bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic',
    alias: { '@': './src' },
  });
  const module = { exports: {} };
  const require = createRequire(import.meta.url);
  const load = name => name === 'react-markdown' ? ReactMarkdown : name === 'remark-gfm' ? remarkGfm : require(name);
  new Function('require', 'module', 'exports', compiled.outputFiles[0].text)(load, module, module.exports);
  const html = renderToStaticMarkup(React.createElement(module.exports.AiConversation, { mode: 'workspace', session: {
    messages: [{ role: 'assistant', content: '## 分析\n\n**正文**', status: 'partial' }],
    input: '', setInput() {}, loading: true, error: null,
    progress: { phase: 'tool', status: 'running', message: '正在查询行情', elapsedMs: 2000 },
    send() {}, stop() {}, toolUses: [],
  } }));
  assert.match(html, /<h2>分析<\/h2>/);
  assert.match(html, /<strong>正文<\/strong>/);
  assert.match(html, /role="status"/);
  assert.match(html, /正在查询行情/);
  assert.match(html, /停止生成/);
  assert.doesNotMatch(html, /存入沉淀/);
});
