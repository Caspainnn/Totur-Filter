const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync('tutor-report.html', 'utf8');
const script = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/)[1].split('/* Shortlist */')[0];
const feedback = {textContent: ''}, storage = new Map();
const section = {querySelector: () => ({textContent: '', hidden: false}), querySelectorAll: () => []};
let click, writes = 0, conflict = false, offline = false, updates = 0;
let disk = {closed_order_keys: ['existing-order'], rejection_feedback: [], preference_overrides: {'commute.maximum_one_way_minutes': 45}};
const window = {
  showSaveFilePicker() {throw Error('Local save must not open a file picker');},
  showDirectoryPicker() {throw Error('Local save must not open a directory picker');},
  tutorPreferenceEditor: {baseline: {'pay.minimum_hourly_cny': 100},
    collect() {return {'pay.minimum_hourly_cny': 130};}, updateBaseline() {updates++;}}
};
const document = {
  querySelector: () => ({content: 'synthetic-token'}),
  getElementById(id) {
    if (id === 'close-feedback') return feedback;
    if (id === 'saved-closed-keys') return {textContent: '["new-order"]'};
    if (id === 'user-settings-data') return {textContent: '{"edited_preference_paths":["pay.minimum_hourly_cny"]}'};
    return section;
  },
  querySelectorAll: selector => selector === 'section' ? [section] : [],
  addEventListener(name, handler) {if (name === 'click') click = handler;}, dispatchEvent() {}
};
const fetch = async (url, options) => {
  assert.equal(url, '/api/settings');
  assert.equal(options.headers['X-Tutor-Token'], 'synthetic-token');
  if (offline) throw Error('Disconnected');
  if (options.method === 'GET') return {ok: true, json: async () => ({revision: 'r1', settings: disk})};
  writes++;
  if (conflict) return {ok: false, status: 409, json: async () => ({error: 'SETTINGS_CHANGED'})};
  const body = JSON.parse(options.body);
  assert.equal(body.revision, 'r1');
  disk = body.settings;
  return {ok: true, json: async () => ({revision: 'r2', settings: disk})};
};
vm.runInNewContext(script, {window, document, fetch, Set, JSON, CustomEvent: class {},
  localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)}});
const event = {target: {closest: selector => selector === '#save-closed' ? {} : null}};
(async () => {
  await click(event);
  assert.equal(writes, 1);
  assert.deepEqual(disk.closed_order_keys, ['existing-order', 'new-order']);
  assert.equal(disk.preference_overrides['commute.maximum_one_way_minutes'], 45);
  assert.equal(disk.preference_overrides['pay.minimum_hourly_cny'], 130);
  assert.match(feedback.textContent, /已保存/);
  await click(event);
  assert.equal(writes, 2, 'Repeated save still uses local API without a picker');
  conflict = true;
  await click(event);
  assert.equal(updates, 2, 'A conflict must not clear dirty state');
  assert.match(feedback.textContent, /变化|修改|冲突/);
  offline = true;
  await click(event);
  assert.equal(updates, 2);
  assert.doesNotMatch(feedback.textContent, /^已保存/);
  console.log('Local save: repeated saves without pickers; preserves records; conflicts and network errors never claim success');
})().catch(error => {console.error(error); process.exitCode = 1;});
