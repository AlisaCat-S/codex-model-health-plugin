// Retention export stays bound to the selected report while the UI changes.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=fs.existsSync(path.resolve(__dirname,'../gpt56_vnext'))?path.resolve(__dirname,'..'):path.resolve(__dirname,'../../..');
const source=fs.readFileSync(path.join(root,'gpt56_vnext/web/workbench.js'),'utf8');
(async()=>{
 let exporter,download;const state={sessionId:'A'},requests=[];
 const start=source.indexOf('action("retention-export",');const end=source.indexOf('}, "progress");',start)+'}, "progress");'.length;
 vm.runInNewContext(source.slice(start,end),{state,TextEncoder,t:x=>x,action:(_,fn)=>exporter=fn,
  json:async url=>{requests.push(url);state.sessionId='B';return requests.length===1?{coverage:{},records:[{attempt_id:1}]}:{coverage:{},records:[]};},
  download:(data,name)=>download={data,name}});
 await exporter();assert(requests.every(x=>x.includes('/A?')));assert.equal(download.data.session_id,'A');assert.equal(download.name,'meow-evidence-A.json');
 const html=fs.readFileSync(path.join(root,'gpt56_vnext/web/index.html'),'utf8');
 for(const id of ['allow-http','preset-http'])assert(html.includes('id="'+id+'"'));
 assert(source.includes('allow_insecure: $("preset-http").checked'));
 console.log('Report export ownership and local HTTP controls passed; retired collector UI is covered by CLI workflow tests.');
})().catch(e=>{console.error(e);process.exitCode=1;});
