const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/report_workspace.js','utf8');
const code=source.slice(source.indexOf("const feedback ="),source.indexOf('// Restored drafts'));
const feedback={textContent:''},toast={hidden:true};
let changed,id=0;const timers=new Map();
const context={document:{getElementById:key=>key==='close-feedback'?feedback:toast},
  MutationObserver:class{constructor(callback){changed=callback;}observe(){}},
  clearTimeout:key=>timers.delete(key),setTimeout:(callback,delay)=>{assert.equal(delay,3000);timers.set(++id,callback);return id;}};
vm.runInNewContext(code,context);
for(const message of ['已复制简历。','请检查时间区间','保存失败','已保存到文件']){
  feedback.textContent=message;changed();assert.equal(toast.hidden,false);assert.equal(timers.size,1);
  const callback=[...timers.values()][0];timers.clear();callback();assert.equal(feedback.textContent,'');assert.equal(toast.hidden,true);
}
feedback.textContent='旧提示';changed();const old=[...timers.values()][0];feedback.textContent='新提示';changed();old();assert.equal(feedback.textContent,'新提示');assert.equal(timers.size,1);
console.log('All toast messages dismiss after 3000ms; new messages reset the timer');
