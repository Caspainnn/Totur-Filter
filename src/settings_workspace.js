/* Local settings UI and reviewed document import; no remote requests. */
(() => {
const editor = window.tutorPreferenceEditor;
const holder = document.getElementById('preference-fields');
if (!editor || !holder) return;
const form = document.getElementById('preference-form');
const section = document.getElementById('preferences');
const status = document.getElementById('close-feedback');
let schema = {};
try {schema = JSON.parse(document.getElementById('settings-schema').textContent);} catch {}
const groups = [
  ['profile','本人信息','填写本人条件，无法判断的教师要求仍需确认'],
  ['subjects','年级与科目','按学段选择年级和可接科目'],
  ['time','授课时间','设置可上课日与时间规则'],
  ['pay','报价','最低时薪与区间报价规则'],
  ['location','地点与通勤','优先地点、黑名单和公共交通'],
  ['runtime','运行设置','本机运行信息与已学习规则']
];
function node(tag, content, className) {const item = document.createElement(tag); if (content) item.textContent = content; if (className) item.className=className; return item;}
const tabs = node('nav', '', 'settings-tabs'); tabs.setAttribute('aria-label','设置分组');
const panels = new Map(), tabButtons = new Map();
for (const [id,title,description] of groups) {
  const button = node('button',title); button.type='button'; button.dataset.settingsTab=id;
  tabs.appendChild(button); tabButtons.set(id,button);
  const panel = node('div','', 'settings-panel'); panel.dataset.settingsGroup=id; panel.hidden=true;
  panel.appendChild(node('h3',title)); panel.appendChild(node('p',description,'settings-description'));
  const fields = node('div','','settings-fields'); panel.appendChild(fields); holder.appendChild(panel);
  panels.set(id,{panel,fields});
  button.addEventListener('click',()=>show(id));
}
section.insertBefore(tabs,form);
function show(id) {
  panels.forEach(({panel},key)=>{panel.hidden=key!==id; tabButtons.get(key).setAttribute('aria-pressed',String(key===id));});
}
function wrapper(path) {return editor.controls.get(path)?.control.closest('.preference-field');}
for (const [path] of editor.controls) {
  const destination = path.startsWith('tutor_profile.') ? 'profile' : path.startsWith('subjects.') || path==='grades.accepted' ? 'subjects' : path.startsWith('availability.') ? 'time' : path.startsWith('pay.') ? 'pay' : path.startsWith('commute.') || ['preferred_address_keywords','location_blacklist'].includes(path) ? 'location' : 'runtime';
  panels.get(destination).fields.appendChild(wrapper(path));
}
const messageWindow=editor.controls.get('message_window_days').control;
wrapper('message_window_days').appendChild(node('p','切换后立即用本地七天数据重新筛选，列表和待选项同步更新；保存后下次打开继续使用。不会重新采集消息或调用地图。','note'));
messageWindow.addEventListener('change',()=>{changed(messageWindow);document.dispatchEvent(new CustomEvent('tutor-message-window-changed'));status.textContent='已按过去'+messageWindow.value+'天重新筛选本地订单。';});
// Preserve the legacy controls for round-trip compatibility; stage controls replace their presentation.
for (const path of ['subjects.primary_academic_subjects','subjects.science_subjects','subjects.by_stage','pending_female_keyword_rejection']) wrapper(path).hidden=true;
const context = section.querySelector('.preference-context');
if (context) panels.get('runtime').fields.appendChild(context);
const learned = document.getElementById('learned-rules');
panels.get('runtime').panel.appendChild(node('h4','已学习的排除规则'));
panels.get('runtime').panel.appendChild(node('p','删除规则不会解除原订单的熄单；保存后下次筛选生效。','note'));
panels.get('runtime').panel.appendChild(learned);
section.querySelectorAll(':scope > h3').forEach(item=>item.remove());
section.querySelectorAll(':scope > p').forEach(item=>item.hidden=true);

const gradeSelect = editor.controls.get('grades.accepted').control;
gradeSelect.hidden=true;
const gradeWrapper = wrapper('grades.accepted');
gradeWrapper.classList.add('grade-field');
const tree = node('div','','grade-tree'); gradeWrapper.appendChild(tree);
const gradeChecks = new Map(), parentChecks=[];
function syncGrades() {
  [...gradeSelect.options].forEach(option=>{option.selected=Boolean(gradeChecks.get(option.value)?.checked);});
  parentChecks.forEach(({parent,children})=>{const count=children.filter(child=>child.checked).length;parent.checked=count===children.length;parent.indeterminate=count>0&&count<children.length;});
}
function changed(control) {control.dispatchEvent(new Event('input',{bubbles:true}));}
for (const [title,names] of Object.entries(schema.grade_groups || {})) {
  const group = node('div','','grade-group');
  const head = node('div','','grade-parent');
  const parent = document.createElement('input'); parent.type='checkbox'; parent.setAttribute('aria-label',title+'全选');
  const expand=node('button',title);expand.type='button';expand.setAttribute('aria-expanded',String(['小学','初中'].includes(title)));
  head.appendChild(parent); head.appendChild(expand); group.appendChild(head);
  const childrenHolder=node('div','','grade-children'); childrenHolder.hidden=!['小学','初中'].includes(title);group.appendChild(childrenHolder);
  const children=[];
  for (const name of names) {
    const label=node('label');const checkbox=document.createElement('input');checkbox.type='checkbox';
    checkbox.checked=[...gradeSelect.selectedOptions].some(option=>option.value===name);
    label.appendChild(checkbox);label.appendChild(document.createTextNode(name));childrenHolder.appendChild(label);
    children.push(checkbox);gradeChecks.set(name,checkbox);
    checkbox.addEventListener('change',()=>{syncGrades();changed(gradeSelect);});
  }
  parentChecks.push({parent,children});
  parent.addEventListener('change',()=>{children.forEach(child=>child.checked=parent.checked);syncGrades();changed(gradeSelect);});
  expand.addEventListener('click',()=>{childrenHolder.hidden=!childrenHolder.hidden;expand.setAttribute('aria-expanded',String(!childrenHolder.hidden));});
  tree.appendChild(group);
}
syncGrades();

const policyControl=editor.controls.get('subjects.by_stage').control;
const stages=[['preschool','幼教'],['primary','小学'],['junior','初中'],['senior','高中'],['adult','成人']];
const experience=editor.controls.get('tutor_profile.teaching_experience_levels').control;
experience.hidden=true;
const experienceChecks=node('div','','experience-checks');
wrapper('tutor_profile.teaching_experience_levels').appendChild(experienceChecks);
function renderExperience(){
  experienceChecks.replaceChildren();
  for(const [stage,title] of stages){const label=node('label'),check=document.createElement('input');check.type='checkbox';check.checked=[...experience.selectedOptions].some(option=>option.value===stage);label.appendChild(check);label.appendChild(document.createTextNode(title));experienceChecks.appendChild(label);check.addEventListener('change',()=>{[...experience.options].find(option=>option.value===stage).selected=check.checked;changed(experience);});}
}
renderExperience();
const resume=editor.controls.get('tutor_profile.resume').control;
panels.get('profile').fields.appendChild(wrapper('tutor_profile.resume'));
wrapper('tutor_profile.resume').classList.add('resume-field');
const copyResume=node('button','一键复制简历');copyResume.type='button';
wrapper('tutor_profile.resume').appendChild(copyResume);
wrapper('tutor_profile.resume').appendChild(node('p','可编辑后复制给中介；仅本地保存，不会自动发送。简历文字与筛选条件分别维护。','note'));
copyResume.addEventListener('click',async()=>{
  if(!resume.value.trim()){status.textContent='请先填写简历。';return;}
  try{await navigator.clipboard.writeText(resume.value);status.textContent='已复制简历。';}
  catch{resume.focus();resume.select();try{if(!document.execCommand('copy'))throw new Error();status.textContent='已复制简历。';}catch{status.textContent='已选中简历，请按 Ctrl+C 复制。';}}
});
function ensurePolicies(value) {
  const legacyScience=editor.controls.get('subjects.science_subjects').control.value.split('\n').filter(Boolean);
  const primary=editor.controls.get('subjects.primary_academic_subjects').control.value.split('\n').filter(Boolean);
  for (const [stage] of stages) if (!value[stage] || value[stage].mode==='legacy') value[stage]={mode:'legacy',accepted:stage==='primary' ? [...new Set([...(primary.length?primary:legacyScience),'全科','小学陪伴'])] : legacyScience};
  return value;
}
let policies=ensurePolicies(JSON.parse(policyControl.value || '{}')), activeStage='primary';
policyControl.value=JSON.stringify(policies);
const subjectArea=node('div','','subject-area');subjectArea.appendChild(node('h4','每个学段的可接科目'));
const stageNav=node('nav','','subject-tabs');subjectArea.appendChild(stageNav);
const subjectBody=node('div');subjectArea.appendChild(subjectBody);
panels.get('subjects').panel.appendChild(subjectArea);
const stageButtons=new Map();
for (const [stage,title] of stages) {
  const button=node('button',title);button.type='button';stageNav.appendChild(button);stageButtons.set(stage,button);
  button.addEventListener('click',()=>{activeStage=stage;renderSubjects();});
}
function savePolicy() {policyControl.value=JSON.stringify(policies);changed(policyControl);}
function renderSubjects() {
  stageButtons.forEach((button,stage)=>button.setAttribute('aria-pressed',String(stage===activeStage)));
  subjectBody.replaceChildren();const policy=policies[activeStage];
  const modes=node('div','','subject-modes');
  for (const [mode,title] of [['any','不限科目'],['custom','自选科目']]) {
    const label=node('label');const radio=document.createElement('input');radio.type='radio';radio.name='subject-mode';radio.value=mode;
    radio.checked=mode==='any' ? policy.mode==='any' : policy.mode!=='any';
    radio.addEventListener('change',()=>{policy.mode=mode;savePolicy();renderSubjects();});
    label.appendChild(radio);label.appendChild(document.createTextNode(title));modes.appendChild(label);
  }
  subjectBody.appendChild(modes);
  if (policy.mode==='legacy') subjectBody.appendChild(node('p','当前沿用原规则；编辑该学段后按新选择筛选。','note'));
  const choices=node('div','','subject-choices');
  for (const name of [...new Set([...(schema.subject_choices || []),'全科','小学陪伴',...policy.accepted])]) {
    const label=node('label');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=policy.mode==='any'||policy.accepted.includes(name);checkbox.disabled=policy.mode==='any';
    checkbox.addEventListener('change',()=>{policy.mode='custom';policy.accepted=checkbox.checked ? [...new Set([...policy.accepted,name])] : policy.accepted.filter(value=>value!==name);savePolicy();});
    label.appendChild(checkbox);label.appendChild(document.createTextNode(name));choices.appendChild(label);
  }
  subjectBody.appendChild(choices);
  const custom=node('div','','custom-subject');const input=document.createElement('input');input.type='text';input.maxLength=100;input.placeholder='添加其他科目';input.setAttribute('aria-label','自定义科目');
  const add=node('button','添加');add.type='button';
  function addSubject() {const value=input.value.trim();if(!value)return;policy.mode='custom';policy.accepted=[...new Set([...policy.accepted,value])];savePolicy();renderSubjects();}
  add.addEventListener('click',addSubject);input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addSubject();}});
  custom.appendChild(input);custom.appendChild(add);subjectBody.appendChild(custom);
  subjectBody.appendChild(node('p','未知年级或未识别科目保留待确认；自选科目的组合必须全部符合。','note'));
}
renderSubjects();

