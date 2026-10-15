'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(ROOT, 'apps/web/package.json'));
const ts = fromWeb('typescript');
const RUN = 'comprun_poll_budget_fixture';
const active = {run_id: RUN, repository: 'owner/repo', commit_sha: 'a'.repeat(40),
  status: 'running', terminal: false, current_stage: 'human_review_request',
  progress_percent: 91.3, human_review_required: true, client_delivery_allowed: false};
const finished = {...active, status: 'review_required', terminal: true, progress_percent: 100};

function harness(respond, locale = 'en') {
  let cursor = 0, timer = 0;
  const state = [], cache = new Map(), calls = [], storage = new Map();
  const window = {location: new URL(`https://nico.test/assessment?run_id=${RUN}`),
    localStorage: {getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k)},
    history: {state: null, replaceState(_s, _t, url) {window.location = new URL(url, window.location);}},
    setTimeout(fn, ms) {if (ms <= 5000) queueMicrotask(fn); return ++timer;}, clearTimeout() {},
    requestAnimationFrame(fn) {fn();}, scrollTo() {},
  };
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const module = {exports: {}};
    cache.set(filename, module.exports);
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    }}).outputText;
    vm.runInNewContext(compiled, {module, exports: module.exports, window, URL, URLSearchParams,
      Headers, Response, AbortController, setTimeout: window.setTimeout, clearTimeout() {},
      process: {env: {}}, console,
      fetch: async (url, init) => {calls.push({url, method: init.method}); return Response.json(await respond(calls, window));},
      require(name) {
        if (name === 'react') return {
          useState(initial) {const i = cursor++; if (!(i in state)) state[i] = typeof initial === 'function' ? initial() : initial;
            return [state[i], v => {state[i] = typeof v === 'function' ? v(state[i]) : v;}];},
          useRef(initial) {const i = cursor++; if (!(i in state)) state[i] = {current: initial}; return state[i];},
          useEffect() {},
        };
        if (!name.startsWith('.')) return fromWeb(name);
        return load(path.resolve(path.dirname(filename), name + '.ts'));
      },
    }, {filename});
    cache.set(filename, module.exports);
    return module.exports;
  }
  const {useAssessmentRun} = load(path.join(ROOT, 'apps/web/app/assessment/useAssessmentRun.ts'));
  const render = () => {cursor = 0; return useAssessmentRun(locale);};
  return {render, calls, storage, window};
}

for (const locale of ['en', 'es-MX']) {
  for (const historyDenied of [false, true]) {
    test(`saved review remains visible with history denied=${historyDenied} (${locale})`, async () => {
      const payload = {...finished, current_stage: 'client_ready_authorization',
        report: {canonical_truth_sha256: 'b'.repeat(64)}, findings: [{id:'finding_fixture'}]};
      const before = JSON.stringify(payload);
      const h = harness(() => payload, locale);
      if (historyDenied) h.window.history.replaceState = () => {throw new Error('history mutation denied');};
      await h.render().retry();
      const result = h.render();
      assert.equal(result.phase, 'review_required');
      assert.equal(result.issue, null);
      assert.equal(result.result.run_id, RUN);
      assert.equal(result.result.commit_sha, payload.commit_sha);
      assert.equal(result.result.human_review_required, true);
      assert.equal(result.result.client_delivery_allowed, false);
      assert.equal(result.result.progress_percent, 100);
      assert.equal(JSON.stringify(result.result.findings), JSON.stringify(payload.findings));
      assert.equal(JSON.stringify(payload), before);
      assert.equal(h.calls.length, 1);
      assert.equal(h.calls[0].method, 'GET');
      assert.equal(h.window.location.searchParams.get('run_id'), RUN);
    });
  }
}

test('unchanged exact-run URL avoids redundant browser history writes', async () => {
  const h = harness(() => finished);
  h.window.location.searchParams.set('tier', 'comprehensive');
  let writes = 0;
  h.window.history.replaceState = () => {writes++; throw new Error('history mutation denied');};
  await h.render().retry();
  assert.equal(h.render().phase, 'review_required');
  assert.equal(writes, 0);
});

test('review recovery survives unavailable storage and history without a POST', async () => {
  const h = harness(() => finished);
  h.window.localStorage.setItem = () => {throw new Error('storage unavailable');};
  h.window.history.replaceState = () => {throw new Error('history mutation denied');};
  await h.render().retry();
  assert.equal(h.render().phase, 'review_required');
  assert.equal(h.render().result.run_id, RUN);
  assert.equal(h.render().result.client_delivery_allowed, false);
  assert.equal(h.window.location.searchParams.get('run_id'), RUN);
  assert.deepEqual(h.calls.map(c => c.method), ['GET']);
});
