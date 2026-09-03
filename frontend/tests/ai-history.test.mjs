import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { conversationDestination } from '../src/lib/conversationDestination.ts';

const layout = fs.readFileSync(new URL('../src/components/layout/Layout.tsx', import.meta.url), 'utf8');
const router = fs.readFileSync(new URL('../src/router.tsx', import.meta.url), 'utf8');

test('conversation destinations preserve source context', () => {
  assert.equal(conversationDestination({ id: 'abc', kind: 'debate', source: { type: 'debate' } }), '/finance/debate?conversationId=abc');
  assert.match(conversationDestination({ id: 'xyz', kind: 'chat', source: { type: 'news' } }), /conversationId=xyz/);
  assert.match(conversationDestination({ id: 'xyz', kind: 'chat', source: { type: 'news' } }), /source=news/);
  const stockDestination = conversationDestination({ id: 'stock', kind: 'chat', source: { type: 'stock', code: '600183' } });
  assert.match(stockDestination, /\/finance\/stocks\/600183\/ai\?/);
  assert.match(stockDestination, /source=stock/);
  assert.match(stockDestination, /code=600183/);
});

test('AI history is moved into the workspace and old route redirects', () => {
  assert.doesNotMatch(layout, /label: "AI 对话记录"/);
  assert.match(router, /path: ["']\/ai\/conversations["'][\s\S]*Navigate to="\/finance\/ai"/);
});
