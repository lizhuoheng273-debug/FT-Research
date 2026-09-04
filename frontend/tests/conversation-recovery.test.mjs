import assert from 'node:assert/strict';
import test from 'node:test';
import { createConversationClient } from '../src/lib/conversationClient.ts';
const tick = () => new Promise(resolve => setImmediate(resolve));
const detail = messages => ({conversation:{id:'c1'},messages,activeRunId:null});
const apiBase = {start:async()=>({runId:'r1',status:'running'}), events:()=>new Promise(()=>{}),cancel:async()=>{}};

for (const action of ['done', 'stop']) {
  test(`${action} clears loading when history fetch is still pending`, async () => {
    let emit;
    let resolveHistory;
    const client = createConversationClient({...apiBase,
      get: () => new Promise(resolve => { resolveHistory = resolve; }),
      events: (_run, _after, sink) => { emit = sink; return new Promise(() => {}); },
    });
    await client.send('c1', {clientRequestId:'q1', question:'test', context:{}});
    client.attach('c1', () => {});
    assert.equal(client.snapshot('c1').historyLoading, true);
    if (action === 'stop') await client.stop('c1');
    else emit({runId:'r1', seq:1, type:'done'});
    resolveHistory({...detail([]), activeRunId:'r1'});
    await tick();
    assert.equal(client.snapshot('c1').historyLoading, false);
    assert.equal(client.snapshot('c1').activeRunId, null);
    client.resetIdentity();
  });
}

test('reopening history refreshes messages added in another tab',async()=>{
  let server=detail([{role:'user',content:'one'},{role:'assistant',content:'answer'}]);
  const client=createConversationClient({...apiBase,get:async()=>server});
  const detach=client.attach('c1',()=>{}); await tick();detach();
  server=detail([...server.messages,{role:'user',content:'two'},{role:'assistant',content:'new answer'}]);
  client.attach('c1',()=>{});await tick();
  assert.equal(client.snapshot('c1').messages.length,4);client.resetIdentity();
});
test('history errors are visible and can be retried',async()=>{
  let failed=true;
  const client=createConversationClient({...apiBase,get:async()=>{if(failed)throw new Error('history unavailable');return detail([]);}});
  client.attach('c1',()=>{});await tick();
  assert.match(client.snapshot('c1').error,/history unavailable/);
  failed=false;client.attach('c1',()=>{});await tick();
  assert.equal(client.snapshot('c1').error,null);client.resetIdentity();
});
test('reopening after network failure replays partial text exactly once',async()=>{
  let round=0;
  const client=createConversationClient({...apiBase,get:async()=>({...detail([]),activeRunId:'r1'}),events:async(runId,after,emit)=>{
    round++;
    if(round===1){emit({runId,seq:1,type:'delta',payload:{text:'ABC'}});throw new Error('offline');}
    if(round===2)throw new Error('offline');
    emit({runId,seq:1,type:'delta',payload:{text:'ABC'}});emit({runId,seq:2,type:'done'});
  }});
  const detach=client.attach('c1',()=>{});await tick();await tick();detach();
  client.attach('c1',()=>{});await tick();await tick();
  assert.deepEqual(client.snapshot('c1').messages.map(m=>m.content),['ABC']);client.resetIdentity();
});

test('normal stop event arriving before cancel reply does not block the next question', async () => {
  let emit;
  let resolveCancel;
  const client = createConversationClient({...apiBase,
    get: async () => detail([]),
    events: (_run, _after, sink) => { emit = sink; return new Promise(() => {}); },
    cancel: () => new Promise(resolve => { resolveCancel = resolve; }),
  });
  await client.send('c1', {clientRequestId:'q1', question:'test', context:{}});
  const stopping = client.stop('c1');
  emit({runId:'r1', seq:1, type:'stopped', payload:{message:'已停止，已保留部分回答'}});
  resolveCancel({ok:true});
  await stopping;
  assert.equal(client.snapshot('c1').error, null);
  assert.equal(client.snapshot('c1').status, 'stopped');
  client.resetIdentity();
});
