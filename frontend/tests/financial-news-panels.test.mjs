import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

async function load() {
  const code = await readFile(new URL('../src/components/news/FinancialNewsPanels.tsx', import.meta.url), 'utf8');
  const exports = {};
  vm.runInNewContext(ts.transpileModule(code, {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText, {
    exports, Date, Intl, require(name) {
      if (name==='react/jsx-runtime') return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
      return new Proxy({}, {get:(_,key)=>key});
    },
  });
  return exports;
}
function nodes(tree) {
  if (tree == null || typeof tree!=='object') return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (typeof tree.type==='function') return nodes(tree.type(tree.props));
  return [tree,...nodes(tree.props?.children)];
}
function text(tree) {
  if (tree==null || typeof tree==='boolean') return '';
  if (Array.isArray(tree)) return tree.map(text).join(' ');
  if (typeof tree!=='object') return String(tree);
  if (typeof tree.type==='function') return text(tree.type(tree.props));
  return text(tree.props?.children);
}
test('hot list renders five news titles linking out, not summaries or a second content stream', async()=>{
  const {GlobalHotList}=await load();
  const items=Array.from({length:10},(_,i)=>({id:String(i),title:`新闻${i}`,summary:'不应展示的灰色摘要',originalUrl:`https://example.test/${i}`,independentSourceCount:3,independentSources:['CNBC','BBC','中新社'],publishedAt:'2026-09-02T12:00:00Z'}));
  const tree=GlobalHotList({items,loading:false});
  const titles=nodes(tree).filter(n=>n.type==='a'&&n.props['data-news-title']);
  assert.equal(titles.length,5);
  assert.ok(titles.every(n=>n.props.target==='_blank'&&n.props.rel.includes('noopener')));
  assert.ok(!text(tree).includes('不应展示的灰色摘要'));
  assert.match(text(tree),/3\s+个独立来源/);
});
test('upcoming events expose Beijing times and date-only uncertainty with original links',async()=>{
  const {UpcomingEvents}=await load();
  const tree=UpcomingEvents({loading:false,data:{items:[
    {id:'1',title:'央行讲话',date:'2026-09-03',startsAt:'2026-09-03T12:30:00Z',precision:'time',category:'央行',source:'美联储',originalUrl:'https://example.test/1'},
    {id:'2',title:'公司财报',date:'2026-09-04',startsAt:null,precision:'date',category:'财报',source:'公司官网',sourceTimezone:'America/New_York',originalUrl:'https://example.test/2'},
  ],sources:[],stale:false,partial:false}});
  assert.ok(text(tree).includes('20:30'));
  assert.ok(text(tree).includes('时间待定'));
  assert.equal(nodes(tree).filter(n=>n.type==='a').length,2);
});
test('missing news and unavailable calendar have explicit non-fabricated empty states',async()=>{
  const {GlobalHotList,UpcomingEvents}=await load();
  assert.ok(text(GlobalHotList({items:[],loading:false})).includes('多来源'));
  assert.ok(text(UpcomingEvents({data:null,loading:false,error:'连接失败'})).includes('连接失败'));
  assert.equal(nodes(UpcomingEvents({data:{items:[],sources:[],partial:true},loading:false})).filter(n=>n.type==='a').length,0);
});
