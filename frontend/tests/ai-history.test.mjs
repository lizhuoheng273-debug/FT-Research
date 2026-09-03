import assert from 'node:assert/strict';
import test from 'node:test';
import { conversationDestination } from '../src/lib/conversationDestination.ts';

test('conversation destinations preserve source context', () => {
  assert.equal(conversationDestination({ id: 'abc', kind: 'debate', source: { type: 'debate' } }), '/finance/debate?conversationId=abc');
  assert.match(conversationDestination({ id: 'xyz', kind: 'chat', source: { type: 'stock', code: '600183' } }), /conversationId=xyz/);
});
