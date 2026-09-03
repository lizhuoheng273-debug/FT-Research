import assert from 'node:assert/strict';
import test from 'node:test';
import { createConversationClient } from '../src/lib/conversationClient.ts';

function createFakeApi() {
  let sink;
  return {
    async get(id) { return { conversation: { id, title: '测试', source: {} }, messages: [], activeRunId: null }; },
    async start() { return { runId: 'run1', status: 'running' }; },
    events(_runId, _after, onEvent, signal) {
      sink = onEvent;
      return new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
    },
    async cancel() {},
    emit(event) { sink(event); },
  };
}

test('progress events update active tool state', async () => {
  const api = createFakeApi();
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '分析', context: {} });

  api.emit({ runId: 'run1', seq: 1, type: 'progress', payload: { phase: 'tool', status: 'running', tool: 'query_market_chart', message: '正在调用板块行情', elapsedMs: 0 } });
  assert.equal(client.snapshot('c1').progress.message, '正在调用板块行情');
  assert.equal(client.snapshot('c1').toolUses[0].status, 'running');
  api.emit({ runId: 'run1', seq: 2, type: 'progress', payload: { phase: 'tool', status: 'timeout', tool: 'query_market_chart', message: '板块行情超时', elapsedMs: 20000 } });
  assert.equal(client.snapshot('c1').toolUses[0].status, 'timeout');
});
