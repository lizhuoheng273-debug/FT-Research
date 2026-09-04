import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

async function load(path, expose, review = null) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  let firstState = true;
  vm.runInNewContext(js + '\n' + expose, { exports, require(name) {
    if (name === 'react') return {useState(initial) {const value = firstState ? review : initial; firstState = false; return [value, () => {}];},useEffect() {},useMemo: f => f()};
    if (name === 'react/jsx-runtime') return {jsx: (type,props) => ({type,props}),jsxs: (type,props) => ({type,props})};
    if (name === '@/lib/utils') return {cn: (...parts) => parts.filter(Boolean).join(' ')};
    return new Proxy({}, {get: (_,key) => key});
  }});
  return exports;
}
function nodes(tree) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (typeof tree.type === 'function') return nodes(tree.type(tree.props));
  return [tree, ...nodes(tree.props?.children)];
}
function text(tree) {
  if (tree == null || typeof tree === 'boolean') return '';
  if (Array.isArray(tree)) return tree.map(text).join(' ');
  if (typeof tree !== 'object') return String(tree);
  if (typeof tree.type === 'function') return text(tree.type(tree.props));
  return text(tree.props?.children);
}
test('daily candles open at the latest 30 trading sessions without discarding older MA data', async () => {
  const {chartOption} = await load('../src/components/market/MarketChart.tsx', 'exports.chartOption = chartOption;');
  const points = Array.from({length: 250}, (_,i) => ({time:`2026-${i}`,open:10,close:11,high:12,low:9,volume:100,amount:1000}));
  const option = chartOption({period:'daily',asset:'index',points});
  assert.equal(option.series[0].data.length, 250);
  for (const zoom of option.dataZoom) {assert.equal(zoom.startValue, 220);assert.equal(zoom.endValue,249);}
  const short = chartOption({period:'daily',asset:'index',points:points.slice(0,12)});
  assert.equal(short.dataZoom[0].startValue,0);
  const dated = chartOption({period:'daily',asset:'index',points:[{...points[0],time:'2026-09-02T00:00:00'}]});
  assert.equal(dated.xAxis[0].data[0], '09-02');
});
test('emotion percentages are rounded for display rather than exposing floating point noise', async () => {
  const {DailyReview} = await load('../src/pages/DailyReview.tsx','',{
    tradingDate:'2026-09-02',indices:[],breadth:{up:12,down:8,upRatio:60,downRatio:40},liquidity:{},sectors:[],turnoverTop:[],
    shortTermEmotion:{zt_count:52,dt_count:8,max_boards:4,lianban_count:13,seal_rate:0.776,break_rate:0.224,promotion_rate:0.157},
  });
  const content = text(DailyReview());
  assert.ok(content.includes('77.6%'));
  assert.ok(content.includes('22.4%'));
  assert.ok(!content.includes('00000000000'));
});
test('turnover preview has five entries, labelled numeric columns and no links nested in buttons', async () => {
  const {DailyReview} = await load('../src/pages/DailyReview.tsx','',{
    tradingDate:'2026-09-02',indices:[],breadth:{},liquidity:{},sectors:[],shortTermEmotion:null,
    turnoverTop:Array.from({length:20},(_,i)=>({code:String(600000+i),name:`股票${i}`,price:10,pct:1,amount:1e8})),
  });
  // Closed modal content is outside the preview and tested by its own component.
  const tree = DailyReview();
  const visible = {...tree,props:{...tree.props,children:tree.props.children.filter(n=>n?.type!=='MarketReviewModal')}};
  const all = nodes(visible);
  assert.equal(all.filter(n=>n.type==='Link'&&n.props.to?.startsWith('/finance/stocks/')).length,5);
  for (const heading of ['名称','现价','涨跌幅','成交额']) assert.ok(all.some(n=>n.type==='th'&&text(n).includes(heading)));
  for (const button of all.filter(n=>n.type==='button')) assert.ok(!nodes(button.props.children).some(n=>n.type==='Link'));
});

test('intraday review explains that the AI close brief appears after market close', async () => {
  const {DailyReview} = await load('../src/pages/DailyReview.tsx','',{
    tradingDate:'2026-09-04',final:false,indices:[],breadth:{},liquidity:{},sectors:[],turnoverTop:[],shortTermEmotion:null,
    brief:{status:'missing',text:'',generatedAt:null},sources:[],
  });

  const content = text(DailyReview());
  assert.ok(content.includes('当前尚未收盘，AI 收盘简述将在收盘后生成。'));
});

test('turnover change is labelled as a same-time previous-session comparison', async () => {
  const {DailyReview} = await load('../src/pages/DailyReview.tsx','',{
    tradingDate:'2026-09-04',final:false,indices:[],breadth:{up:1,down:1},
    liquidity:{todayAmountYuan:1234171931604,previousAmountYuan:1098668918331.46,changeAmountYuan:135503013272.54,changePct:12.33,direction:'expanded'},
    sectors:[],turnoverTop:[],shortTermEmotion:null,brief:{status:'missing',text:'',generatedAt:null},sources:[],
  });

  const tree = DailyReview();
  const content = text(tree);
  assert.ok(content.includes('较上一交易日同期放量'));
  assert.ok(content.includes('1,355.03 亿'));
  assert.ok(content.includes('12.33%'));
  const header = nodes(tree).find(node => node.type === 'PageHeader');
  assert.ok(header.props.actions.props.context.includes('较上一交易日同期'));
});
