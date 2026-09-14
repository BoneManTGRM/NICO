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

test('terminal result on the last continuation is not replaced by polling timeout', async () => {
  let posts = 0;
  const h = harness(calls => {if (calls.at(-1).method === 'POST') posts++;
    return posts === 360 ? finished : active;});
  await h.render().retry();
  assert.equal(posts, 360);
  assert.equal(h.render().phase, 'review_required');
  assert.equal(h.render().issue, null);
  assert.equal(h.storage.has('nico.comprehensive.active-run.v1'), false);
});

test('poll budget performs an exact-run read to reconcile publication after the last continuation', async () => {
  let posts = 0;
  const h = harness(calls => {const method = calls.at(-1).method;
    if (method === 'POST') posts++;
    return posts === 360 && method === 'GET' ? finished : active;});
  await h.render().retry();
  assert.equal(h.calls.at(-1).method, 'GET');
  assert.equal(h.render().phase, 'review_required');
  assert.equal(posts, 360);
});

for (const locale of ['en', 'es-MX']) test(`active run has an actionable same-run recovery after poll exhaustion (${locale})`, async () => {
  let recovered = false;
  const h = harness(() => recovered ? finished : active, locale);
  await h.render().retry();
  const paused = h.render();
  assert.equal(paused.phase, 'timed_out');
  assert.equal(paused.running, false);
  assert.equal(paused.issue?.retryable, true);
  assert.equal(paused.issue?.runCreated, true);
  assert.equal(paused.issue?.code, 'assessment_poll_budget_exhausted');
  assert.equal(paused.result.run_id, RUN);
  assert.equal(h.window.location.searchParams.get('run_id'), RUN);
  assert.ok(h.storage.has('nico.comprehensive.active-run.v1'));
  const before = h.calls.length;
  recovered = true;
  await paused.retry();
  assert.equal(h.calls.length, before + 1);
  assert.equal(h.calls.at(-1).method, 'GET');
  assert.equal(h.render().phase, 'review_required');
  assert.ok(h.calls.every(c => c.url.includes(RUN)));
  assert.equal(h.render().result.client_delivery_allowed, false);
});

test('failed final status read preserves the last observation and permits recovery without more mutations', async () => {
  let posts = 0;
  const h = harness(calls => {
    if (calls.at(-1).method === 'POST') posts++;
    else if (posts === 360) throw new Error('status transport unavailable');
    return active;
  });
  await h.render().retry();
  assert.equal(posts, 360);
  assert.equal(h.render().result.run_id, RUN);
  assert.equal(h.render().result.terminal, false);
  assert.equal(h.render().phase, 'timed_out');
  assert.equal(h.render().issue.retryable, true);
});

test('a superseded polling loop cannot restore a cleared run after its final read', async () => {
  let posts = 0;
  const h = harness(calls => {
    if (calls.at(-1).method === 'POST') posts++;
    else if (posts === 360) {h.render().startNew(); return finished;}
    return active;
  });
  await h.render().retry();
  assert.equal(posts, 360);
  assert.equal(h.render().phase, 'idle');
  assert.equal(h.render().result, null);
  assert.equal(h.render().issue, null);
  assert.equal(h.window.location.searchParams.has('run_id'), false);
});
