const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync('tutor-report.html', 'utf8');
const script = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/)[1];
const core = script.split('/* Shortlist */')[0].replace(/\}\)\(\);\s*$/, 'globalThis.testMerge = mergeSavedSettings;})();');
const storage = new Map();
const seed = {base_revision: 'fixture', rejection_feedback: [], preference_overrides: {}};
const section = {querySelector: () => ({textContent: '', hidden: false}), querySelectorAll: () => []};
const context = {Set, JSON, window: {tutorPreferenceEditor: {baseline: {'pay.minimum_hourly_cny': 100}}},
  localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
  document: {getElementById: id => id === 'user-settings-data' ? {textContent: JSON.stringify(seed)} : id === 'saved-closed-keys' ? {textContent: '[]'} : section,
    querySelectorAll: selector => selector === 'section' ? [section] : [], addEventListener() {}}};
vm.runInNewContext(core, context);
const state = context.window.tutorUserState;
state.rejection_feedback.push({order_key: 'new', field: 'address', value: '测试站', reason: '地址太远'});
state.deleted_feedback_rules.push({field: 'subject', value: '二年级数学'});
state.preference_overrides = {'pay.minimum_hourly_cny': 150};
state.edited_preference_paths = ['pay.minimum_hourly_cny'];
const old = {closed_order_keys: ['old'], rejection_feedback: [
  {order_key: 'old', field: 'pay', value: '80/h', reason: '薪资不合适'},
  {order_key: 'removed', field: 'subject', value: '二年级数学', reason: '科目不合适'}],
  preference_overrides: {'pay.minimum_hourly_cny': 100, 'commute.maximum_one_way_minutes': 45}};
const merged = context.testMerge(old);
assert.equal(merged.closed_order_keys[0], 'old');
assert.equal(merged.rejection_feedback.length, 2);
assert.equal(merged.preference_overrides['pay.minimum_hourly_cny'], 150);
assert.equal(merged.preference_overrides['commute.maximum_one_way_minutes'], 45);
assert.throws(() => context.testMerge({...old, preference_overrides: {'pay.minimum_hourly_cny': 200}}));

class Element {
  constructor(tag) {this.tag = tag; this.children = []; this.dataset = {}; this.handlers = {}; this.value = ''; this.classList = {toggle() {}};}
  get value() {return this.tag === 'select' ? this.options.find(option=>option.selected)?.value || this._value : this._value;}
  set value(value) {this._value = value; if (this.tag === 'select' && this.children) this.options.forEach(option=>{option.selected=option.value===value;});}
  appendChild(child) {this.children.push(child); child.parentElement = this; return child;}
  replaceChildren() {this.children = [];}
  addEventListener(event, handler) {this.handlers[event] = handler;}
  focus() {}
  setAttribute(name,value) {this[name]=value;}
  get options() {return this.children.filter(child => child.tag === 'option');}
  get selectedOptions() {return this.options.filter(option => option.selected);}
  querySelectorAll(selector) {
    const all = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
    return selector.startsWith('input') ? all.filter(child => child.tag === 'input' && (!selector.includes(':checked') || child.checked)) : all;
  }
  closest() {return this.dataset.path ? this : this.parentElement?.closest();}
}
const ids = Object.fromEntries(['preference-form','preference-fields','learned-rules','back-report','close-feedback','preference-data'].map(id => [id, new Element('div')]));
const baseline = {'pay.minimum_hourly_cny': 100, 'commute.maximum_one_way_minutes': 60,
  'commute.city':'示例城市','commute.origin':'示例地铁站',
  'grades.accepted': ['小学一年级'], 'availability.weekdays.start': '17:00',
  'availability.weekdays.days': [1,2,4], 'availability.full_day_weekdays.days': [3,5], 'availability.weekends.days': [6,7],
  'pay.range_crossing_minimum': 'accept_if_maximum_meets_minimum', 'availability.unspecified_class_time': 'accept_as_negotiable',
  'tutor_profile.gender': 'male', 'tutor_profile.academic_stage': 'master_1', 'tutor_profile.university': '测试大学'};
ids['preference-data'].textContent = JSON.stringify(baseline);
const editorState = {rejection_feedback: [{field:'pay',value:'80/h',reason:'薪资不合适'}], preference_overrides:{}, edited_preference_paths:[], deleted_feedback_rules:[]};
const editorWindow = {tutorUserState: editorState, addEventListener() {}};
vm.runInNewContext(fs.readFileSync('src/preference_editor.js','utf8'), {window: editorWindow, location: {hash:'#preferences'},
  localStorage: context.localStorage, document: {getElementById: id => ids[id], createElement: tag => new Element(tag),
    createTextNode: text => {const element = new Element('text'); element.textContent = text; return element;},
    addEventListener() {}, body: new Element('body')}});
const number = ids['preference-fields'].querySelectorAll('*').find(element => element.dataset.path === 'pay.minimum_hourly_cny');
number.value = '120';
ids['preference-form'].handlers.input({target:number});
assert.equal(editorWindow.tutorPreferenceEditor.collect()['pay.minimum_hourly_cny'], 120);
assert.equal(editorState.edited_preference_paths[0], 'pay.minimum_hourly_cny');
number.value = '-1';
assert.throws(() => editorWindow.tutorPreferenceEditor.collect());
number.value = '120';
ids['learned-rules'].children[0].children[1].handlers.click();
assert.equal(editorState.rejection_feedback.length, 0);
assert.equal(editorState.deleted_feedback_rules.length, 1);
console.log('Feedback save: preserves prior records, exact deletion, stale conflicts; editor validation and rule removal passed');