const dailyControl=editor.controls.get('availability.daily_start').control;
const intervalControl=editor.controls.get('availability.daily_intervals').control;
wrapper('availability.daily_start').hidden=true;
for(const path of ['availability.weekdays.start','availability.weekdays.days','availability.full_day_weekdays.days','availability.weekends.days'])wrapper(path).hidden=true;
const weekdays=['周一','周二','周三','周四','周五','周六','周日'];
function legacyDaily() {
  const values=editor.collect(), full=[...values['availability.full_day_weekdays.days'],...values['availability.weekends.days']];
  return Object.fromEntries(weekdays.map((_,index)=>[String(index+1),full.includes(index+1)?'all':values['availability.weekdays.days'].includes(index+1)?values['availability.weekdays.start']:'off']));
}
let daily={...legacyDaily(),...JSON.parse(dailyControl.value)};
function normalizeIntervals(value){for(const ranges of Object.values(value)){for(const pair of ranges)for(let i=0;i<2;i++)if(/^\d{1,2}:\d{2}$/.test(pair[i]))pair[i]=pair[i].padStart(5,'0');ranges.sort((a,b)=>(a[0]||'99:99').localeCompare(b[0]||'99:99'));}return value;}
function effectiveIntervals(){const legacy={...legacyDaily(),...JSON.parse(dailyControl.value)};return normalizeIntervals({...Object.fromEntries(Object.entries(legacy).map(([day,value])=>[day,value==='off'?[]:[[value==='all'?'00:00':value,'24:00']]])),...JSON.parse(intervalControl.value)});}
let intervals=effectiveIntervals();
const dailyHolder=node('div','','daily-grid');wrapper('availability.daily_intervals').appendChild(dailyHolder);wrapper('availability.daily_intervals').classList.add('daily-field');
wrapper('availability.daily_intervals').appendChild(node('p','可添加多个区间；留空表示当天不可上课。结束可填 24:00；跨午夜请拆到两天。','note'));
function saveIntervals(){
  const complete=pair=>pair.every(value=>/^\d{2}:\d{2}$/.test(value))&&pair[0]<pair[1];
  for(const ranges of Object.values(intervals))ranges.sort((a,b)=>Number(complete(b))-Number(complete(a))||a[0].localeCompare(b[0]));
  intervalControl.value=JSON.stringify(intervals);if(editor.validIntervals(intervals))changed(intervalControl);
}
const intervalDeleteIcon='<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><path d="M519.620465 0c-103.924093 0-188.511256 82.467721-192.083349 185.820279H85.015814A48.91386 48.91386 0 0 0 36.101953 234.686512a48.91386 48.91386 0 0 0 48.913861 48.866232h54.010046V831.345116c0 102.852465 69.822512 186.844279 155.909954 186.844279h439.200744c86.087442 0 155.909953-83.491721 155.909954-186.844279V284.100465h48.91386a48.91386 48.91386 0 0 0 48.913861-48.890046 48.91386 48.91386 0 0 0-48.913861-48.866233h-227.756651A191.559442 191.559442 0 0 0 519.620465 0z m-107.234232 177.080558c3.548279-49.771163 46.627721-88.540279 99.851907-88.540279 53.224186 0 96.327442 38.745302 99.351813 88.540279h-199.20372z m-111.997024 752.044651c-30.981953 0-65.083535-39.15014-65.083535-95.041488V287.744h575.488v546.839814c0 55.915163-34.077767 95.041488-65.059721 95.041488H300.389209v-0.500093z" fill="#D81E06"></path><path d="M368.116093 796.814884c24.361674 0 44.27014-21.670698 44.27014-48.818605v-278.623256c0-27.147907-19.908465-48.818605-44.27014-48.818604-24.33786 0-44.27014 21.670698-44.27014 48.818604v278.623256c0 27.147907 19.360744 48.818605 44.293954 48.818605z m154.933581 0c24.361674 0 44.293953-21.670698 44.293954-48.818605v-278.623256c0-27.147907-19.932279-48.818605-44.293954-48.818604-24.33786 0-44.27014 21.670698-44.270139 48.818604v278.623256c0 27.147907 19.932279 48.818605 44.293953 48.818605z m132.810419 0c24.33786 0 44.27014-21.670698 44.27014-48.818605v-278.623256c0-27.147907-19.932279-48.818605-44.27014-48.818604s-44.27014 21.670698-44.27014 48.818604v278.623256c0 27.147907 19.360744 48.818605 44.27014 48.818605z" fill="#D81E06"></path></svg>';
function renderDaily() {
  dailyHolder.replaceChildren();
  weekdays.forEach((day,index)=>{
    const key=String(index+1),ranges=intervals[key],row=node('div','','interval-day');row.appendChild(node('strong',day));
    const list=node('div','','interval-list');row.appendChild(list);
    if(!ranges.length)list.appendChild(node('span','不可上课','note'));
    ranges.forEach((pair,rangeIndex)=>{
      const entry=node('div','','interval-entry');
      for(let side=0;side<2;side++){
        if(side)entry.appendChild(node('span','至'));
        const picker=node('div','','interval-clock'),hour=document.createElement('select'),minute=document.createElement('select');
        const label=day+'区间'+(rangeIndex+1)+(side?'结束':'开始');hour.setAttribute('aria-label',label+'小时');minute.setAttribute('aria-label',label+'分钟');
        const parts=pair[side].split(':');
        for(const [control,count,value] of [[hour,side?25:24,parts[0]],[minute,60,parts[1]]]){const blank=node('option','--');blank.value='';control.appendChild(blank);for(let n=0;n<count;n++){const option=node('option',String(n).padStart(2,'0'));option.value=String(n).padStart(2,'0');control.appendChild(option);}control.value=value || '';}
        minute.disabled=hour.value==='24';
        function selectTime(){if(hour.value==='24'){minute.value='00';}else if(hour.value && !minute.value){minute.value='00';}pair[side]=hour.value||minute.value?hour.value+':'+minute.value:'';saveIntervals();renderDaily();}
        hour.addEventListener('change',selectTime);minute.addEventListener('change',selectTime);picker.appendChild(hour);picker.appendChild(node('span',':'));picker.appendChild(minute);entry.appendChild(picker);
      }
      const remove=node('button','','interval-delete');remove.type='button';remove.innerHTML=intervalDeleteIcon;remove.setAttribute('aria-label','删除'+day+'区间'+(rangeIndex+1));remove.setAttribute('title','删除此区间');remove.addEventListener('click',()=>{ranges.splice(rangeIndex,1);saveIntervals();renderDaily();});entry.appendChild(remove);list.appendChild(entry);
    });
    if(!editor.validIntervals({[key]:ranges}))list.appendChild(node('p',ranges.some(pair=>pair.some(value=>!/^\d{2}:\d{2}$/.test(value)))?'请补全新区间的时间。':'区间不能重叠，结束须晚于开始。','interval-error'));
    const add=node('button','添加区间');add.type='button';add.disabled=ranges.length>=20;
    add.addEventListener('click',()=>{ranges.push(['','']);intervalControl.value=JSON.stringify(intervals);renderDaily();});row.appendChild(add);dailyHolder.appendChild(row);
  });
}
renderDaily();

