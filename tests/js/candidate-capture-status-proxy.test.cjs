'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const source = fs.readFileSync(path.join(root, 'apps/web/app/api/nico/assessment/[...path]/route.ts'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
test('count-only status preserves auth, explicit projection, and no-store transport', async () => {
  const calls = [], module = {exports: {}};
  vm.runInNewContext(compiled, {module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
    crypto: require('node:crypto').webcrypto,
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.test'}},
    fetch: async (url, init) => {calls.push({url: String(url), init}); return new Response('{"candidate_source_capture_diagnostics":{"status":"missing"}}', {headers: {'content-type': 'application/json'}});},
  });
  const context = {params: Promise.resolve({path: ['comprehensive-run', 'run']})};
  const request = {method: 'GET', nextUrl: new URL('https://app.test/api/nico/assessment/comprehensive-run/run?projection=candidate-source-capture-v1'),
    headers: new Headers(), cookies: {get: () => undefined}};
  assert.equal((await module.exports.GET(request, context)).status, 401);
  assert.equal(calls.length, 0);
  request.cookies.get = () => ({value: 'SYNTHETIC-SESSION'});
  const response = await module.exports.GET(request, context);
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://backend.test/assessment/comprehensive-run/run?projection=candidate-source-capture-v1');
  assert.equal(calls[0].init.headers.get('X-NICO-Operator-Session'), 'SYNTHETIC-SESSION');
  assert.equal(calls[0].init.cache, 'no-store');
  assert.equal(calls[0].init.redirect, 'manual');
  assert.equal(response.headers.get('Cache-Control'), 'no-store, private, max-age=0');
  assert.equal((await response.json()).candidate_source_capture_diagnostics.status, 'missing');
});
