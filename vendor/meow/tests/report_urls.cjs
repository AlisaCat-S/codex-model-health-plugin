const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=fs.existsSync(path.resolve(__dirname,'../gpt56_vnext'))?path.resolve(__dirname,'..'):path.resolve(__dirname,'../../..');
const context=vm.createContext({URL});
vm.runInContext(fs.readFileSync(path.join(root,'gpt56_vnext/web/ui.js'),'utf8')+';this.UI=MeowUI',context);
for(const language of ['zh-CN','en']){
 const text=context.UI.reportMeta({model:'a',requestModel:'alias-a',url:'https://tested.invalid/v1',group:'group-a'},language);
 assert(text.includes('https://tested.invalid/v1'));assert(text.includes('alias-a'));assert(text.includes('group-a'));
 const missing=context.UI.reportMeta({model:'a',requestModel:'a'},language);
 assert(!missing.includes('undefined'));assert(!missing.includes('null'));
}
console.log('Shared report URL, alias, group and historical missing-field checks passed.');
