const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const code = ts.transpileModule(fs.readFileSync(path.join(root, 'apps/web/app/AssessmentMarkdownCopyBridge.tsx'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness(lang) {
  let now = 0, nextTimer = 0, handler;
  const timers = new Map(), requests = [], copies = [];
  class Element {
    constructor() { this.attrs = {}; this.isConnected = true; this.textContent = ''; }
    setAttribute(k, v) { this.attrs[k] = v; }
    getAttribute(k) { return this.attrs[k] ?? null; }
    remove() { this.isConnected = false; }
  }
  let actions = new Element();
  actions.attrs = {'data-run-id': 'comprun_owned', 'data-commit-sha': 'b'.repeat(40), 'data-assessment-report-ready': 'true'};
  actions.querySelector = () => actions.status?.isConnected ? actions.status : null;
  actions.appendChild = status => { actions.status = status; };
  class Button extends Element {
    constructor() { super(); this.disabled = false; this.textContent = lang === 'en' ? 'Copy Markdown' : 'Copiar Markdown'; }
    closest(selector) { return selector === 'button' ? this : actions; }
  }
  const button = new Button();
  const window = {
    location: new URL(`https://unit.invalid/assessment?lang=${lang}`),
    setTimeout(fn, delay) { timers.set(++nextTimer, {fn, at: now + delay}); return nextTimer; },
    clearTimeout(id) { timers.delete(id); },
  };
  const document = {documentElement: {lang}, createElement: () => new Element(),
    addEventListener(name, fn) { handler = fn; }, removeEventListener() {}, querySelectorAll: () => []};
  const module = {exports: {}};
  vm.runInNewContext(code, {module, exports: module.exports, window, document, Element, HTMLButtonElement: Button,
    URL, AbortController, Date: {now: () => now},
    navigator: {clipboard: {writeText(text) { copies.push(text); return Promise.resolve(); }}},
    fetch(url, init) { return new Promise((resolve, reject) => requests.push({url, init, resolve, reject})); },
    require(name) {
      if (name === 'react') return {useEffect: fn => fn(), useRef: value => ({current: value})};
      if (name.endsWith('assessmentLocale')) return {reportLanguageForRequest: () => lang};
      throw Error(name);
    },
  });
  module.exports.default();
  async function advance(ms) {
    now += ms;
    for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.fn(); }
    await flush();
  }
  async function click() {
    await handler({target: button, preventDefault() {}, stopPropagation() {}, stopImmediatePropagation() {}});
    await flush();
  }
  function respond(index = 0, changes = {}, status = 200) {
    requests[index].resolve({ok: status === 200, status, json: async () => ({run_id: 'comprun_owned',
      commit_sha: 'b'.repeat(40), report_language: lang, assessment_rerun: false,
      report: {markdown: '# Owned report'}, ...changes})});
  }
  function replaceActions() {
    const old = actions;
    old.isConnected = false;
    actions = new Element();
    actions.attrs = {...old.attrs};
    actions.querySelector = () => actions.status?.isConnected ? actions.status : null;
    actions.appendChild = status => { actions.status = status; };
  }
  return {get actions() { return actions; }, requests, copies, click, advance, respond, replaceActions};
}
for (const lang of ['en', 'es-MX']) {
  test(`${lang}: pending stays visible, repeated clicks deduplicate, ready needs a new clipboard gesture`, async () => {
    const h = harness(lang);
    await h.click();
    await h.advance(9000);
    assert.equal(h.actions.status.isConnected, true);
    assert.equal(h.actions.status.attrs['aria-busy'], 'true');
    await h.click();
    assert.equal(h.requests.length, 1);
    h.respond(); await flush();
    assert.equal(h.actions.status.attrs['aria-busy'], 'false');
    assert.match(h.actions.status.textContent, /Markdown (ready|listo)/);
    assert.deepEqual(h.copies, []);
    await h.advance(9000);
    assert.equal(h.actions.status.isConnected, true);
    await h.click();
    assert.deepEqual(h.copies, ['# Owned report']);
    assert.equal(h.requests.length, 1);
  });
  test(`${lang}: errors persist and retry only follows an explicit gesture`, async () => {
    const h = harness(lang);
    await h.click(); h.respond(0, {detail: {code: 'bounded_failure'}}, 503); await flush();
    assert.equal(h.actions.status.attrs.role, 'alert');
    assert.match(h.actions.status.textContent, /HTTP 503/);
    await h.advance(9000);
    assert.equal(h.actions.status.isConnected, true);
    assert.equal(h.requests.length, 1);
    await h.click(); assert.equal(h.requests.length, 2);
    h.respond(1); await flush();
    assert.match(h.actions.status.textContent, /Markdown (ready|listo)/);
  });
  test(`${lang}: timeout aborts, retains lock until settlement, and rejects late readiness`, async () => {
    const h = harness(lang);
    await h.click(); await h.advance(120000);
    assert.equal(h.requests[0].init.signal.aborted, true);
    assert.equal(h.actions.status.attrs.role, 'alert');
    assert.match(h.actions.status.textContent, /timed out|agotó/);
    await h.click(); assert.equal(h.requests.length, 1);
    h.respond(); await flush();
    assert.doesNotMatch(h.actions.status.textContent, /Markdown (ready|listo)/);
    assert.deepEqual(h.copies, []);
    await h.advance(1200); await h.click(); assert.equal(h.requests.length, 2);
    h.respond(1); await flush();
    assert.match(h.actions.status.textContent, /Markdown (ready|listo)/);
  });
  for (const changes of [{run_id: 'comprun_wrong'}, {commit_sha: 'c'.repeat(40)},
    {report_language: 'wrong'}, {assessment_rerun: true}, {report: {markdown: ''}}]) {
    test(`${lang}: rejects invalid report ${Object.keys(changes)[0]}`, async () => {
      const h = harness(lang);
      await h.click(); h.respond(0, changes); await flush();
      assert.equal(h.actions.status.attrs.role, 'alert');
      assert.deepEqual(h.copies, []);
    });
  }
}

for (const lang of ['en', 'es-MX']) {
  for (const outcome of ['ready', 'error', 'timeout']) {
    test(`${lang}: replacement container observes existing preparation ${outcome}`, async () => {
      const h = harness(lang);
      await h.click(); await h.advance(1200);
      h.replaceActions(); await h.click();
      assert.equal(h.requests.length, 1);
      if (outcome === 'timeout') await h.advance(120000);
      else { h.respond(0, {}, outcome === 'error' ? 503 : 200); await flush(); }
      assert.equal(h.actions.status.attrs['aria-busy'], 'false');
      assert.equal(h.actions.status.attrs.role, outcome === 'ready' ? 'status' : 'alert');
      if (outcome === 'timeout') { h.respond(); await flush(); }
    });
  }
  test(`${lang}: timeout covers response body and never caches its late result`, async () => {
    const h = harness(lang);
    await h.click();
    let finishBody;
    h.requests[0].resolve({ok: true, json: () => new Promise(resolve => { finishBody = resolve; })});
    await flush(); await h.advance(120000);
    assert.equal(h.actions.status.attrs.role, 'alert');
    finishBody({run_id: 'comprun_owned', commit_sha: 'b'.repeat(40), report_language: lang,
      assessment_rerun: false, report: {markdown: '# Late body'}});
    await flush(); await h.click();
    assert.equal(h.requests.length, 2);
    assert.deepEqual(h.copies, []);
    h.respond(1); await flush();
  });
}
