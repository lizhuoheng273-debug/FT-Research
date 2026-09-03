import assert from 'node:assert/strict';
import test from 'node:test';
import { createConversationClient } from '../src/lib/conversationClient.ts';

function createFakeApi() {
  let sink;
  return {
    startCount: 0,
    cancelCount: 0,
    async get(id) {
      return { conversation: { id, kind: 'chat', title: '测试', source: { type: 'review' }, status: 'idle' }, messages: [], activeRunId: null };
    },
    async start() { this.startCount++; return { runId: 'run1', status: 'running' }; },
    events(runId, after, onEvent, signal) {
      sink = onEvent;
      return new Promise(resolve => signal.addEventListener('abort', () => resolve(), { once: true }));
    },
    async cancel() { this.cancelCount++; },
    emit(event) { assert.ok(sink, 'subscription started'); sink(event); },
  };
}

test('detach leaves background stream alive and duplicate sequence is ignored', async () => {
  const api = createFakeApi();
  const client = createConversationClient(api);
  const detach = client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  api.emit({ runId: 'run1', seq: 1, type: 'delta', payload: { text: '第一段' } });
  detach();
  api.emit({ runId: 'run1', seq: 1, type: 'delta', payload: { text: '重复' } });
  api.emit({ runId: 'run1', seq: 2, type: 'delta', payload: { text: '第二段' } });
  assert.equal(client.snapshot('c1').messages.at(-1).content, '第一段第二段');
  assert.equal(api.cancelCount, 0);
  assert.equal(api.startCount, 1);
  await client.stop('c1');
  assert.equal(api.cancelCount, 1);
  client.resetIdentity();
});
