const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const web=path.resolve(__dirname,'../gpt56_vnext/web');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.textContent='';this.events={};this.scrollTop=0;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 setAttribute(key,value){this[key]=value;}
 addEventListener(key,fn){this.events[key]=fn;}
 focus(){this.focused=true;}
}
const document={documentElement:{lang:'zh-CN',dataset:{}},createElement:tag=>new Element(tag)};
const context=vm.createContext({document,URL,Option:class extends Element{constructor(text,value){super('option');this.textContent=text;this.value=value;}},matchMedia:()=>({matches:true,addEventListener(){}}),localStorage:{getItem(){return 'system';},setItem(){}},console});
vm.runInContext(fs.readFileSync(path.join(web,'ui.js'),'utf8')+';this.UI=MeowUI',context);const ui=context.UI;

(async()=>{
 assert.equal(ui.modelName('other_known_external','其他'),'other');
 assert.equal(ui.modelName('gpt','GPT'),'GPT');
 assert.equal(ui.alias({id:'claude-fable-5.1'},'https://relay.test/v1'),'claude-fable-5-1');
 assert.equal(ui.alias({id:'x',request_model:'anthropic/claude-fable-5.1'},'https://openrouter.ai/api/v1'),'anthropic/claude-fable-5.1');
 assert.equal(ui.alias({id:'other',reference_only:true},'https://relay.test/v1'),'');
 const input=new Element();ui.autofill(input,{id:'claude-fable-5.1'},'https://relay.test/v1');input.value='custom';
 ui.autofill(input,{id:'gpt'},'https://relay.test/v1');assert.equal(input.value,'custom');
 const theme=new Element('select');ui.theme(theme);assert.equal(document.documentElement.dataset.theme,'dark');theme.value='light';theme.events.change();assert.equal(document.documentElement.dataset.theme,'light');
 const list=new Element(),button=new Element(),notice=new Element(),field=new Element();let resolve;
 ui.models({button,input,list,notice,fields:[field],connection:()=>({base_url:'https://old.test/v1'}),fetchModels:()=>new Promise(r=>resolve=r)});
 const pending=button.events.click();field.events.input();resolve({models:['stale']});await pending;assert.equal(list.children.length,0);assert.equal(button.disabled,false);
 const box=new Element(),rows=[{id:'a',model:'<img onerror=alert(1)>',url:'https://fixture.invalid/v1',created:'2026-09-08T00:00:00Z',done:9,valid:6,planned:20,status:'检测中',color:'running'}];let opened;
 ui.history(box,rows,{selected:'a',empty:'empty',open:id=>opened=id});box.children[0].children[0].onclick();assert.equal(opened,'a');
 assert.equal(box.children[0].children[0].children[0].children[0].textContent,rows[0].model);
 const old=box.children[0];ui.history(box,rows,{selected:'a',empty:'empty',open(){}});assert.equal(box.children[0],old);
 box.scrollTop=80;ui.history(box,[{...rows[0],done:10}],{selected:'a',empty:'empty',open(){}});assert.equal(box.scrollTop,80);
 assert.equal(ui.progress({done:3,valid:2,planned:20,attempts:5,retries:2,budget:10}),'已处理 3/20 · 有效样本 2/20 · 实际尝试 5 · 重试 2/10');
 assert.equal(ui.error({http_status:200,upstream:{code:'429',message:'rate limited'}}),'HTTP 200 · 429 · rate limited');
 assert.equal(ui.error({http_status:200,code:'response_decode_error',local:{type:'UnicodeDecodeError',message:'invalid byte'}},()=> '解码失败'),'HTTP 200 · 解码失败 · UnicodeDecodeError · invalid byte');
 const partial={quality_status:'sufficient',valid_samples:6,planned_samples:10};
 assert.ok(ui.partialNote(partial).includes('未满额'));
 assert.equal(ui.partialNote(partial,true),'');
 assert.equal(ui.partialNote({...partial,valid_samples:10}),'');
 assert.equal(ui.partialNote({...partial,quality_status:'insufficient_valid_samples'}),'');
 for(const file of ['ui.js','app.js','workbench.js','i18n.js'])new vm.Script(fs.readFileSync(path.join(web,file),'utf8'));
 console.log('Shared UI: aliases, manual input, theme, stale model fetch, safe report text, refresh/scroll and progress passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
