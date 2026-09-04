import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {build} from 'esbuild';
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const compiled = await build({
  absWorkingDir: fileURLToPath(new URL('..', import.meta.url)),
  entryPoints: ['src/components/ai/AiConversation.tsx'],
  bundle: true, write: false, platform: 'node', format: 'cjs',
  packages: 'external', jsx: 'automatic', alias: {'@': './src'},
});
const require = createRequire(import.meta.url);

// Exercise the actual component's layout effects with stable refs and React's
// Object.is dependency semantics; Node's test runner has no browser DOM.
function mount() {
  const refs = [], dependencies = [];
  let refIndex = 0, effectIndex = 0, pending = [];
  const react = {...React,
    useRef(value) { return refs[refIndex++] ??= {current: value}; },
    useLayoutEffect(effect, deps) {
      const index = effectIndex++;
      if (!dependencies[index] || deps.some((value, i) => !Object.is(value, dependencies[index][i]))) pending.push(effect);
      dependencies[index] = deps;
    },
  };
  const mod = {exports: {}};
  new Function('require', 'module', 'exports', compiled.outputFiles[0].text)(
    name => name === 'react' ? react : name === 'react-markdown' ? ReactMarkdown : name === 'remark-gfm' ? remarkGfm : require(name), mod, mod.exports);
  const scroll = {scrollTop: 0, scrollHeight: 800, clientHeight: 400};
  const session = {conversationId: 'one', messages: [{role: 'assistant', content: 'PARTIAL', status: 'streaming'}], input: '', setInput() {}, loading: true, error: null, send() {}, stop() {}};
  function render(changes = {}) {
    Object.assign(session, changes);
    refIndex = effectIndex = 0; pending = [];
    const tree = mod.exports.AiConversation({session});
    refs[0].current = scroll;
    pending.forEach(effect => effect());
    return tree.props.children[0];
  }
  render();
  return {scroll, session, render};
}

test('terminal status reveals the partial-answer explanation while following output', () => {
  const view = mount();
  view.scroll.scrollHeight = 900;
  view.render({messages: [{...view.session.messages[0], status: 'failed'}]});
  assert.equal(view.scroll.scrollTop, 900);
});

test('a new error reveals retry controls without requiring another text delta', () => {
  const view = mount();
  view.scroll.scrollHeight = 920;
  view.render({error: 'Connection failed', retry() {}});
  assert.equal(view.scroll.scrollTop, 920);
});

test('equivalent snapshots and loading toggles do not jump the scroll position', () => {
  const view = mount();
  view.scroll.scrollTop = 390;
  view.render({messages: view.session.messages.map(message => ({...message})), loading: false});
  assert.equal(view.scroll.scrollTop, 390);
});

test('terminal errors do not pull readers away from older content', () => {
  const view = mount();
  view.scroll.scrollTop = 0;
  view.render().props.onScroll({currentTarget: view.scroll});
  view.scroll.scrollHeight = 920;
  view.render({error: 'Connection failed', messages: [{...view.session.messages[0], status: 'failed'}]});
  assert.equal(view.scroll.scrollTop, 0);
});

test('a new inline tool status stays visible while following output', () => {
  const view = mount();
  view.scroll.scrollHeight = 940;
  view.render({progress: {phase: 'tool', status: 'running', tool: 'query_news', message: '正在查新闻'}});
  assert.equal(view.scroll.scrollTop, 940);
});

test('elapsed-time ticks do not cause repeated scroll jumps', () => {
  const view = mount();
  view.render({progress: {phase: 'reasoning', status: 'running', message: '模型正在推理…', elapsedMs: 1000}});
  view.scroll.scrollTop = 390;
  view.render({progress: {phase: 'reasoning', status: 'running', message: '模型正在推理…', elapsedMs: 2000}});
  assert.equal(view.scroll.scrollTop, 390);
});
