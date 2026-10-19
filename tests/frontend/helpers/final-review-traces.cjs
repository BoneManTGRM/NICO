// Reuse the actual-handler suite's fixtures/adapters without registering its tests.
// Instrument only the adapters: the TSX source is compiled and executed unchanged.
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
const filename = path.resolve('tests/frontend/final_review_approval.test.cjs');
const original = fs.readFileSync(filename, 'utf8');
let prefix = original.slice(0, original.indexOf("test('pending approval remains actionable"));
const helpers = original.slice(original.indexOf('function loadHelpers('), original.indexOf("test('final review navigation"));
const replacements = [
  ['const slots = [], effects', 'const trace = []; const capture = (kind, value) => trace.push(JSON.parse(JSON.stringify({kind, value}, (_k, v) => typeof v === "function" ? "[callback]" : v)));\n  const slots = [], effects'],
  ['slots[index] = typeof value === \'function\' ? value(slots[index]) : value;', 'slots[index] = typeof value === \'function\' ? value(slots[index]) : value; capture("state", {index, value: slots[index]});'],
  ['slots[index] = {current: initial};', 'slots[index] = new Proxy({current: initial}, {set(target, key, value) {target[key] = value; capture("ref", {index, key, value}); return true;}});'],
  ['requests.push(request);', 'requests.push(request); capture("request", request);'],
  ['dispatchEvent(event) {listeners', 'dispatchEvent(event) {capture("event", event.type); listeners'],
  ['if (popupBlocked) return null;', 'capture("popup-open", {blocked: popupBlocked}); if (popupBlocked) return null;'],
  ['close() {this.closed = true;}', 'close() {this.closed = true; capture("popup-close", true);}'],
  ['popup.url = url;', 'popup.url = url; capture("popup-present", url);'],
  ['class Anchor {click() {downloads.push', 'class Anchor {click() {capture("download", {filename: this.download, href: this.href}); downloads.push'],
  ['tree = context.exports.default(); return tree;', 'tree = context.exports.default(); capture("render", tree); return tree;'],
  ['return {button, field, change, click, load, ready, render, requests', 'return {trace, button, field, change, click, load, ready, render, requests'],
];
for (const [from, to] of replacements) {
  if (!prefix.includes(from)) throw new Error(`Missing harness instrumentation anchor: ${from}`);
  prefix = prefix.replace(from, to);
}
const helperModule = new Module(filename, module);
helperModule.filename = filename; helperModule.paths = module.paths;
helperModule._compile(prefix + helpers + '\nmodule.exports = {harness, fixture, authorizedFixture, response, stable, digest};', filename);
module.exports = helperModule.exports;
