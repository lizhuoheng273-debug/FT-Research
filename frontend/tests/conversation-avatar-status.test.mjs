import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const compiled = await build({absWorkingDir:fileURLToPath(new URL('..',import.meta.url)),entryPoints:['src/components/ai/AiConversation.tsx'],bundle:true,write:false,platform:'node',format:'cjs',packages:'external',jsx:'automatic',alias:{'@':'./src'}});
const mod={exports:{}}, require=createRequire(import.meta.url);
new Function('require','module','exports',compiled.outputFiles[0].text)(name=>name==='react-markdown'?ReactMarkdown:name==='remark-gfm'?remarkGfm:require(name),mod,mod.exports);
function render(overrides={},mode='workspace') {
  return renderToStaticMarkup(React.createElement(mod.exports.AiConversation,{mode,session:{
    messages:[{role:'user',content:'QUESTION'},{role:'assistant',content:'ANSWER',status:'partial'}],
    loading:true, input:'', setInput(){}, send(){}, stop(){}, error:null, toolUses:[],
    progress:{phase:'reasoning',status:'running',message:'模型正在推理…',elapsedMs:7000},...overrides,
  }}));
}
function statusHeader(html) { return (html.match(/<header\b[^>]*>[\s\S]*?<\/header>/g)||[]).find(header=>header.includes('role="status"')) || ''; }

test('reasoning slider exposes the selected mode and remains usable during generation',()=>{
  const html=render({reasoningEffort:'high',setReasoningEffort(){}});
  const selector=html.match(/<input[^>]*type="range"[^>]*>/)?.[0] || '';
  assert.match(selector,/aria-label="推理强度"/);
  assert.match(selector,/aria-valuetext="均衡"/);
  assert.match(selector,/min="0"/); assert.match(selector,/max="2"/); assert.match(selector,/step="1"/);
  assert.doesNotMatch(selector,/ disabled=""/);
  assert.match(html,/下一条提问生效/);
});

for (const [effort,label] of [['low','快速'],['high','均衡'],['max','深入']]) test(`${effort} is announced by the slider`,()=>{
  assert.match(render({reasoningEffort:effort,setReasoningEffort(){}}),new RegExp(`aria-valuetext="${label}"`));
});
test('reasoning slider is locked only while a request is being submitted',()=>{
  assert.match(render({reasoningLocked:true,setReasoningEffort(){}}),/<input[^>]*type="range"[^>]* disabled=""/);
});

for (const mode of ['workspace','compact']) test(`${mode} shows progress beside the assistant avatar, before its answer`,()=>{
  const html=render({},mode), header=statusHeader(html);
  assert.match(header,/aria-label="AI 头像"/);
  assert.match(header,/模型正在推理/);
  assert.match(header,/7 秒/);
  assert.equal((html.match(/role="status"/g)||[]).length,1);
  assert.ok(html.indexOf(header)<html.indexOf('ANSWER'));
});
test('all running tools are named even when the latest progress names only one',()=>{
  const html=render({progress:{phase:'tool',status:'running',tool:'query_news',message:'LATEST'},toolUses:[
    {name:'query_quote',status:'running'}, {name:'query_news',status:'running'}, {name:'query_reports',status:'completed'},
  ]});
  const header=statusHeader(html);
  assert.match(header,/正在调用/); assert.match(header,/查行情/); assert.match(header,/查新闻/);
  assert.doesNotMatch(header,/查研报/);
});
test('an unfamiliar tool remains identifiable with only a progress event',()=>{
  assert.match(statusHeader(render({progress:{phase:'tool',status:'running',tool:'custom_lookup',message:'执行中'}})),/custom_lookup/);
});
test('financial tools display readable names instead of internal identifiers',()=>{
  assert.match(statusHeader(render({progress:{phase:'tool',status:'running',message:'执行中'},toolUses:[{name:'query_fund_flow',status:'running'}]})),/查资金流向/);
});
test('output progress supersedes stale running tools from legacy events',()=>{
  const header=statusHeader(render({progress:{phase:'output',status:'running',message:'模型输出中…'},toolUses:[{name:'query_quote',status:'running'}]}));
  assert.match(header,/模型输出中/); assert.doesNotMatch(header,/正在调用/);
});
test('submission gets its own avatar without attaching activity to a previous answer',()=>{
  const html=render({messages:[{role:'assistant',content:'OLD ANSWER',status:'complete'}],progress:{phase:'submit',status:'running',message:'正在提交请求…'}});
  const header=statusHeader(html);
  assert.match(header,/正在提交请求/);
  assert.ok(html.indexOf(header)>html.indexOf('OLD ANSWER'));
});
for (const status of ['complete','stopped','failed']) test(`${status} ends avatar activity even with stale tool progress`,()=>{
  const html=render({loading:false,messages:[{role:'assistant',content:'ANSWER',status}],toolUses:[{name:'query_quote',status:'running'}]});
  assert.match(html,/aria-label="AI 头像"/);
  assert.doesNotMatch(html,/role="status"/); assert.doesNotMatch(html,/animate-spin/);
});
