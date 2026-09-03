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

test('stream updates publish fresh message snapshots for reactive consumers', async () => {
  const api = createFakeApi();
  const renders = [];
  const client = createConversationClient(api);
  client.attach('c1', state => renders.push(state.messages));
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });

  const beforeDelta = renders.at(-1);
  api.emit({ runId: 'run1', seq: 1, type: 'delta', payload: { text: '第一段' } });
  const afterFirstDelta = renders.at(-1);
  api.emit({ runId: 'run1', seq: 2, type: 'delta', payload: { text: '第二段' } });
  const afterSecondDelta = renders.at(-1);

  assert.notEqual(afterFirstDelta, beforeDelta);
  assert.notEqual(afterSecondDelta, afterFirstDelta);
  assert.equal(afterSecondDelta.at(-1).content, '第一段第二段');

  api.emit({ runId: 'run1', seq: 3, type: 'done', payload: {} });
  assert.notEqual(renders.at(-1), afterSecondDelta);
  assert.equal(client.snapshot('c1').activeRunId, null);
});

test('stream failures stop the pending assistant message', async () => {
  const api = createFakeApi();
  api.events = async () => { throw new Error('events unavailable'); };
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  await new Promise(resolve => setTimeout(resolve, 0));
  const snapshot = client.snapshot('c1');
  assert.equal(snapshot.status, 'error');
  assert.equal(snapshot.activeRunId, null);
  assert.equal(snapshot.messages.at(-1).status, 'error');
});

test('an EOF without a terminal event stops the pending assistant message', async () => {
  const api = createFakeApi();
  api.events = async () => {};
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  await new Promise(resolve => setTimeout(resolve, 0));
  const snapshot = client.snapshot('c1');
  assert.equal(snapshot.status, 'error');
  assert.equal(snapshot.activeRunId, null);
  assert.equal(snapshot.messages.at(-1).status, 'error');
});

test('stopping a run cannot clear a newer run', async () => {
  const api = createFakeApi();
  let releaseCancel;
  let runNumber = 0;
  api.start = async () => ({ runId: `run${++runNumber}`, status: 'running' });
  api.cancel = () => new Promise(resolve => { api.cancelCount++; releaseCancel = resolve; });
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '第一问', context: {} });
  const stopping = client.stop('c1');
  await new Promise(resolve => setTimeout(resolve, 0));
  await client.send('c1', { clientRequestId: 'r2', question: '第二问', context: {} });
  releaseCancel();
  await stopping;
  const snapshot = client.snapshot('c1');
  assert.equal(snapshot.activeRunId, 'run2');
  assert.equal(snapshot.messages[1].status, 'stopped');
  assert.equal(snapshot.messages.at(-1).status, 'partial');
});

test('stopping while start is pending cancels the run after it is created', async () => {
  const api = createFakeApi();
  let releaseStart;
  api.start = () => new Promise(resolve => { releaseStart = resolve; });
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  const sending = client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  await new Promise(resolve => setTimeout(resolve, 0));
  await client.stop('c1');
  releaseStart({ runId: 'run1', status: 'running' });
  await sending;
  await new Promise(resolve => setTimeout(resolve, 0));
  const snapshot = client.snapshot('c1');
  assert.equal(snapshot.activeRunId, null);
  assert.equal(snapshot.status, 'stopped');
  assert.equal(snapshot.messages.at(-1).status, 'stopped');
  assert.equal(api.cancelCount, 1);
});

test('attach resumes an active run from the server detail', async () => {
  const api = createFakeApi();
  let subscribed = false;
  let resumeSink;
  api.get = async id => ({ conversation: { id, kind: 'chat', title: '测试', source: {}, status: 'running' }, messages: [], activeRunId: 'run1' });
  api.events = (_runId, _after, onEvent, signal) => {
    subscribed = true;
    resumeSink = onEvent;
    return new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
  };
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(subscribed, true);
  assert.equal(client.snapshot('c1').activeRunId, 'run1');
  resumeSink({ runId: 'run1', seq: 1, type: 'delta', payload: { text: '恢复回答' } });
  assert.equal(client.snapshot('c1').messages.at(-1).content, '恢复回答');
});

test('attach can resubscribe after a previous stream ended', async () => {
  const api = createFakeApi();
  let detailCount = 0;
  let subscriptions = 0;
  api.get = async id => ({ conversation: { id, kind: 'chat', title: '测试', source: {}, status: 'running' }, messages: [], activeRunId: detailCount++ === 0 ? null : 'run2' });
  api.events = async (runId, _after, onEvent) => {
    subscriptions++;
    onEvent({ runId, seq: 1, type: 'done', payload: {} });
  };
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '第一次', context: {} });
  await new Promise(resolve => setTimeout(resolve, 0));
  client.attach('c1', () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(subscriptions, 2);
});

test('a transient stream EOF retries from the last sequence', async () => {
  const api = createFakeApi();
  let subscriptions = 0;
  api.events = async (_runId, _after, onEvent) => {
    subscriptions++;
    if (subscriptions === 2) onEvent({ runId: 'run1', seq: 1, type: 'done', payload: {} });
  };
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(subscriptions, 2);
  assert.equal(client.snapshot('c1').status, 'completed');
});

test('a stale attach response cannot resurrect a completed run', async () => {
  const api = createFakeApi();
  let releaseDetail;
  api.get = () => new Promise(resolve => { releaseDetail = resolve; });
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '复盘', context: {} });
  api.emit({ runId: 'run1', seq: 1, type: 'done', payload: {} });
  releaseDetail({ conversation: { id: 'c1', kind: 'chat', title: '测试', source: {}, status: 'running' }, messages: [], activeRunId: 'run1' });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(client.snapshot('c1').activeRunId, null);
});

test('attaching a different active run resets its event cursor', async () => {
  const api = createFakeApi();
  let afterValue;
  let eventSink;
  api.get = async id => ({ conversation: { id, kind: 'chat', title: '测试', source: {}, status: 'running' }, messages: [], activeRunId: null });
  api.events = (runId, after, onEvent) => {
    afterValue = after;
    eventSink = onEvent;
    return Promise.resolve();
  };
  const client = createConversationClient(api);
  client.attach('c1', () => {});
  await client.send('c1', { clientRequestId: 'r1', question: '第一问', context: {} });
  eventSink({ runId: 'run1', seq: 1, type: 'delta', payload: { text: '一' } });
  eventSink({ runId: 'run1', seq: 2, type: 'done', payload: {} });
  api.get = async id => ({ conversation: { id, kind: 'chat', title: '测试', source: {}, status: 'running' }, messages: [], activeRunId: 'run2' });
  client.attach('c1', () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(afterValue, 0);
  assert.equal(client.snapshot('c1').lastSeq, 0);
});
