'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {Module, createRequire} = require('node:module');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '../..');
// This specific route wins Next.js routing over /api/nico/[...path].
const ROUTE = path.join(ROOT, 'apps/web/app/api/nico/assessment/[...path]/route.ts');
function shippedRoute() {
  // Production Node 24 supports native TS; the existing Python CI harness uses
  // Node 20 and installs the web project's TypeScript compiler.
  if (Number(process.versions.node.split('.')[0]) >= 24) return require(ROUTE);
  const ts = createRequire(path.join(ROOT, 'apps/web/package.json'))('typescript');
  const compiled = ts.transpileModule(fs.readFileSync(ROUTE, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
  });
  const loaded = new Module(ROUTE, module);
  loaded._compile(compiled.outputText, ROUTE);
  return loaded.exports;
}
const api = shippedRoute();
const TOKEN = 'synthetic-engineering-test-session';
const segments = ['comprehensive-run', 'comprun_test', 'report', 'evidence-package'];
function load(fetch) {
  global.fetch = fetch;
  process.env.NODE_ENV = 'production';
  process.env.NICO_API_URL = 'https://backend.nico.test';
  delete process.env.NICO_BACKEND_URL;
  delete process.env.NEXT_PUBLIC_NICO_API_URL;
  return api;
}
function request({session = TOKEN, method = 'GET', headerSession = ''} = {}) {
  return {method, nextUrl: new URL('https://app.nico.test/api/nico/assessment'),
    cookies: {get: () => session ? {value: session} : undefined},
    headers: new Headers({'origin': 'https://app.nico.test',
      ...(headerSession ? {'x-nico-operator-session': headerSession} : {})}),
    arrayBuffer: async () => new ArrayBuffer(0),
  };
}
const context = (parts = segments) => ({params: Promise.resolve({path: parts})});

test('ordinary owner download streams exact retained bytes and provenance', async () => {
  const bytes = Buffer.from([80, 75, 3, 4, 0, 255, 13, 10]);
  let calls = 0;
  const api = load(async (url, init) => {
    calls++;
    assert.equal(url.pathname, '/assessment/comprehensive-run/comprun_test/report/evidence-package');
    assert.equal(init.headers.get('x-nico-operator-session'), TOKEN);
    assert.equal(init.redirect, 'manual');
    return new Response(bytes, {headers: {'content-type': 'application/zip',
      'content-disposition': 'attachment; filename="retained.zip"',
      'x-nico-artifact-sha256': 'a'.repeat(64), 'x-nico-evidence-manifest-sha256': 'b'.repeat(64),
      'x-nico-artifact-scope': 'retained-canonical-artifact-set', 'x-nico-run-revision': '57',
      'x-nico-approval-status': 'pending_human_approval', 'x-nico-client-delivery-allowed': 'false'}});
  });
  const response = await api.GET(request(), context());
  assert.equal(response.status, 200);
  assert.deepEqual(Buffer.from(await response.arrayBuffer()), bytes);
  assert.equal(response.headers.get('content-disposition'), 'attachment; filename="retained.zip"');
  assert.equal(response.headers.get('x-nico-evidence-manifest-sha256'), 'b'.repeat(64));
  assert.equal(response.headers.get('x-nico-artifact-scope'), 'retained-canonical-artifact-set');
  assert.equal(response.headers.get('x-nico-run-revision'), '57');
  assert.equal(response.headers.get('x-nico-approval-status'), 'pending_human_approval');
  assert.equal(response.headers.get('x-nico-client-delivery-allowed'), 'false');
  assert.equal(response.headers.get('cache-control'), 'no-store, private, max-age=0');
  assert.equal(calls, 1);
});

for (const [name, options, parts, status] of [
  ['unauthenticated', {session: ''}, segments, 401],
  ['conflicting identities', {headerSession: 'different-test-session'}, segments, 409],
  ['mutation', {method: 'POST'}, segments, 405],
  ['unknown artifact', {}, [...segments.slice(0, -1), 'private-debug'], 404],
  ['extra path', {}, [...segments, 'extra'], 404],
]) test(name + ' cannot reach the backend', async () => {
  const api = load(async () => { throw new Error('must not reach backend'); });
  const response = await api[options.method || 'GET'](request(options), context(parts));
  assert.equal(response.status, status);
});

test('explicit upstream access denial is preserved', async () => {
  const api = load(async () => Response.json({detail: 'scope_denied'}, {status: 403}));
  const response = await api.GET(request(), context());
  assert.equal(response.status, 403);
  assert.equal((await response.json()).detail, 'scope_denied');
});
