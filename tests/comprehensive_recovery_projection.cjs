/* Exercise the real TSX component's request handlers without a live service.
 * Hooks and JSX are minimal test doubles; component logic is not rewritten.
 * Full React/WebKit rendering and exact production recovery are separate gates.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const ts = require(require.resolve('typescript', {paths: [path.join(root, 'apps/web')]}));
const sourcePath = path.join(root, 'apps/web/app/operations/ComprehensiveRecoveryPanel.tsx');
const source = fs.readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  fileName: sourcePath,
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
    esModuleInterop: true,
  },
}).outputText;
const RUN_ID = 'comprun_' + 'a'.repeat(32);
const STAGE = 'final_comprehensive_report_generation';
const blocked = () => ({
  run_id: RUN_ID, repository: 'owner/repository', commit_sha: 'b'.repeat(40),
  status: 'blocked', terminal: true, current_stage: STAGE, progress_percent: 96,
  technical_reason: 'run_storage_compressed_size_limit',
  human_review_required: true, client_delivery_allowed: false,
  response_projection: {durable_projection: true},
});

function harness(responder, locale = 'en', refreshKey = '') {
  const state = [];
  const calls = [];
  const effects = [];
  const navigations = [];
  let cursor = 0;
  let settles = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (value) => {
        state[index] = value;
        if (index === 1 && value === false) settles++;
      }];
    },
    useMemo: (factory) => factory(),
    useEffect: (callback) => effects.push(callback),
  };
  const jsx = (type, props) => ({type, props});
  const exports = {};
  const sandbox = {
    exports, console, URL, Error, TypeError,
    fetch: async (url, options) => {
      calls.push({url, options});
      return responder(url, options);
    },
    window: {location: {origin: 'https://nico.example', assign: (url) => navigations.push(url)}},
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return {jsx, jsxs: jsx};
      if (name === '../assessment/assessmentCopy') return {copyFor: () => ({stageLabels: {}})};
      if (name === './operations.module.css') {
        return {__esModule: true, default: new Proxy({}, {get: (_, key) => String(key)})};
      }
      if (name === './PrivateCheckoutRecovery') return {__esModule: true, default: () => null};
      throw new Error('Unexpected dependency: ' + name);
    },
  };
  vm.runInNewContext(compiled, sandbox, {filename: sourcePath, timeout: 1000});
  function render() {
    cursor = 0;
    effects.length = 0;
    return exports.default({apiUrl: '/api/nico', targetRunId: RUN_ID, refreshKey, locale});
  }
  function walk(node, found = []) {
    if (!node || typeof node !== 'object') return found;
    if (Array.isArray(node)) { node.forEach((child) => walk(child, found)); return found; }
    found.push(node);
    walk(node.props?.children, found);
    return found;
  }
  async function click(index) {
    const tree = render();
    const button = walk(tree).filter((node) => node.type === 'button')[index];
    assert.ok(button, 'Expected the real recovery button');
    assert.equal(button.props.disabled, false);
    const before = settles;
    button.props.onClick();
    for (let tick = 0; tick < 100 && settles === before; tick++) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    assert.ok(settles > before, 'Request handler must settle');
    return render();
  }
  return {state, calls, effects, navigations, render, walk, click};
}
function response(status, payload) {
  return {status, ok: status >= 200 && status < 300, json: async () => payload};
}
function compactOnly(_url, options) {
  // Deliberately fail the old full-record path rather than returning green anyway.
  if (options.headers['X-NICO-Browser-Projection'] !== 'terminal-manifest-v1') {
    return response(504, {detail: {message: 'Full-record status exceeded its request budget'}});
  }
  return response(200, blocked());
}
function assertReadOnlyCall(call) {
  assert.equal(call.url, '/api/nico/assessment/comprehensive-run/' + RUN_ID);
  assert.equal(call.options.method || 'GET', 'GET');
  assert.equal(call.options.credentials, 'same-origin');
  assert.equal(call.options.cache, 'no-store');
  assert.equal(call.options.headers['X-NICO-Browser-Projection'], 'terminal-manifest-v1');
  assert.equal(call.options.headers['X-NICO-Admin-Token'], undefined);
  assert.equal(call.options.body, undefined);
}

for (const locale of ['en', 'es-MX']) {
  test('reload requests bounded exact status and preserves failure: ' + locale, async () => {
    const h = harness(compactOnly, locale);
    h.render();
    h.effects.forEach((effect) => effect());
    assert.equal(h.calls.length, 0, 'Opening recovery alone must not start work');
    const tree = await h.click(0);
    assert.equal(h.calls.length, 1);
    assertReadOnlyCall(h.calls[0]);
    assert.deepEqual(h.state[0], blocked());
    assert.equal(h.state[2], '');
    assert.equal(h.navigations.length, 0);
    const nodes = h.walk(tree);
    assert.ok(nodes.some((node) => node.props?.['data-status-id'] === 'blocked'));
    assert.ok(nodes.some((node) => node.props?.['data-stage-id'] === STAGE));
    assert.ok(nodes.some((node) => node.props?.['data-delivery-state'] === 'blocked'));
    assert.ok(nodes.some((node) => node.props?.children === 'run_storage_compressed_size_limit'));
  });
}

test('mismatched exact identity clears status and leaves Resume disabled', async () => {
  const h = harness(() => response(200, {...blocked(), run_id: 'comprun_' + 'c'.repeat(32)}));
  const tree = await h.click(0);
  assert.equal(h.state[0], null);
  assert.match(h.state[2], /different Comprehensive run identity/);
  assert.equal(h.walk(tree).filter((node) => node.type === 'button')[1].props.disabled, true);
  assert.equal(h.calls.length, 1);
  assertReadOnlyCall(h.calls[0]);
});

for (const status of [401, 403, 504]) {
  test('HTTP ' + status + ' remains visible without retry or anonymous fallback', async () => {
    const h = harness(() => response(status, {detail: {message: 'Preserved error ' + status}}));
    const tree = await h.click(0);
    assert.equal(h.state[0], null);
    assert.equal(h.state[2], 'Preserved error ' + status);
    assert.equal(h.walk(tree).filter((node) => node.type === 'button')[1].props.disabled, true);
    assert.equal(h.calls.length, 1);
    assertReadOnlyCall(h.calls[0]);
    assert.equal(h.navigations.length, 0);
  });
}

test('network failure cannot initiate a continuation', async () => {
  const h = harness(() => {throw new TypeError('Network unavailable');});
  const tree = await h.click(0);
  assert.equal(h.state[0], null);
  assert.equal(h.state[2], 'Network unavailable');
  assert.equal(h.walk(tree).filter((node) => node.type === 'button')[1].props.disabled, true);
  assert.equal(h.calls.length, 1);
  assertReadOnlyCall(h.calls[0]);
});

test('a failed reload invalidates a previously loaded state', async () => {
  let count = 0;
  const h = harness((url, options) => ++count === 1
    ? compactOnly(url, options) : response(504, {detail: {message: 'Timed out'}}));
  await h.click(0);
  assert.equal(h.state[0]?.run_id, RUN_ID);
  const tree = await h.click(0);
  assert.equal(h.state[0], null);
  assert.equal(h.state[2], 'Timed out');
  assert.equal(h.walk(tree).filter((node) => node.type === 'button')[1].props.disabled, true);
  assert.equal(h.calls.length, 2);
  h.calls.forEach(assertReadOnlyCall);
});

test('explicit Resume retains the existing one-stage mutation contract', async () => {
  const h = harness((url, options) => options.method === 'POST'
    ? response(200, blocked()) : compactOnly(url, options));
  await h.click(0);
  await h.click(1);
  assert.equal(h.calls.length, 2);
  const mutation = h.calls[1];
  assert.equal(mutation.url, '/api/nico/assessment/comprehensive-run/' + RUN_ID + '/continue');
  assert.equal(mutation.options.method, 'POST');
  assert.equal(mutation.options.credentials, 'same-origin');
  assert.deepEqual(JSON.parse(mutation.options.body), {max_stages: 1});
  assert.equal(mutation.options.headers['X-NICO-Browser-Projection'], undefined,
    'This repair must not change continuation dispatch semantics');
  assert.equal(h.state[0].status, 'blocked');
  assert.equal(h.state[0].client_delivery_allowed, false);
  assert.match(h.state[2], /remained blocked/);
  assert.equal(h.navigations.length, 0);
});
