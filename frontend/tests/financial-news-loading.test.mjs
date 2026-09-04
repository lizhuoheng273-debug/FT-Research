import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const source=await readFile(new URL('../src/pages/FinancialNews.tsx',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function mount(api){
  const cells=[],effects=[],cleanups=[],deadlines=new Map();
  let cursor=0,mounted=false,timer=0;
  const fakeSetTimeout=fn=>{deadlines.set(++timer,fn);return timer;};
  const fakeClearTimeout=id=>deadlines.delete(id);
  const exports={};
  vm.runInNewContext(compiled,{
    exports,Error,AbortController,document:{visibilityState:'visible'},window:{setTimeout:fakeSetTimeout,clearTimeout:fakeClearTimeout},
    setTimeout:fakeSetTimeout,clearTimeout:fakeClearTimeout,
    setInterval:()=>++timer,clearInterval:()=>{},
    require(name){
      if(name==='react')return{
        useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>{cells[i]=typeof v==='function'?v(cells[i]):v;}];},
        useEffect(fn){if(!mounted)effects.push(fn);},useMemo:fn=>fn(),
      };
      if(name==='react/jsx-runtime')return{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
      if(name==='@/lib/api')return{api};
      return new Proxy({},{get:(_,key)=>key});
    },
  });
  function render(){cursor=0;const tree=exports.FinancialNews();if(!mounted){mounted=true;effects.forEach(fn=>cleanups.push(fn()));}return tree;}
  function find(node,type){if(Array.isArray(node))return node.map(n=>find(n,type)).find(Boolean);if(!node||typeof node!=='object')return;return node.type===type?node.props:find(node.props?.children,type);}
  render();
  return{component:type=>find(render(),type),expire:()=>[...deadlines.values()].forEach(fn=>fn()),unmount:()=>cleanups.forEach(fn=>fn?.())};
}

function findButton(node,label){
  if(Array.isArray(node))return node.map(n=>findButton(n,label)).find(Boolean);
  if(!node||typeof node!=='object')return;
  if(node.type==='button'&&node.props?.['aria-label']===label)return node.props;
  return findButton(node.props?.children,label);
}
function findRole(node,role){
  if(Array.isArray(node))return node.map(n=>findRole(n,role)).find(Boolean);
  if(!node||typeof node!=='object')return;
  if(node.props?.role===role)return node.props;
  return findRole(node.props?.children,role);
}
function nodeText(node){
  if(node==null||typeof node==='boolean')return '';
  if(Array.isArray(node))return node.map(nodeText).join(' ');
  if(typeof node!=='object')return String(node);
  return nodeText(node.props?.children);
}
test('calendar renders independently while headlines are pending, without watchlist requests',async()=>{
  let signal;
  const app=mount({financialNewsOverview:s=>{signal=s;return new Promise(()=>{});},financialNewsCalendar:()=>Promise.resolve({items:[{id:'confirmed'}]})});
  await flush();
  assert.equal(app.component('UpcomingEvents').loading,false);
  assert.equal(app.component('UpcomingEvents').data.items[0].id,'confirmed');
  assert.equal(app.component('GlobalHotList').loading,true);
  app.unmount();assert.equal(signal.aborted,true);
});
test('a timed out calendar exits loading and leaves the hot list available',async()=>{
  const app=mount({financialNewsOverview:()=>Promise.resolve({globalHighlights:[{id:'news'}]}),financialNewsCalendar:signal=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted'))))});
  await flush();app.expire();await flush();
  assert.equal(app.component('GlobalHotList').items[0].id,'news');
  assert.equal(app.component('UpcomingEvents').loading,false);
  assert.match(app.component('UpcomingEvents').error,/超时/);
  app.unmount();
});
test('late responses after unmount cannot update the prior page',async()=>{
  let resolve;
  const app=mount({financialNewsOverview:()=>new Promise(r=>{resolve=r;}),financialNewsCalendar:()=>Promise.resolve({items:[]})});
  await flush();app.unmount();resolve({globalHighlights:[{id:'late'}]});await flush();
  assert.equal(app.component('GlobalHotList').items.length,0);
});
test('refresh button forces a calendar refresh and exposes visible progress',async()=>{
  let finish, calls=0;
  const app=mount({
    financialNewsOverview:()=>Promise.resolve({globalHighlights:[]}),
    financialNewsCalendar:()=>Promise.resolve({items:[]}),
    financialNewsCalendarRefresh:()=>{calls++;return new Promise(resolve=>{finish=resolve;});},
  });
  await flush();
  let button=findButton(app.component('PageHeader').actions,'刷新页面');
  assert.equal(button.title,'刷新页面');
  button.onClick();
  button=findButton(app.component('PageHeader').actions,'正在刷新最新日程');
  assert.equal(button['aria-busy'],true);
  assert.equal(calls,1);
  finish({outcome:'updated',calendar:{items:[{id:'latest'}],partial:false,stale:false}});
  await flush();
  const actions=app.component('PageHeader').actions;
  assert.equal(findButton(actions,'正在刷新最新日程'),undefined);
  assert.match(nodeText(actions),/最新日程已更新/);
  assert.doesNotMatch(findRole(actions,'status').className,/\bhidden\b/);
  app.unmount();
});