// Tag editors mirror the original string control; they use the same save path.
for (const [path,title] of [['preferred_address_keywords','优先地点'],['location_blacklist','位置黑名单']]) {
  const {control}=editor.controls.get(path);const field=wrapper(path);field.classList.add('tag-field');field.querySelector('span').textContent=title;control.hidden=true;
  const chips=node('div','','place-tags'),input=document.createElement('input'),add=node('button','添加');add.type='button';input.type='text';input.maxLength=100;input.placeholder='添加'+title;input.setAttribute('aria-label','添加'+title);
  const entry=node('div','','tag-entry');entry.appendChild(input);entry.appendChild(add);field.appendChild(chips);field.appendChild(entry);
  function renderTags(){chips.replaceChildren();for(const value of control.value.split('\n').filter(Boolean)){const button=node('button',value+' ×');button.type='button';button.setAttribute('aria-label','移除'+value);button.addEventListener('click',()=>{control.value=control.value.split('\n').filter(item=>item!==value).join('\n');changed(control);renderTags();});chips.appendChild(button);}}
  add.addEventListener('click',()=>{const value=input.value.trim();if(!value)return;control.value=[...new Set([...control.value.split('\n').filter(Boolean),value])].join('\n');input.value='';changed(control);renderTags();});
  control.addEventListener('input',renderTags);renderTags();
}
panels.get('location').panel.appendChild(node('p','公共交通含步行与换乘。线上订单自动识别，无需通勤。地点变更在下次运行时定位核实。','note'));
const locationPanel=panels.get('location');
const places=node('div','','settings-fields address-preferences');
places.appendChild(wrapper('preferred_address_keywords'));places.appendChild(wrapper('location_blacklist'));
locationPanel.panel.insertBefore(node('h4','地址偏好'),locationPanel.fields);locationPanel.panel.insertBefore(places,locationPanel.fields);
locationPanel.panel.insertBefore(node('h4','通勤设置'),locationPanel.fields);
for(const path of ['commute.city','commute.origin','commute.maximum_one_way_minutes'])locationPanel.fields.appendChild(wrapper(path));
locationPanel.fields.appendChild(node('p','交通方式：公共交通（含步行与换乘）','note'));

