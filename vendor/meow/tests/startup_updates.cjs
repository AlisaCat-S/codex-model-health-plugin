const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=fs.existsSync(path.resolve(__dirname,'../gpt56_vnext'))?path.resolve(__dirname,'..'):path.resolve(__dirname,'../../..');
const source=fs.readFileSync(path.join(root,'gpt56_vnext/web/workbench.js'),'utf8');
const fields=new Map();let calls=[],failure=false;
const local=[{id:'gpt',mode:'gpt',version:'4.5.3-predictive.2',publisher:'maintainer'}];
const context=vm.createContext({Promise,locale:'en',state:{snapshot:{packages:local,catalog:{packages:[]}}},
 $:id=>{if(!fields.has(id))fields.set(id,{hidden:true,textContent:'',disabled:true});return fields.get(id);},t:s=>s,
 post:async url=>{calls.push(url);if(failure)throw Error('offline');return url.includes('program')?{available:true,current_version:'4.5.3',latest_version:'4.6.0',notes:'fixture'}:{packages:[{id:'gpt',mode:'gpt',publisher:'maintainer',version:'4.6.0'}]};}});
vm.runInContext(source.slice(source.indexOf('let programUpdate='),source.indexOf('action("quick-update",')),context);
(async()=>{
 assert(context.newerVersion('4.5.10','4.5.9'));assert(!context.newerVersion('4.5.3','4.5.3'));
 assert(context.newerVersion('4.5.3','4.5.3-predictive.2'));
 await context.checkUpdates();assert.equal(calls.length,2);
 assert(calls.every(v=>!v.includes('install')&&!v.includes('download')));
 assert.equal(fields.get('startup-updates').hidden,false);assert.equal(fields.get('startup-baseline-update').hidden,false);
 context.state.snapshot.catalog.packages.push({id:'evil',mode:'gpt',publisher:'community',version:'99.0.0'});
 assert.equal(context.baselineUpdates().length,1);
 context.state.snapshot.catalog.packages[0].withdrawn='withdrawn';assert.equal(context.baselineUpdates().length,0);
 context.state.snapshot.packages.push({id:'gpt-chat',mode:'chat',version:'4.5.4-chat.1',publisher:'maintainer'});
 context.state.snapshot.catalog.packages.push({id:'claude-chat',mode:'chat',version:'4.5.4-chat.1',publisher:'maintainer'});
 assert.equal(context.baselineUpdates().length,1,'Different Chat packages must not hide each other');
 failure=true;await context.checkUpdates(true);assert(fields.get('program-status').textContent.includes('自动检查'));
 assert(calls.every(v=>!v.includes('install')&&!v.includes('download')));
 console.log('Update checks, version ordering, baseline provenance, withdrawal and offline non-installation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
