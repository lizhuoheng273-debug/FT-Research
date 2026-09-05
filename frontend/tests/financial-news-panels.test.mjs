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
test('hot list keeps five rows visible, folds rows six to ten, and opens an internal story', async()=>{
  const {GlobalHotList}=await load();
  const items=Array.from({length:10},(_,i)=>({id:String(i),rank:i+1,title:`新闻${i+1}`,summary:'不应展示的灰色摘要',platformCount:3,rankScore:20-i,bestSourceRank:1,placements:[{sourceId:'sina',sourceName:'新浪财经',listKind:'popularity',sourceRank:i+1,originalUrl:`https://example.test/${i}`,fetchedAt:'2026-09-02T12:00:00Z'}],publishedAt:'2026-09-02T12:00:00Z'}));
  let opened;
  const tree=GlobalHotList({items,loading:false,onOpenStory:item=>{opened=item.id;}});
  const titles=nodes(tree).filter(n=>n.type==='button'&&n.props['data-news-title']);
  assert.equal(titles.length,10);
  titles[0].props.onClick();
  assert.equal(opened,'0');
  const details=nodes(tree).find(n=>n.type==='details');
  assert.equal(details.props.open,undefined);
  assert.equal(nodes(details).filter(n=>n.type==='button'&&n.props['data-news-title']).length,5);
  assert.equal(nodes(tree).filter(n=>n.type==='a').length,10);
  assert.equal(nodes(tree).find(n=>n.type==='a').props.href,undefined);
  assert.ok(!text(tree).includes('不应展示的灰色摘要'));
  assert.match(text(tree),/3\s+个平台上榜/);
  assert.match(text(tree),/展开第 6–10 条/);
});
test('hot list labels popularity and editorial placements without pretending both are readership ranks',async()=>{
  const {GlobalHotList}=await load();
  const tree=GlobalHotList({
    items:[{id:'x',rank:1,title:'财经热点',platformCount:2,placements:[
      {sourceId:'cls',sourceName:'财联社',listKind:'popularity',sourceRank:1,originalUrl:'https://cls.test/x'},
      {sourceId:'ths',sourceName:'同花顺',listKind:'editorial',sourceRank:2,originalUrl:'https://ths.test/x'},
    ]}],loading:false,generatedAt:'2026-09-04T05:32:00Z',
  });
  const content=text(tree);
  assert.match(content,/\u6570\u636e\u66f4\u65b0/);
  assert.match(content,/财联社\s+#\s*1\s+·\s+热门榜/);
  assert.match(content,/同花顺\s+#\s*2\s+·\s+编辑精选/);
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
  assert.ok(text(GlobalHotList({items:[],loading:false})).includes('暂无可用的平台热点榜'));
  assert.ok(text(UpcomingEvents({data:null,loading:false,error:'连接失败'})).includes('连接失败'));
  assert.equal(nodes(UpcomingEvents({data:{items:[],sources:[],partial:true},loading:false})).filter(n=>n.type==='a').length,0);
});
