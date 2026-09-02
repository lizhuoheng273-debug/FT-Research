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
  const exports={};
  vm.runInNewContext(compiled,{
    exports,Error,AbortController,document:{visibilityState:'visible'},
    setTimeout:fn=>{deadlines.set(++timer,fn);return timer;},clearTimeout:id=>deadlines.delete(id),
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
