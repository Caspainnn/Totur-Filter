// Run the actual settings scripts against a small DOM double; no browser, network or private data.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.handlers={};this.attrs={};this.value='';this.textContent='';this.hidden=false;this.classes=new Set();this.classList={add:(...names)=>names.forEach(x=>this.classes.add(x)),toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};}
  set className(value){this.classes=new Set(value.split(' '));} get className(){return [...this.classes].join(' ');}
  set value(value){this._value=value;if(this.tagName==='select'&&this.children)this.options.forEach(option=>option.selected=option.value===value);}get value(){return this.tagName==='select'?this.selectedOptions[0]?.value||this._value:this._value;}
  get options(){return this.children.filter(x=>x.tagName==='option');}get selectedOptions(){return this.options.filter(x=>x.selected);}
  appendChild(child){child.remove();child.parentElement=this;this.children.push(child);return child;}
  insertBefore(child,before){child.remove();child.parentElement=this;const index=this.children.indexOf(before);this.children.splice(index<0?this.children.length:index,0,child);return child;}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(x=>x!==this);this.parentElement=null;}
  replaceChildren(...children){this.children.forEach(x=>x.parentElement=null);this.children=[];children.forEach(x=>this.appendChild(x));}
  setAttribute(key,value){this.attrs[key]=value;}getAttribute(key){return this.attrs[key];}
  addEventListener(type,handler){(this.handlers[type]||=[]).push(handler);}
  dispatchEvent(event){event.target||=this;for(const handler of this.handlers[event.type]||[])handler(event);if(event.bubbles)this.parentElement?.dispatchEvent(event);return true;}
  click(){this.dispatchEvent({type:'click',target:this});}focus(){}select(){}showModal(){this.open=true;}close(){this.open=false;}
  matches(selector){if(selector==='*')return true;if(selector.startsWith('.'))return this.classes.has(selector.slice(1));if(selector==='[data-path]')return Boolean(this.dataset.path);if(selector==='input:checked')return this.tagName==='input'&&this.checked;return this.tagName===selector;}
  closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector);}
  querySelectorAll(selector){const direct=selector.startsWith(':scope > ');if(direct)selector=selector.slice(9);const all=direct?this.children:this.children.flatMap(x=>[x,...x.querySelectorAll('*')]);return all.filter(x=>x.matches(selector));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const ids={},create=(id,tag='div')=>ids[id]=new Element(tag);
const section=create('preferences'),form=create('preference-form','form'),holder=create('preference-fields');section.appendChild(form);form.appendChild(holder);section.appendChild(create('back-report','button'));section.appendChild(create('learned-rules'));create('close-feedback');
create('settings-schema').textContent=JSON.stringify({grade_groups:{小学:['小学一年级'],初中:['初中一年级']},subject_choices:['数学','英语']});
const baseline={'pay.minimum_hourly_cny':100,'pay.range_crossing_minimum':'accept_if_maximum_meets_minimum','commute.maximum_one_way_minutes':60,'commute.city':'示例城市','commute.origin':'示例地铁站',
  'grades.accepted':['小学一年级'],'subjects.science_subjects':['数学'],'subjects.primary_academic_subjects':['数学'],
  'availability.weekdays.start':'18:00','availability.weekdays.days':[1,2,3,4,5],'availability.full_day_weekdays.days':[],'availability.weekends.days':[6,7],
  'availability.unspecified_class_time':'needs_confirmation','tutor_profile.gender':'male','tutor_profile.university':'示例大学','tutor_profile.academic_stage':'master_1','tutor_profile.resume':'大学生简历\n姓名：示例',
  'tutor_profile.teaching_experience_levels':['primary']};
create('preference-data').textContent=JSON.stringify(baseline);
const listeners={},downloads=[],blobs=new Map(),storage=new Map();
let copied='';
const document={body:new Element('body'),createElement:tag=>new Element(tag),createTextNode:text=>Object.assign(new Element('text'),{textContent:text}),getElementById:id=>ids[id]||null,
  addEventListener(type,fn){(listeners[type]||=[]).push(fn);},dispatchEvent(event){for(const fn of listeners[event.type]||[])fn(event);}};
document.body.appendChild(section);
document.documentElement=new Element('html');create('theme-toggle','button');
const originalCreate=document.createElement;
document.createElement=tag=>{const el=originalCreate(tag);if(tag==='a')el.click=()=>downloads.push({name:el.download,blob:blobs.get(el.href)});return el;};
class Event {constructor(type,opts={}){this.type=type;Object.assign(this,opts);}}
const context={document,window:{tutorUserState:{preference_overrides:{},edited_preference_paths:[],rejection_feedback:[],deleted_feedback_rules:[]},addEventListener(){}},
  location:{hash:'#preferences'},localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},navigator:{clipboard:{async writeText(value){copied=value;}}},
  Event,CustomEvent:Event,Blob,URL:{createObjectURL(blob){const key='blob:'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}},setTimeout(){},console};