const toolbar=node('div','','settings-document-tools');
document.getElementById('back-report')?.remove();
const templateButton=node('button','下载模板'),importButton=node('button','导入模板'),exportButton=node('button','导出用户设置');templateButton.type=importButton.type=exportButton.type='button';
toolbar.appendChild(templateButton);toolbar.appendChild(importButton);toolbar.appendChild(exportButton);
const settingsHeader=node('div','','settings-header');section.insertBefore(settingsHeader,tabs);settingsHeader.appendChild(tabs);settingsHeader.appendChild(toolbar);
const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='.md,.json,.txt';fileInput.hidden=true;section.appendChild(fileInput);
importButton.addEventListener('click',()=>fileInput.click());
const dialog=document.createElement('dialog');dialog.className='settings-import-dialog';dialog.appendChild(node('h3','导入变更预览'));
const changes=node('div');dialog.appendChild(changes);
dialog.appendChild(node('p','只应用所列偏好，不导入熄单、学习规则、密钥或运行计划。应用后仍需保存更改。','note'));
const applyButton=node('button','应用这些变更'),cancel=node('button','取消');applyButton.type=cancel.type='button';dialog.appendChild(applyButton);dialog.appendChild(cancel);section.appendChild(dialog);
let incoming={};cancel.addEventListener('click',()=>dialog.close());
function importValues(values) {
  if (!values || typeof values!=='object' || Array.isArray(values)) throw new Error('文档格式不正确');
  const unknown=Object.keys(values).filter(path=>!editor.controls.has(path));if(unknown.length)throw new Error('文档包含不支持的设置：'+unknown.join('、'));
  for(const [path,value] of Object.entries(values)){
    const {kind,control,label}=editor.controls.get(path);
    const arrayKind=['strings','multi','days'].includes(kind);
    let valid=arrayKind?Array.isArray(value):kind==='number'?typeof value==='number'&&Number.isFinite(value):kind==='boolean'?typeof value==='boolean':kind==='tier'?value===null||typeof value==='boolean':['policy','daily','intervals'].includes(kind)?value!==null&&typeof value==='object'&&!Array.isArray(value):typeof value==='string';
    if(valid&&kind==='select')valid=[...control.options].some(option=>option.value===value);
    if(valid&&kind==='multi')valid=value.every(item=>typeof item==='string'&&[...control.options].some(option=>option.value===item));
    if(valid&&kind==='days')valid=value.every(day=>Number.isInteger(day)&&day>=1&&day<=7);
    if(valid&&kind==='strings')valid=value.every(item=>typeof item==='string'&&item.length>0&&item.length<=100);
    if(!valid)throw new Error('文档中的值不正确：'+label);
  }
  const current=editor.collect(), originalBaseline={...editor.baseline};
  const importedDaily=values['availability.daily_start'];
  if (values['subjects.by_stage']) values={...values,'subjects.by_stage':{...current['subjects.by_stage'],...values['subjects.by_stage']}};
  if (values['availability.daily_start']) values={...values,'availability.daily_start':{...daily,...values['availability.daily_start']}};
  if(typeof intervals!=='undefined' && (values['availability.daily_intervals'] || importedDaily)){
    const requested=Object.fromEntries(Object.entries(importedDaily || {}).map(([day,value])=>[day,value==='off'?[]:[[value==='all'?'00:00':value,'24:00']]]));
    values={...values,'availability.daily_intervals':{...intervals,...requested,...values['availability.daily_intervals']}};
  }
  try {editor.updateBaseline(values);const normalized=editor.collect();values=Object.fromEntries(Object.keys(values).map(path=>[path,normalized[path]]));}
  finally {editor.updateBaseline(current);Object.keys(editor.baseline).forEach(key=>delete editor.baseline[key]);Object.assign(editor.baseline,originalBaseline);}
  incoming=Object.fromEntries(Object.entries(values).filter(([path,value])=>JSON.stringify(current[path])!==JSON.stringify(value)));
  changes.replaceChildren();
  if(importWarnings.length)changes.appendChild(node('p','以下旧文档项目未导入，保留当前值：'+importWarnings.join('、'),'note'));
  for(const [path,value] of Object.entries(incoming)) {const label=editor.controls.get(path).label;changes.appendChild(node('p',label+'：'+JSON.stringify(current[path])+' → '+JSON.stringify(value)));}
  if(!Object.keys(incoming).length){status.textContent='导入内容与当前设置一致。';return;}
  dialog.showModal();
}
let importWarnings=[];
function parseLegacy(text) {
  const decode=value=>value.replace(/&#124;/g,'|').replace(/<br>/g,'\n').replace(/&amp;/g,'&');
  const cells=new Map();for(const line of text.split('\n')){const match=line.match(/^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|/);if(match&&!/未填|默认/.test(match[2])&&!/^项目$|^---/.test(match[1].trim()))cells.set(match[1].replace(/（.*?）/g,'').trim(),decode(match[2].trim()));}
  const values={};
  const mappings={'学校全称':'tutor_profile.university','在读阶段':'tutor_profile.academic_stage','城市':'commute.city','出发地点':'commute.origin','最低时薪':'pay.minimum_hourly_cny','最长单程分钟数':'commute.maximum_one_way_minutes','地址优先关键词':'preferred_address_keywords','学校常用简称':'tutor_profile.university_aliases'};
  for(const [label,path] of Object.entries(mappings))if(cells.has(label)){const value=cells.get(label);values[path]=path.includes('minimum_hourly')||path.includes('maximum_one_way') ? Number(value.match(/[\d.]+/)?.[0]) : ['preferred_address_keywords','tutor_profile.university_aliases'].includes(path) ? value.split(/[、,，;；]/).map(v=>v.trim()).filter(Boolean) : value;}
  if(cells.has('性别'))values['tutor_profile.gender']=cells.get('性别')==='男'?'male':cells.get('性别')==='女'?'female':cells.get('性别');
  const range=cells.get('学生年级范围');if(range){
    const names=Object.values(schema.grade_groups).flat(),aliases=new Map(names.map(name=>[name,name]));
    for(const name of names){const match=name.match(/^(小学|初中|高中)([一二三四五六])年级$/);if(match)aliases.set((match[1]==='小学'?'小':match[1]==='初中'?'初':'高')+match[2],name);}
    const selected=[];
    for(const part of range.split(/[、,，;；\s]+/).filter(Boolean)){
      if(aliases.has(part)){selected.push(aliases.get(part));continue;}
      const group=part.replace(/全部|全选|都接受/g,'');if(schema.grade_groups[group]&&group!=='成人'){selected.push(...schema.grade_groups[group]);continue;}
      const endpoints=part.split(/至|到|~|～|—|-/);if(endpoints.length===2&&endpoints.every(item=>aliases.has(item))){const a=names.indexOf(aliases.get(endpoints[0])),b=names.indexOf(aliases.get(endpoints[1]));if(a<=b){selected.push(...names.slice(a,b+1));continue;}}
      throw new Error('文档的年级范围无法安全识别：'+part+'。请使用导出的完整年级名称。');
    }
    values['grades.accepted']=[...new Set(selected)];
  }
  const used=new Set(Object.keys(mappings).filter(label=>cells.has(label)));if(cells.has('性别'))used.add('性别');if(range)used.add('学生年级范围');
  // The exported human-readable table uses labels, not code paths.
  for(const [path,{kind,label}] of editor.controls){const key=label.replace(/（.*?）/g,'').trim();if(!cells.has(key)||kind==='policy')continue;used.add(key);const raw=cells.get(key);let value=raw;
    if(kind==='number')value=Number(raw);
    else if(kind==='boolean')value=['是','开启'].includes(raw)?true:['否','关闭'].includes(raw)?false:raw;
    else if(kind==='tier')value=raw==='未提供'?null:raw==='是'?true:raw==='否'?false:raw;
    else if(kind==='days')value=raw==='无'?[]:raw.split(/[、,，\s]+/).filter(Boolean).map(day=>['周一','周二','周三','周四','周五','周六','周日'].indexOf(day)+1);
    else if(kind==='strings'||kind==='multi')value=raw==='无'?[]:raw.split(/[、,，;；\n]+/).map(item=>item.trim()).filter(Boolean);
    if(path==='tutor_profile.gender')value=raw==='男'?'male':raw==='女'?'female':raw;
    if(path==='tutor_profile.teaching_experience_levels')value=value.map(name=>stages.find(([,label])=>label===name)?.[0] || name);
    if(path==='pay.range_crossing_minimum')value=raw==='上限达到最低时薪即可'?'accept_if_maximum_meets_minimum':raw==='下限不足时待确认'?'needs_confirmation':raw;
    if(path==='availability.unspecified_class_time')value=raw==='按可协商通过'?'accept_as_negotiable':raw==='待确认'?'needs_confirmation':raw;
    if(path==='message_window_days')value=raw.replace(/^过去([1357])天$/,'$1');
    values[path]=value;
  }
  for(const [stage,title] of stages){const key=cells.has(title+'可接科目')?title+'可接科目':title+'科目';if(!cells.has(key))continue;used.add(key);const raw=cells.get(key);const mode=/^(?:不限科目|全部科目|都接受)$/.test(raw)?'any':raw.startsWith('沿用原规则')?'legacy':'custom';values['subjects.by_stage'] ||= {};values['subjects.by_stage'][stage]={mode,accepted:mode==='any'?[]:raw.replace(/^沿用原规则[:：]?/,'').split(/[、,，;；\n]+/).map(item=>item.trim()).filter(Boolean)};}
  weekdays.forEach((day,index)=>{const key=cells.has(day+'可上课时间')?day+'可上课时间':day;if(!cells.has(key))return;const raw=cells.get(key);const start=raw==='全天'?'all':raw==='不可上课'?'off':/^(?:[01]\d|2[0-3]):[0-5]\d之后$/.test(raw)?raw.slice(0,5):null;
    if(start!==null){used.add(key);values['availability.daily_start']||={};values['availability.daily_start'][String(index+1)]=start;}
    else {const ranges=raw.split(/[、,，;；]+/).map(value=>value.trim().split(/\s*[-–—~～至到]\s*/));if(ranges.every(pair=>pair.length===2&&pair.every(t=>/^\d{2}:\d{2}$/.test(t)))){used.add(key);values['availability.daily_intervals']||={};values['availability.daily_intervals'][String(index+1)]=ranges;}}
  });
  if(values['tutor_profile.academic_stage']){const aliases={研一:'master_1',研二:'master_2',研三:'master_3',大一:'undergraduate_1',大二:'undergraduate_2',大三:'undergraduate_3',大四:'undergraduate_4'};values['tutor_profile.academic_stage']=aliases[values['tutor_profile.academic_stage']]||values['tutor_profile.academic_stage'];}
  if(!Object.keys(values).length)throw new Error('未找到可安全导入的设置。请点击“下载模板”，填写后再导入。');
  // A free-form document has unsupported fields: never silently treat a partial parse as complete.
  importWarnings=[...cells.keys()].filter(key=>!used.has(key));
  return values;
}
fileInput.addEventListener('change',async()=>{
  try {importWarnings=[];const file=fileInput.files[0];if(!file)return;if(file.size>200000)throw new Error('文档过大');const content=await file.text();let payload;
    const block=content.match(/```json\s*([\s\S]*?)```/i);
    if(block)payload=JSON.parse(block[1]);else if(content.trim().startsWith('{'))payload=JSON.parse(content);else {importValues(parseLegacy(content));return;}
    importValues(payload.preferences || payload.preference_overrides || payload);
  }catch(error){status.textContent=error.userMessage || error.message || '导入失败，现有设置未改动。';}finally{fileInput.value='';}
});
applyButton.addEventListener('click',()=>{
  editor.updateBaseline(incoming);
  for(const path of Object.keys(incoming))if(!window.tutorUserState.edited_preference_paths.includes(path))window.tutorUserState.edited_preference_paths.push(path);
  // updateBaseline normally commits a successful file save; importing must retain the old conflict baseline.
  Object.assign(editor.baseline, conflictBaseline);
  for(const [name,checkbox] of gradeChecks)checkbox.checked=[...gradeSelect.selectedOptions].some(option=>option.value===name);
  syncGrades();policies=ensurePolicies(JSON.parse(policyControl.value));policyControl.value=JSON.stringify(policies);renderSubjects();
  daily={...legacyDaily(),...JSON.parse(dailyControl.value)};intervals=effectiveIntervals();renderDaily();renderExperience();
  editor.controls.forEach(({control,kind})=>{if(kind==='strings')control.dispatchEvent(new Event('input'));});
  window.tutorUserState.preference_overrides=editor.collect();
  try{localStorage.setItem('wechat-tutor-filter.feedback.v1',JSON.stringify(window.tutorUserState));}catch{}
  document.dispatchEvent(new CustomEvent('tutor-settings-draft-changed'));dialog.close();status.textContent='已应用导入变更；点击保存更改，下次筛选生效。';
});
let conflictBaseline={...editor.baseline};
document.addEventListener('tutor-settings-saved',()=>{
  conflictBaseline={...editor.baseline};
  for(const [name,checkbox] of gradeChecks)checkbox.checked=[...gradeSelect.selectedOptions].some(option=>option.value===name);
  syncGrades();
  editor.controls.forEach(({control,kind})=>{if(kind==='strings')control.dispatchEvent(new Event('input'));});
  policies=ensurePolicies(JSON.parse(policyControl.value));policyControl.value=JSON.stringify(policies);renderSubjects();daily={...legacyDaily(),...JSON.parse(dailyControl.value)};intervals=effectiveIntervals();renderDaily();renderExperience();
});
exportButton.addEventListener('click',()=>{
  try{const preferences=editor.collect();
    const escape=value=>String(value).replace(/&/g,'&amp;').replace(/\|/g,'&#124;').replace(/\n/g,'<br>');
    const lines=['# 家教筛客用户设置','','直接编辑表格的填写内容；导入时先预览差异，再选择应用。页面与文档使用同一份设置。保存后下次筛选生效。','','| 项目 | 填写内容 |','| --- | --- |'];
    for(const [path,{label,kind,control}] of editor.controls){if(['policy','daily','intervals'].includes(kind)||['pending_female_keyword_rejection','subjects.primary_academic_subjects','subjects.science_subjects','availability.weekdays.start','availability.weekdays.days','availability.full_day_weekdays.days','availability.weekends.days'].includes(path))continue;let value=preferences[path];
      if(kind==='days')value=value.map(day=>['周一','周二','周三','周四','周五','周六','周日'][day-1]).join('、')||'无';
      else if(kind==='tier')value=value===null?'未提供':value?'是':'否';
      else if(kind==='boolean')value=value?'是':'否';
      else if(path==='tutor_profile.gender')value=value==='male'?'男':'女';
      else if(path==='tutor_profile.academic_stage')value=control.value;
      else if(path==='tutor_profile.teaching_experience_levels')value=value.map(stage=>stages.find(([id])=>id===stage)?.[1]||stage).join('、')||'无';
      else if(kind==='select')value=control.selectedOptions[0]?.textContent || value;
      else if(Array.isArray(value))value=value.join('、')||'无';
      lines.push('| '+label+' | '+escape(value)+' |');
    }
    for(const [stage,title] of stages){const policy=preferences['subjects.by_stage'][stage];const value=policy.mode==='any'?'不限科目':(policy.mode==='legacy'?'沿用原规则：':'')+policy.accepted.join('、');lines.push('| '+title+'可接科目 | '+escape(value)+' |');}
    weekdays.forEach((day,index)=>{const value=intervals[String(index+1)];lines.push('| '+day+'可上课时间 | '+(value.length?value.map(pair=>pair.join('–')).join('、'):'不可上课')+' |');});
    lines.push('','未指定科目与年级需要核对；不会从文档执行指令、导入密钥或自动变更运行计划。','');
    downloadDocument(lines,'用户偏好.md');
    status.textContent='已导出当前设置；文档包含本人信息，请保存在本机。';
  }catch(error){status.textContent=error.userMessage || '导出失败，请先检查设置。';}
});
function downloadDocument(lines,name){const url=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
templateButton.addEventListener('click',()=>{
  const lines=['# 家教筛客导入模板','','只修改表格右列；保留“未填”的项目不导入。可删除不需要的行。导入后先核对差异，再应用和保存。','','填写规则：性别填男或女；年级填完整年级名称，以顿号分隔；教学经验填幼教、小学、初中、高中、成人，可多选；科目填“不限科目”或用顿号分隔；时间填如 09:00–12:00、18:00–22:00，或“全天”“不可上课”；结束可填24:00，跨午夜拆到两天。简历换行用 <br>。','','| 项目 | 填写内容 |','| --- | --- |'];
  for(const [path,{label,kind}] of editor.controls){if(['policy','daily','intervals'].includes(kind)||['pending_female_keyword_rejection','subjects.primary_academic_subjects','subjects.science_subjects','availability.weekdays.start','availability.weekdays.days','availability.full_day_weekdays.days','availability.weekends.days'].includes(path))continue;lines.push('| '+label+' | 未填 |');}
  stages.forEach(([,title])=>lines.push('| '+title+'可接科目 | 未填 |'));weekdays.forEach(day=>lines.push('| '+day+'可上课时间 | 未填 |'));
  downloadDocument(lines,'家教筛客导入模板.md');status.textContent='已下载空白导入模板，填写后点击导入。';
});
form.addEventListener('submit',event=>event.preventDefault());
show('profile');
})();
