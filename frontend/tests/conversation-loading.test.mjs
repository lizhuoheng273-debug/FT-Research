import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
const compiled=await build({absWorkingDir:fileURLToPath(new URL('..',import.meta.url)).replaceAll('\\\\','/'),entryPoints:['src/components/ai/AiConversation.tsx'],bundle:true,write:false,platform:'node',format:'cjs',packages:'external',jsx:'automatic',alias:{'@':'./src'}});
const mod={exports:{}},require=createRequire(import.meta.url);
new Function('require','module','exports',compiled.outputFiles[0].text)(name=>name==='react-markdown'?ReactMarkdown:name==='remark-gfm'?remarkGfm:require(name),mod,mod.exports);
function render(messages){return renderToStaticMarkup(React.createElement(mod.exports.AiConversation,{suggestions:['SUGGESTION'],session:{messages,input:'',setInput(){},loading:false,historyLoading:true,error:null,progress:null,send(){},stop(){},toolUses:[]}}));}
test('cached history refresh does not insert a loading row into the answer',()=>{
 const html=render([{role:'assistant',content:'CACHED ANSWER',status:'complete'}]);
 assert.match(html,/CACHED ANSWER/); assert.doesNotMatch(html,/正在加载对话记录/);
});
test('cold history loading does not flash a new conversation',()=>{
 const html=render([]);assert.match(html,/正在加载对话记录/);
 assert.doesNotMatch(html,/SUGGESTION/);assert.doesNotMatch(html,/AI 会先阅读当前股票/);
});