vm.createContext(context);
const workspaceSource=fs.readFileSync('src/report_workspace.js','utf8');
const themeCode=workspaceSource.slice(workspaceSource.indexOf('const themeButton'),workspaceSource.indexOf('const search'));
vm.runInContext('(()=>{'+themeCode+'})();',context);
assert(ids['theme-toggle'].innerHTML.includes('M554.666667'));
ids['theme-toggle'].click();assert.equal(document.documentElement.dataset.theme,'light');
assert(ids['theme-toggle'].innerHTML.includes('M425.799111'));
assert.equal(ids['theme-toggle'].getAttribute('title'),'切换到暗色主题');
vm.runInContext('(()=>{'+themeCode+'})();',context);assert.equal(document.documentElement.dataset.theme,'light','Theme must restore after reload');
vm.runInContext(fs.readFileSync('src/preference_editor.js','utf8'),context);
vm.runInContext(fs.readFileSync('src/settings_workspace.js','utf8').replace("form.addEventListener('submit'", "window.testSettings={parseLegacy,importValues};form.addEventListener('submit'"),context);
const editor=context.window.tutorPreferenceEditor;
const messageWindow=editor.controls.get('message_window_days').control;
assert.equal(messageWindow.value,'7');
messageWindow.value='1';messageWindow.dispatchEvent(new Event('change'));
assert.equal(context.window.tutorUserState.preference_overrides.message_window_days,'1');
assert(ids['close-feedback'].textContent.includes('过去1天'));
const all=()=>document.body.querySelectorAll('*');
const byText=(tag,text)=>all().find(x=>x.tagName===tag&&x.textContent===text);
const input=(label)=>all().find(x=>x.attrs['aria-label']===label);
const clickChange=(el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));};
function setClock(label,value){const [hour,minute]=value.split(':');input(label+'分钟').value=minute;input(label+'分钟').dispatchEvent(new Event('change'));input(label+'小时').value=hour;input(label+'小时').dispatchEvent(new Event('change'));}
const clockValue=label=>input(label+'小时').value+':'+input(label+'分钟').value;
assert(!all().includes(ids['back-report']));
assert(byText('button','下载模板').closest('.settings-header'));
assert(byText('button','导入模板'));
assert(editor.controls.get('pending_female_keyword_rejection').control.closest('.preference-field').hidden);
const experience=all().find(x=>x.className==='experience-checks');
assert.equal(experience.querySelectorAll('input').length,5);
const preschool=experience.querySelectorAll('input')[0];preschool.checked=true;preschool.dispatchEvent(new Event('change',{bubbles:true}));
assert.deepEqual(Array.from(editor.collect()['tutor_profile.teaching_experience_levels']),['preschool','primary']);
byText('button','授课时间').click();
const monday=all().find(x=>x.className==='interval-day');monday.children.at(-1).click();
assert(input('周一区间2开始小时'),'Adding before a midnight-ending interval must still create a row');
assert.throws(()=>editor.collect(),'Incomplete draft interval cannot be saved');
setClock('周一区间2开始','08:30');setClock('周一区间2结束','12:00');
assert.equal(editor.collect()['availability.daily_intervals']['1'].length,2);
assert.equal(clockValue('周一区间1开始'),'08:30','Morning interval must sort before evening');
assert.equal(clockValue('周一区间2结束'),'24:00','Existing interval must remain unchanged');
assert(input('删除周一区间1').innerHTML.includes('fill="#D81E06"'));
input('删除周一区间1').click();assert.equal(editor.collect()['availability.daily_intervals']['1'].length,1);
setClock('周一区间1结束','17:00');assert.throws(()=>editor.collect());
setClock('周一区间1结束','20:00');
byText('button','下载模板').click();byText('button','导出用户设置').click();byText('button','一键复制简历').click();
(async()=>{
  const template=await downloads[0].blob.text(),exported=await downloads[1].blob.text();
  assert(template.includes('未填')&&!template.includes('示例大学')&&!template.includes('姓名：示例'));
  assert(exported.includes('18:00–20:00')&&exported.includes('用户简历')&&!exported.includes('开启待确认原文'));
  const parsed=context.window.testSettings.parseLegacy(exported);
  assert.equal(parsed['availability.daily_intervals']['1'][0][1],'20:00');
  assert.equal(parsed['tutor_profile.resume'],'大学生简历\n姓名：示例');
  assert.deepEqual(Array.from(parsed['tutor_profile.teaching_experience_levels']),['preschool','primary']);
  context.window.testSettings.importValues(parsed);
  editor.updateBaseline({'grades.accepted':['初中一年级'],'preferred_address_keywords':['新地点']});
  document.dispatchEvent(new Event('tutor-settings-saved'));
  const junior=all().find(x=>x.tagName==='label'&&x.children.some(child=>child.textContent==='初中一年级'));
  assert(junior.children[0].checked,'Saved merge must refresh visible grades');
  assert(byText('button','新地点 ×'),'Saved merge must refresh visible location tags');
  assert.equal(copied,'大学生简历\n姓名：示例');
  console.log('Settings UI: checkboxes, interval add/edit/delete/validation, header tools, private-free template, export and copy passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
