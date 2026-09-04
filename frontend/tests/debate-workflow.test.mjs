import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const compile=source=>ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const code=compile(await readFile(new URL('../src/pages/Debate.tsx',import.meta.url),'utf8'));
const flush=()=>new Promise(r=>setImmediate(r));
function text(n){if(n==null||typeof n==='boolean')return '';if(Array.isArray(n))return n.map(text).join('');if(typeof n!=='object')return String(n);return text(n.props?.children);}
function nodes(n){if(!n||typeof n!=='object')return [];if(Array.isArray(n))return n.flatMap(nodes);return[n,...nodes(n.props?.children)];}
function mount(){
  const cells=[],effects=[],cleanups=[],requests=[],routes=[],saved=[];let cursor=0,mounted=false;
  const exports={};
  vm.runInNewContext(code,{exports,Error,DOMException,AbortController,require(name){
    if(name==='react')return{
      useState(initial){const i=cursor++;if(!(i in cells))cells[i]=typeof initial==='function'?initial():initial;return[cells[i],v=>{cells[i]=typeof v==='function'?v(cells[i]):v;}];},
      useRef(initial){const i=cursor++;return cells[i]??={current:initial};},useEffect(fn){if(!mounted)effects.push(fn);},
    };
    if(name==='react/jsx-runtime')return{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
    if(name==='react-router-dom')return{useNavigate:()=>url=>routes.push(url),Link:'Link'};
    if(name==='@/lib/agents')return{debateStream:(code,rounds,h,signal)=>new Promise((resolve,reject)=>requests.push({code,rounds,h,signal,resolve,reject}))};
    if(name==='@/lib/notes')return{addNote:(...args)=>saved.push(args)};
    if(name==='@/lib/api')return{ApiError:Error};
    return new Proxy({},{get:(_,key)=>key});
  }});
  function render(){cursor=0;const tree=exports.Debate();if(!mounted){mounted=true;effects.forEach(fn=>cleanups.push(fn()));}return tree;}
  render();
  return{render,requests,routes,saved,input:()=>nodes(render()).find(n=>n.type==='StockSearchInput').props,
    button:label=>nodes(render()).find(n=>n.type==='button'&&text(n).includes(label)),unmount:()=>cleanups.forEach(fn=>fn?.())};
}
test('stock name selection stays on debate and submits only its code after clicking start',async()=>{
  const app=mount();app.input().onSelect({name:'贵州茅台',code:'600519'});
  assert.equal(app.routes.length,0);assert.equal(app.input().value,'600519');assert.equal(app.requests.length,0);
  app.button('开始辩论').props.onClick();assert.equal(app.requests[0].code,'600519');assert.equal(app.requests[0].rounds,1);
  app.unmount();
});
test('partial delta renders immediately; stopping blocks late updates and saving',async()=>{
  const app=mount();app.input().onChange('600519');app.button('开始辩论').props.onClick();const req=app.requests[0];
  req.h.onStageStart('bull','多方');req.h.onDelta('bull','第一段');assert.match(text(app.render()),/第一段/);
  app.button('中止').props.onClick();req.h.onDelta('bull','停止后的脏内容');req.resolve();await flush();
  assert.equal(req.signal.aborted,true);assert.doesNotMatch(text(app.render()),/脏内容|辩论完成/);assert.equal(app.button('保存'),undefined);
});
test('unmount aborts active debate',()=>{const app=mount();app.input().onChange('600519');app.button('开始辩论').props.onClick();app.unmount();assert.equal(app.requests[0].signal.aborted,true);});
test('old request cleanup cannot stop a new debate',async()=>{
  const app=mount();app.input().onChange('600519');app.button('开始辩论').props.onClick();const old=app.requests[0];
  app.button('中止').props.onClick();app.input().onChange('600183');app.button('开始辩论').props.onClick();
  old.resolve();await flush();assert.ok(app.button('中止'));assert.equal(app.input().disabled,true);app.unmount();
});
test('partial failure is not labeled completed or saved as a complete report',async()=>{
  const app=mount();app.input().onChange('600519');app.button('开始辩论').props.onClick();const req=app.requests[0];
  req.h.onStageStart('bull','多方');req.h.onError('上游失败','bull');req.h.onStageDone('bull','多方','失败',true);req.resolve();await flush();
  assert.doesNotMatch(text(app.render()),/辩论完成/);assert.equal(app.button('保存'),undefined);app.unmount();
});
test('complete stages save one full report against the selected stock',async()=>{
  const app=mount();app.input().onChange('600519');app.button('开始辩论').props.onClick();const req=app.requests[0];
  for(const stage of ['bull','bear','referee']){req.h.onStageStart(stage,stage);req.h.onDelta(stage,stage+'正文');req.h.onStageDone(stage,stage,stage+'正文',false);}
  req.resolve();await flush();app.button('保存').props.onClick();assert.equal(app.saved.length,1);assert.match(app.saved[0][1],/600519/);assert.match(app.saved[0][2],/referee正文/);app.unmount();
});

test('debate client uses server config, forwards failures and requires a terminal event',async()=>{
  const exports={},requests=[];let events=[{type:'stage_done',stage:'bull',label:'多方',content:'失败',failed:true},{type:'done',stages:[]}];let failed;
  vm.runInNewContext(compile(await readFile(new URL('../src/lib/agents.ts',import.meta.url),'utf8')),{exports,require(name){
    if(name==='@/lib/api')return{ApiError:Error};
    if(name==='@/lib/llm')return{loadLlm:()=>null};
    if(name==='@/lib/ndjson')return{streamNdjson:async(url,body,callback)=>{requests.push({url,body});events.forEach(callback);}};
  }});
  await exports.debateStream('600519',1,{onStageDone:(_s,_l,_c,f)=>{failed=f;}});
  assert.equal(JSON.stringify(requests[0].body),'{"code":"600519","rounds":1}');assert.equal(failed,true);
  events=[{type:'delta',stage:'bull',text:'截断'}];await assert.rejects(()=>exports.debateStream('600519',1),/中断|完整|结束/);
});
