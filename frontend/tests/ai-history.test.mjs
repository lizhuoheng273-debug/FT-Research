import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { conversationDestination } from '../src/lib/conversationDestination.ts';

const layout = fs.readFileSync(new URL('../src/components/layout/Layout.tsx', import.meta.url), 'utf8');
const history = fs.readFileSync(new URL('../src/pages/AiHistory.tsx', import.meta.url), 'utf8');

test('conversation destinations preserve source context', () => {
  assert.equal(conversationDestination({ id: 'abc', kind: 'debate', source: { type: 'debate' } }), '/finance/debate?conversationId=abc');
  assert.match(conversationDestination({ id: 'xyz', kind: 'chat', source: { type: 'stock', code: '600183' } }), /conversationId=xyz/);
});

test('AI history is labeled as conversation records', () => {
  assert.match(layout, /label: "AI 对话记录"/);
  assert.match(history, /<h1[^>]*>AI 对话记录<\/h1>/);
});
