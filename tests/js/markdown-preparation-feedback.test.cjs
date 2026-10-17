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
  let now = 0, nextTimer = 0, handler, reportLanguage = lang;
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
      if (name.endsWith('assessmentLocale')) return {reportLanguageForRequest: () => reportLanguage};
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
  return {get actions() { return actions; }, requests, copies, click, advance, respond, replaceActions, setLanguage(value) { reportLanguage = value; }};
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
  test(`${lang}: slow notice preserves the 151-second successful request and its lock`, async () => {
    const h = harness(lang);
    await h.click(); await h.advance(120000);
    assert.equal(h.requests[0].init.signal, undefined);
    assert.equal(h.actions.status.attrs.role, 'status');
    assert.equal(h.actions.status.attrs['aria-busy'], 'true');
    assert.match(h.actions.status.textContent, /longer than expected|más de lo esperado/);
    await h.click(); assert.equal(h.requests.length, 1);
    await h.advance(31249);
    h.respond(); await flush();
    assert.match(h.actions.status.textContent, /Markdown (ready|listo)/);
    assert.deepEqual(h.copies, []);
    await h.click();
    assert.deepEqual(h.copies, ['# Owned report']);
    assert.equal(h.requests.length, 1);
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
  for (const outcome of ['ready', 'error', 'slow']) {
    test(`${lang}: replacement container observes existing preparation ${outcome}`, async () => {
      const h = harness(lang);
      await h.click(); await h.advance(1200);
      h.replaceActions(); await h.click();
      assert.equal(h.requests.length, 1);
      if (outcome === 'slow') await h.advance(120000);
      else { h.respond(0, {}, outcome === 'error' ? 503 : 200); await flush(); }
      assert.equal(h.actions.status.attrs['aria-busy'], outcome === 'slow' ? 'true' : 'false');
      assert.equal(h.actions.status.attrs.role, outcome === 'error' ? 'alert' : 'status');
      if (outcome === 'slow') { h.respond(); await flush(); }
    });
  }
  test(`${lang}: slow response body remains pending until actual settlement`, async () => {
    const h = harness(lang);
    await h.click();
    let finishBody;
    h.requests[0].resolve({ok: true, json: () => new Promise(resolve => { finishBody = resolve; })});
    await flush(); await h.advance(120000);
    assert.equal(h.actions.status.attrs['aria-busy'], 'true');
    await h.click(); assert.equal(h.requests.length, 1);
    finishBody({run_id: 'comprun_owned', commit_sha: 'b'.repeat(40), report_language: lang,
      assessment_rerun: false, report: {markdown: '# Slow body'}});
    await flush(); await h.click();
    assert.equal(h.requests.length, 1);
    assert.deepEqual(h.copies, ['# Slow body']);
  });
}

for (const lang of ['en', 'es-MX']) {
  for (const dimension of ['run', 'commit', 'language']) {
    for (const slow of [false, true]) {
      test(`${lang}: ${dimension} A-B-A retains the pending lock, slow=${slow}`, async () => {
        const h = harness(lang);
        function selectB(enabled) {
          if (dimension === 'run') h.actions.attrs['data-run-id'] = enabled ? 'comprun_other' : 'comprun_owned';
          if (dimension === 'commit') h.actions.attrs['data-commit-sha'] = (enabled ? 'c' : 'b').repeat(40);
          if (dimension === 'language') h.setLanguage(enabled ? (lang === 'en' ? 'es-MX' : 'en') : lang);
        }
        await h.click(); await h.advance(slow ? 120000 : 1200);
        selectB(true); await h.click(); await h.advance(1200);
        selectB(false); await h.click();
        assert.equal(h.requests.length, 2);
        assert.equal(h.requests[0].init.signal, undefined);
        h.respond(0); h.respond(1); await flush();
        assert.match(h.actions.status.textContent, /Markdown (ready|listo)/);
        await h.click(); assert.deepEqual(h.copies, ['# Owned report']);
      });
    }
    for (const outcome of ['ready', 'error', 'slow']) {
      test(`${lang}: changed visible ${dimension} suppresses stale ${outcome} feedback`, async () => {
        const h = harness(lang);
        await h.click();
        const pending = h.actions.status.textContent;
        if (dimension === 'run') h.actions.attrs['data-run-id'] = 'comprun_other';
        if (dimension === 'commit') h.actions.attrs['data-commit-sha'] = 'c'.repeat(40);
        if (dimension === 'language') h.setLanguage(lang === 'en' ? 'es-MX' : 'en');
        if (outcome === 'slow') await h.advance(120000);
        else { h.respond(0, {}, outcome === 'error' ? 503 : 200); await flush(); }
        assert.equal(h.actions.status.textContent, pending);
        assert.deepEqual(h.copies, []);
        if (outcome === 'slow') { h.respond(); await flush(); }
      });
    }
  }
}

for (const lang of ['en', 'es-MX']) {
  test(`${lang}: upstream timeout settles request and permits only explicit retry`, async () => {
    const h = harness(lang);
    await h.click(); await h.advance(240000);
    assert.equal(h.requests.length, 1);
    h.respond(0, {detail: {code: 'assessment_artifact_timeout'}}, 504); await flush();
    assert.match(h.actions.status.textContent, /HTTP 504/);
    assert.match(h.actions.status.textContent, /Server work may still continue|El servidor podría seguir trabajando/);
    assert.deepEqual(h.copies, []);
    await h.click(); assert.equal(h.requests.length, 2);
    h.respond(1); await flush();
  });
}
