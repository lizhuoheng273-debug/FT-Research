import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const js=ts.transpileModule(await readFile(new URL('../src/lib/ndjson.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
function load(body){const exports={};vm.runInNewContext(js,{exports,TextDecoder,DOMException,fetch:async()=>({ok:true,body}),require:()=>({ApiError:Error,apiUrl:x=>x,authHeaders:()=>({})})});return exports.streamNdjson;}

test('NDJSON delivers split UTF-8 immediately and flushes final unterminated line',async()=>{
  let controller;const body=new ReadableStream({start(c){controller=c;}});const received=[];
  const pending=load(body)('/api/debate',{},event=>received.push(event));
  const bytes=new TextEncoder().encode('{"type":"delta","text":"你好"}\n');
  controller.enqueue(bytes.slice(0,26));controller.enqueue(bytes.slice(26));
  await new Promise(r=>setImmediate(r));assert.equal(received[0].text,'你好');
  controller.enqueue(new TextEncoder().encode('{"type":"done"}'));controller.close();await pending;
  assert.equal(received[1]?.type,'done');assert.equal(body.locked,false);
});

test('abort cancels a pending reader and prevents late callbacks',async()=>{
  let cancelled=false;const body=new ReadableStream({cancel(){cancelled=true;}});const ctrl=new AbortController();
  const promise=load(body)('/api/debate',{},()=>assert.fail('no events'),ctrl.signal);
  await new Promise(r=>setImmediate(r));ctrl.abort();
  await assert.rejects(promise,{name:'AbortError'});assert.equal(cancelled,true);assert.equal(body.locked,false);
});
