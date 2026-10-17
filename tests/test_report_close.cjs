const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const crypto = require('crypto');
const html = fs.readFileSync('tutor-report.html', 'utf8');
const script = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/)[1];
const browserScript = script.replace(/\r\n?/g, '\n');
const actualHash = crypto.createHash('sha256').update(browserScript).digest('base64');
assert.equal(html.match(/script-src 'sha256-([^']+)'/)[1], actualHash, 'Browser must allow the script after normalizing line endings');
const storage = new Map();
function run() {
  let listener;
  const section = () => ({cards: [], count: {textContent: ''}, empty: {},
    querySelectorAll() { return this.cards; },
    querySelector(selector) { return selector === 'h2 span' ? this.count : selector === '.empty' ? this.empty : {focus() {}}; },
    appendChild(card) { card.parentElement.cards = card.parentElement.cards.filter(c => c !== card); this.cards.push(card); card.parentElement = this; },
    scrollIntoView() {}});
  const pending = section(), closed = section();
  const reason = {}, button = {remove() { this.removed = true; }, closest() { return card; }};
  const card = {dataset: {orderKey: 'synthetic-order'}, parentElement: pending,
    querySelector(selector) { return selector === '.reason' ? reason : selector === '.close-order' ? button : null; }};
  pending.cards.push(card);
  const location = {};
  new vm.Script(script); // Both interactions must parse, with CSP checked above.
  vm.runInNewContext(script.split('/* Shortlist */')[0], {Set, JSON, location,
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    document: {getElementById: () => closed,
      querySelectorAll: selector => selector === 'section' ? [pending, closed] : [card],
      addEventListener: (_, fn) => { listener = fn; }}});
  return {pending, closed, card, location, click: () => listener({target: {closest: selector => selector === '.close-order' ? button : null}})};
}
const first = run();
first.click();
assert.equal(first.closed.cards.length, 1);
assert.equal(first.pending.count.textContent, 0);
assert.equal(first.location.hash, undefined);
const refreshed = run();
assert.equal(refreshed.closed.cards.length, 1);
assert.equal(refreshed.pending.cards.length, 0);
console.log('Manual close: move, counts, no navigation and persistence passed');
