(() => {
const form = document.getElementById('preference-form');
if (!form) return;
const state = window.tutorUserState;
let baseline = {};
try { baseline = JSON.parse(document.getElementById('preference-data').textContent); } catch {}
baseline = {...baseline, ...(state.saved_preference_baseline || {})};
const values = {message_window_days:'7',...baseline, ...state.preference_overrides};
const specs = [
  ['message_window_days','消息时间范围','select',[['1','过去1天'],['3','过去3天'],['5','过去5天'],['7','过去7天']]],
  ['pay.minimum_hourly_cny', '最低时薪（元/小时）', 'number'],
  ['pay.range_crossing_minimum', '报价区间规则', 'select', [['accept_if_maximum_meets_minimum', '上限达到最低时薪即可'], ['needs_confirmation', '下限不足时待确认']]],
  ['commute.maximum_one_way_minutes', '最长单程公共交通（分钟）', 'number'],
  ['commute.city', '城市', 'text'],
  ['commute.origin', '出发地点', 'text'],
  ['preferred_address_keywords', '地址优先关键词（每行一个）', 'strings'],
  ['location_blacklist', '位置黑名单（每行一个）', 'strings'],
  ['subjects.primary_academic_subjects', '小学文化课科目（每行一个）', 'strings'],
  ['subjects.science_subjects', '原规则科目（兼容已有配置）', 'strings'],
  ['subjects.by_stage', '分学段科目', 'policy'],
  ['grades.accepted', '可接学生年级', 'multi', ['幼儿园小班', '幼儿园中班', '幼儿园大班', '学前班', ...'一二三四五六'.split('').map(char => '小学' + char + '年级'), ...'一二三'.split('').map(char => '初中' + char + '年级'), ...'一二三'.split('').map(char => '高中' + char + '年级'), '大学', '成人']],
  ['pending_female_keyword_rejection', '开启待确认原文“女”且无“男”直接排除', 'boolean'],
  ['availability.unspecified_class_time', '未指定具体上课时间', 'select', [['accept_as_negotiable', '按可协商通过'], ['needs_confirmation', '待确认']]],
  ['availability.weekdays.start', '受限上课日的最早开始时间', 'time'],
  ['availability.daily_start', '逐日可上课时间', 'daily'],
  ['availability.daily_intervals', '逐日可上课时间区间', 'intervals'],
  ['availability.weekdays.days', '仅最早开始时间之后可上课的星期', 'days'],
  ['availability.full_day_weekdays.days', '全天可上课的工作日', 'days'],
  ['availability.weekends.days', '全天可上课的周末日', 'days'],
  ['tutor_profile.gender', '本人性别', 'select', [['male', '男'], ['female', '女']]],
  ['tutor_profile.resume', '用户简历', 'resume'],
  ['tutor_profile.academic_stage', '本人在读阶段', 'text'],
  ['tutor_profile.university', '学校全称', 'text'],
  ['tutor_profile.university_aliases', '学校简称（每行一个）', 'strings'],
  ['tutor_profile.teaching_experience_levels', '已有教学经验阶段', 'multi', [['preschool', '幼教'], ['primary', '小学'], ['junior', '初中'], ['senior', '高中'], ['adult', '成人']]],
  ['tutor_profile.university_tiers.211', '学校是否211', 'tier'],
  ['tutor_profile.university_tiers.985', '学校是否985', 'tier']
];
const controls = new Map();
const academicStages = {master_1:'研一',master_2:'研二',master_3:'研三',undergraduate_1:'大一',undergraduate_2:'大二',undergraduate_3:'大三',undergraduate_4:'大四'};
const holder = document.getElementById('preference-fields');
for (const [path, label, kind, options] of specs) {
  const wrapper = document.createElement(['multi','days','intervals','resume'].includes(kind) ? 'div' : 'label');
  wrapper.className = 'preference-field';
  const title = document.createElement('span'); title.textContent = label; wrapper.appendChild(title);
  let control;
  if (kind === 'days') {
    control = document.createElement('div'); control.className = 'day-options';
    const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    weekdays.forEach((name, index) => {
      const option = document.createElement('label'); const checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.value = index + 1; checkbox.checked = (values[path] || []).includes(index + 1);
      option.appendChild(checkbox); option.appendChild(document.createTextNode(name)); control.appendChild(option);
    });
  } else if (['select', 'multi', 'tier'].includes(kind)) {
    control = document.createElement('select');
    control.multiple = kind === 'multi';
    const choices = kind === 'tier' ? [['', '未提供'], ['true', '是'], ['false', '否']] : options;
    for (const entry of choices) {
      const [value, name] = Array.isArray(entry) ? entry : [entry, entry];
      const option = document.createElement('option'); option.value = value; option.textContent = name;
      option.selected = kind === 'multi' ? (values[path] || []).includes(value) : String(values[path] ?? '') === value;
      control.appendChild(option);
    }
  } else {
    control = document.createElement(['strings','resume'].includes(kind) ? 'textarea' : 'input');
    if (kind === 'strings') control.value = (values[path] || []).join('\n');
    else if (['policy','daily','intervals'].includes(kind)) {control.type = 'hidden'; control.value = JSON.stringify(values[path] || {});}
    else if (kind === 'resume') {control.value=values[path] || '';control.maxLength=20000;}
    else if (kind === 'boolean') {control.type = 'checkbox'; control.checked = Boolean(values[path]);}
    else {control.type = kind; control.value = values[path] ?? '';}
    if (kind === 'number') {control.min = 1; control.max = 10000; control.step = 'any';}
    if (kind === 'text') {control.maxLength = 100; control.required = true;}
  }
  if (path === 'tutor_profile.academic_stage') control.value = academicStages[control.value] || control.value;
  control.dataset.path = path; wrapper.appendChild(control); holder.appendChild(wrapper);
  if (kind === 'resume') control.setAttribute('aria-label',label);
  controls.set(path, {control, kind, label});
}
function collect() {
  const result = {};
  for (const [path, {control, kind, label}] of controls) {
    let value;
    if (['policy','daily','intervals'].includes(kind)) value = JSON.parse(control.value);
    else if (kind === 'boolean') value = control.checked;
    else if (kind === 'days') value = [...control.querySelectorAll('input:checked')].map(input => Number(input.value));
    else if (kind === 'multi') value = [...control.selectedOptions].map(option => option.value);
    else if (kind === 'tier') value = control.value ? control.value === 'true' : null;
    else if (kind === 'strings') value = [...new Set(control.value.split(/[\n,，、;；]+/).map(text => text.trim()).filter(Boolean))];
    else if (kind === 'number') value = Number(control.value);
    else value = control.value.trim();
    let valid = true;
    if (kind === 'number') valid = Number.isFinite(value) && value > 0 && value <= 10000;
    if (kind === 'time') valid = /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
    if (kind === 'select') valid = [...control.options].some(option=>option.value===value);
    if (kind === 'daily') valid = value && !Array.isArray(value) && typeof value==='object' && Object.entries(value).every(([day,start])=>/^[1-7]$/.test(day) && (['all','off'].includes(start) || /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(start)));
    if (kind === 'intervals') valid = validIntervals(value);
    if (kind === 'resume') valid = value.length <= 20000;
    if (kind === 'text') valid = value.length > 0 && value.length <= 100;
    if (path === 'commute.city') valid = typeof value === 'string' && /^[\u4e00-\u9fffA-Za-z0-9\s]{1,100}$/.test(value) && Boolean(value.trim());
    if (path === 'commute.origin') valid = typeof value === 'string' && value.length<=100 && !/https?:\/\/|www\./i.test(value) && /大学|学院|学校|医院|站|小区|社区|公园|商场|大厦|家园|花园|公寓|广场|路|街|胡同|园|村|苑|湾|府|庭|阁/.test(value);
    if (kind === 'policy') valid = value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).every(stage => ['preschool','primary','junior','senior','adult'].includes(stage)) && Object.values(value).every(policy => policy && Object.keys(policy).length===2 && Object.keys(policy).every(key=>['mode','accepted'].includes(key)) && ['legacy','any','custom'].includes(policy.mode) && Array.isArray(policy.accepted) && policy.accepted.length <= 100 && policy.accepted.every(subject => typeof subject === 'string' && subject.length > 0 && subject.length <= 100) && (policy.mode !== 'custom' || policy.accepted.length > 0));
    if (kind === 'strings') valid = value.length <= 100 && value.every(text => text.length <= 100);
    if (path === 'grades.accepted') valid = value.length > 0;
    if (!valid) {const error = new Error('Invalid preference'); error.userMessage = '请检查：' + label; control.focus(); throw error;}
    if (path === 'tutor_profile.academic_stage') value = Object.keys(academicStages).find(key=>academicStages[key]===value) || value;
    result[path] = value;
  }
  const restricted = result['availability.weekdays.days'];
  const full = [...result['availability.full_day_weekdays.days'], ...result['availability.weekends.days']];
  if (restricted.some(day => full.includes(day))) {const error = new Error('Overlapping days'); error.userMessage = '同一天不能同时选择“全天”与“仅指定时间之后”。'; throw error;}
  return result;
}
function updateBaseline(overrides) {
  Object.assign(baseline, overrides);
  for (const [path, {control, kind}] of controls) {
    if (!Object.hasOwn(overrides, path)) continue;
    const value = overrides[path];
    if (kind === 'days') control.querySelectorAll('input').forEach(input => {input.checked = value.includes(Number(input.value));});
    else if (kind === 'multi') [...control.options].forEach(option => {option.selected = value.includes(option.value);});
    else if (kind === 'boolean') control.checked = value;
    else if (kind === 'strings') control.value = value.join('\n');
    else if (['policy','daily','intervals'].includes(kind)) control.value = JSON.stringify(value);
    else control.value = value ?? '';
    if (path === 'tutor_profile.academic_stage') control.value = academicStages[control.value] || control.value;
  }
}
function validIntervals(value) {
  return value && typeof value==='object' && !Array.isArray(value) && Object.entries(value).every(([day,ranges])=>{
    let end='';
    return /^[1-7]$/.test(day) && Array.isArray(ranges) && ranges.length<=20 && ranges.every(pair=>{
      const valid=Array.isArray(pair)&&pair.length===2&&pair.every(t=>typeof t==='string')&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(pair[0])&&/^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$/.test(pair[1])&&pair[0]<pair[1]&&pair[0]>=end;
      end=pair?.[1];return valid;
    });
  });
}
window.tutorPreferenceEditor = {collect, baseline, updateBaseline, controls, validIntervals};
function persist() {try {localStorage.setItem('wechat-tutor-filter.feedback.v1', JSON.stringify(state));} catch {}}
form.addEventListener('input', event => {
  const path = event.target.closest('[data-path]')?.dataset.path;
  if (path && !state.edited_preference_paths.includes(path)) state.edited_preference_paths.push(path);
  try {state.preference_overrides = collect(); persist(); document.getElementById('close-feedback').textContent = '偏好已编辑，点击右上角“保存更改”写回项目文件，下次筛选生效。';}
  catch (error) {document.getElementById('close-feedback').textContent = error.userMessage;}
});
function renderRules() {
  const holder = document.getElementById('learned-rules'); holder.replaceChildren();
  if (!state.rejection_feedback.length) {holder.textContent = '暂无学习规则。'; return;}
  const unique = new Map();
  state.rejection_feedback.filter(item=>item.field!=='order').forEach(item => {const key = item.field + '\0' + item.value; if (!unique.has(key)) unique.set(key, item);});
  for (const [key, item] of unique) {
    const row = document.createElement('div'); row.className = 'learned-rule';
    const text = document.createElement('span'); text.textContent = item.reason + '：' + item.value;
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '删除规则';
    remove.addEventListener('click', () => {
      state.deleted_feedback_rules.push({field: item.field, value: item.value});
      state.rejection_feedback = state.rejection_feedback.filter(value => value.field + '\0' + value.value !== key);
      persist(); renderRules(); document.getElementById('close-feedback').textContent = '规则已移除，点击保存后下次筛选生效。';
    });
    row.appendChild(text); row.appendChild(remove); holder.appendChild(row);
  }
}
renderRules();
document.addEventListener('tutor-order-closed', renderRules);
document.addEventListener('tutor-settings-saved', renderRules);
function view() {
  const active = location.hash === '#preferences';
  document.body.classList.toggle('preferences-view', active);
}
window.addEventListener('hashchange', view);
view();
})();
