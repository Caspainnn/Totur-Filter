const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync('tutor-report.html', 'utf8');
const script = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/)[1].split('/* Shortlist */')[1].split('/* Preference editor */')[0];
const storage = new Map();
function run() {
  const handlers = {}, location = {};
  const card = {dataset: {orderKey: 'fixture'}, selected: false,
    classList: {toggle(_, value) {card.selected = value;}},
    querySelector(selector) {return selector === '.shortlist-order' ? {setAttribute() {}} : null;},
    cloneNode() {return {querySelector() {return null;}, querySelectorAll() {return [];}, appendChild(button) {this.button = button;}, dataset: this.dataset};}};
  const container = {cards: [], replaceChildren() {this.cards = [];}, appendChild(copy) {this.cards.push(copy);}};
  const count = {}, empty = {}, jump = {};
  const section = {querySelector(selector) {return selector === '.shortlist-cards' ? container : selector === 'h2 span' ? count : selector === '.empty' ? empty : {focus() {}};}, scrollIntoView() {}};
  vm.runInNewContext(script, {Set, JSON, location,
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    document: {getElementById: id => id === 'shortlist' ? section : jump,
      createElement: () => ({}), querySelectorAll: () => [card],
      addEventListener: (event, fn) => {handlers[event] = fn;}}});
  const button = {closest: () => card};
  return {card, container, count, location,
    click: () => handlers.click({target: {closest: selector => selector === '.shortlist-order, .unshortlist-order' ? button : null}}),
    jump: () => handlers.click({target: {closest: selector => selector === '#jump-shortlist' ? jump : null}}),
    close: () => handlers['tutor-order-closed']({detail: 'fixture'})};
}
const first = run();
first.click();
assert.equal(first.card.selected, true);
assert.equal(first.container.cards.length, 1);
first.jump();
assert.equal(first.location.hash, 'shortlist');
const refreshed = run();
assert.equal(refreshed.card.selected, true);
refreshed.click();
assert.equal(refreshed.container.cards.length, 0);
refreshed.click(); refreshed.close();
assert.equal(refreshed.container.cards.length, 0);
console.log('Shortlist: original highlight, copy, toggle, jump, reload and close passed');
