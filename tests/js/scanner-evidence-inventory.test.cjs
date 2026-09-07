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
const ROUTE = path.join(ROOT, 'apps/web/app/api/nico/assessment/[...path]/route.ts');
const compiled = ts.transpileModule(fs.readFileSync(ROUTE, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
  reportDiagnostics: true,
});
assert.equal((compiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
function load(fetchImpl) {
  const module = {exports: {}};
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
    crypto: require('node:crypto').webcrypto,
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://nico.test'}},
    fetch: fetchImpl,
  }, {filename: ROUTE});
  return module.exports;
}
function request(method = 'GET', session = 'synthetic-owner-session') {
  return {method, headers: new Headers(), cookies: {get: () => session ? {value: session} : undefined}, nextUrl: new URL('https://app.nico.test/api/nico/assessment/comprehensive-run/comprun_test/scanner-evidence')};
}
const context = segments => ({params: Promise.resolve({path: ['comprehensive-run', 'comprun_test', ...segments]})});

test('inventory forwards an authenticated GET through the established cookie bridge', async () => {
  let calls = 0;
  const api = load(async (url, init) => {
    calls++;
    assert.equal(url.pathname, '/assessment/comprehensive-run/comprun_test/scanner-evidence');
    assert.equal(init.method, 'GET');
    assert.equal(init.headers.get('X-NICO-Operator-Session'), 'synthetic-owner-session');
    assert.equal(init.headers.has('X-NICO-Admin-Token'), false);
    assert.equal(init.cache, 'no-store');
    assert.equal(init.redirect, 'manual');
    assert.equal(init.body, undefined);
    return Response.json({read_only: true, scanner_records: []});
  });
  const result = await api.GET(request(), context(['scanner-evidence']));
  assert.equal(result.status, 200);
  assert.equal(calls, 1);
  assert.equal(result.headers.get('Cache-Control'), 'no-store, private, max-age=0');
});

test('inventory needs a session before contacting the backend', async () => {
  const api = load(async () => assert.fail('unauthenticated backend call'));
  assert.equal((await api.GET(request('GET', ''), context(['scanner-evidence']))).status, 401);
});

test('inventory POST and arbitrary raw paths are rejected before contacting the backend', async () => {
  const api = load(async () => assert.fail('forbidden backend call'));
  assert.equal((await api.POST(request('POST'), context(['scanner-evidence']))).status, 405);
  for (const segments of [['scanner-evidence', 'raw'], ['scanner-evidence-download'], ['scanner-evidence', '..']]) {
    assert.equal((await api.GET(request(), context(segments))).status, 404);
  }
});

test('backend owner-only denial is preserved, not interpreted as granted access', async () => {
  const api = load(async () => Response.json({status: 'blocked', detail: {code: 'owner_administration_required'}}, {status: 403}));
  const result = await api.GET(request(), context(['scanner-evidence']));
  assert.equal(result.status, 403);
  assert.equal((await result.json()).detail.code, 'owner_administration_required');
});
