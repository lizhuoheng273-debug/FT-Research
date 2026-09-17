import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = resolve(frontendRoot, "src");
const disclaimerPath = resolve(sourceRoot, "components/ui/Disclaimer.tsx");
const disclaimerSource = readFileSync(disclaimerPath, "utf8");
const debateSource = readFileSync(resolve(sourceRoot, "pages/Debate.tsx"), "utf8");

const compiled = ts.transpileModule(disclaimerSource, {
  compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.CommonJS,
  },
}).outputText;
const disclaimerModule = { exports: {} };
new Function("require", "module", "exports", compiled)(require, disclaimerModule, disclaimerModule.exports);
const { Disclaimer } = disclaimerModule.exports;

function renderDisclaimer(props = {}) {
  return renderToStaticMarkup(React.createElement(Disclaimer, props));
}

function withoutInfoIcon(markup) {
  return markup.replace(/<svg\b[\s\S]*?<\/svg>/, "");
}

function findTsxFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return findTsxFiles(path);
    return entry.isFile() && entry.name.endsWith(".tsx") ? [path] : [];
  });
}

test("full and compact variants preserve their existing rendered output", () => {
  const expectedFull = '<div class="mt-8 flex items-start gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground"><span>FT-Research 是一个中立的信息整理与 AI 接入工具。榜单（连板股 / 成交额等）均为<b class="text-foreground">客观公开数据</b>；本产品<b class="text-foreground">只呈现事实，不推荐个股、不预测涨跌、不给买卖时机、不构成投资建议</b>； 看板内所有分析方向均由你自己配置的 AI 给出，与本产品无关。请自行核实并独立决策，风险自担。</span></div>';
  const expectedCompact = '<p class="text-[11px] leading-relaxed text-muted-foreground/70">FT-Research 只客观呈现公开数据与榜单，不推荐个股、不预测涨跌、不构成投资建议。</p>';

  assert.equal(withoutInfoIcon(renderDisclaimer()), expectedFull);
  assert.equal(withoutInfoIcon(renderDisclaimer({ variant: "full" })), expectedFull);
  assert.equal(renderDisclaimer({ compact: true }), expectedCompact);
  assert.equal(renderDisclaimer({ variant: "compact" }), expectedCompact);
  assert.equal(withoutInfoIcon(renderDisclaimer({ compact: true, variant: "full" })), expectedFull);
});

test("debate variant keeps the bordered notice and ends at the concise bold disclaimer", () => {
  const rendered = renderDisclaimer({ variant: "debate" });
  const expected = '<div class="mt-8 flex items-start gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground"><span>FT-Research 是一个中立的信息整理与 AI 接入工具。榜单（连板股 / 成交额等）均为<b class="text-foreground">客观公开数据</b>；本产品<b class="text-foreground">不构成投资建议</b>。</span></div>';

  assert.equal(withoutInfoIcon(rendered), expected);
  assert.match(rendered, /<b class="text-foreground">不构成投资建议<\/b>。<\/span><\/div>$/);
});

test("Debate alone opts into the debate-specific disclaimer variant", () => {
  const optedInFiles = findTsxFiles(sourceRoot).flatMap((path) => {
    const source = readFileSync(path, "utf8");
    return [...source.matchAll(/<Disclaimer\b([^>]*)\/?\s*>/g)]
      .filter((match) => /\bvariant\s*=/.test(match[1]))
      .map(() => relative(sourceRoot, path).replaceAll("\\", "/"));
  });

  assert.match(debateSource, /<Disclaimer\s+variant="debate"\s*\/>/);
  assert.deepEqual(optedInFiles, ["pages/Debate.tsx"]);
});
