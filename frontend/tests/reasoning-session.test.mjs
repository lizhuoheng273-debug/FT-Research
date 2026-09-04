import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {build} from 'esbuild';
import React from 'react';

const compiled=await build({absWorkingDir:fileURLToPath(new URL('..',import.meta.url)),entryPoints:['src/hooks/useAiChatSession.ts'],bundle:true,write:false,platform:'node',format:'cjs',packages:'external',alias:{'@':'./src'},plugins:[{name:'api-boundary',setup(builder){builder.onResolve({filter:/conversationApi$/},()=>({path:'test-api',external:true}));}}]});
const require=createRequire(import.meta.url);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

// A minimal commit/effect scheduler executes the actual hook and conversation
// client; only React's host runtime and the HTTP boundary are replaced.
function mount(props,storage=new Map()) {
  const oldStorage=globalThis.localStorage;
  const oldWindow=globalThis.window;
  globalThis.window={setInterval,clearInterval,dispatchEvent(){}};
  globalThis.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  const slots=[],cleanups=[];
  let index=0,dirty=true,pending=[],result;
  const react={...React,
    useState(initial){const i=index++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],value=>{const next=typeof value==='function'?value(slots[i]):value;if(!Object.is(next,slots[i])){slots[i]=next;dirty=true;}}];},
    useRef(value){const i=index++;return slots[i]??={current:value};},
    useEffect(effect,deps){const i=index++;if(!slots[i]||deps.some((value,n)=>!Object.is(value,slots[i][n])))pending.push(()=>{cleanups[i]?.();cleanups[i]=effect();});slots[i]=deps;},
  };
  react.useLayoutEffect=react.useEffect;
  const requests=[],sinks=new Map();
  const api={
    create:async()=>({id:'created'}),
    get:async id=>({conversation:{id},messages:[],activeRunId:null}),
    start:async(id,input)=>{requests.push({id,input});return {runId:'run-'+requests.length,status:'running'};},
    events:async(id,after,sink)=>{sinks.set(id,sink);await new Promise(()=>{});},
    cancel:async()=>({ok:true}),
  };
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(name=>name==='react'?react:name==='test-api'?{createConversationApi:()=>api}:require(name),mod,mod.exports);
  function render(nextProps){if(nextProps){props={...props,...nextProps};dirty=true;}let count=0;while(dirty){assert.ok(count++<30,'hook failed to settle');dirty=false;index=0;pending=[];result=mod.exports.useAiChatSession(props);pending.forEach(effect=>effect());}return result;}
  render();
  return {render,requests,sinks,storage,close(){cleanups.forEach(cleanup=>cleanup?.());mod.exports.resetConversationIdentity();globalThis.localStorage=oldStorage;globalThis.window=oldWindow;}};
}

test('AI drafts default to balanced; existing and financial conversations retain deep',()=>{
  for(const [props,want] of [[{source:{type:'ai-news'}},'high'],[{source:{type:'news'}},'max'],[{source:{type:'ai-news'},conversationId:'old'},'max']]){
    const view=mount({conversationKey:'key',context:'context',...props});
    try{assert.equal(view.render().reasoningEffort,want);}finally{view.close();}
  }
});

test('choices stay with their conversation and survive remount',async()=>{
  const props={conversationKey:'a',conversationId:'one',context:'context',source:{type:'news'}};
  const view=mount(props);
  let saved;
  try{
    await tick();view.render().setReasoningEffort('low');assert.equal(view.render().reasoningEffort,'low');
    view.render({conversationId:'two'});assert.equal(view.render().reasoningEffort,'max');
    view.render().setReasoningEffort('high');view.render();
    view.render({conversationId:'one'});assert.equal(view.render().reasoningEffort,'low');
    saved=view.storage;
  }finally{view.close();}
  const restored=mount(props,saved);
  try{assert.equal(restored.render().reasoningEffort,'low');}finally{restored.close();}
});

test('changing effort during a run changes only the next request',async()=>{
  const view=mount({conversationKey:'ai-news',context:'context',source:{type:'ai-news'}});
  try{
    view.render().setReasoningEffort('low');await view.render().send('first');await tick();
    assert.equal(view.requests[0].input.reasoningEffort,'low');
    assert.equal(view.render().loading,true);
    view.render().setReasoningEffort('max');view.render();
    assert.equal(view.requests[0].input.reasoningEffort,'low');
    view.sinks.get('run-1')({runId:'run-1',seq:1,type:'done'});
    view.render();await view.render().send('second');
    assert.equal(view.requests[1].input.reasoningEffort,'max');
    assert.equal(view.storage.get('ft-reasoning-effort:created'),'max');
  }finally{view.close();}
});

test('blocked local storage does not prevent mode selection',()=>{
  const view=mount({conversationKey:'a',conversationId:'one',context:''});
  try{
    globalThis.localStorage={getItem(){throw new Error('blocked');},setItem(){throw new Error('blocked');}};
    view.render().setReasoningEffort('high');assert.equal(view.render().reasoningEffort,'high');
  }finally{view.close();}
});
