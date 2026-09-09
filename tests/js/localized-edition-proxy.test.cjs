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
function setup() {
  const calls = [];
  const module = {exports: {}};
  vm.runInNewContext(compiled, {module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
    crypto: require('node:crypto').webcrypto,
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.test'}},
    fetch: async (url, init) => {calls.push({url: String(url), init}); return new Response('PK-test-artifact', {headers: {'x-nico-artifact-sha256': 'test-digest'}});},
  });
  return {api: module.exports, calls};
}
function request(method, authenticated = true, origin = 'https://app.test') {
  return {method, nextUrl: new URL('https://app.test/api/nico/assessment'),
    headers: new Headers({origin}), cookies: {get: () => authenticated ? {value: 'SYNTHETIC-SESSION'} : undefined},
    arrayBuffer: async () => new TextEncoder().encode('{"authorization_confirmed":true}').buffer};
}
function context(suffix) {return {params: Promise.resolve({path: ['comprehensive-run', 'comprun-test', 'localized-editions', ...suffix.split('/')]})};}
for (const [method, suffix] of [['GET','es-MX'], ['POST','es-MX'], ['POST','es-MX/review'], ['POST','es-MX/authorize-delivery'], ['GET','es-MX/approved-delivery-package']]) {
  test(`${method} ${suffix} preserves authentication and exact route`, async () => {
    const {api,calls} = setup();
    assert.equal((await api[method](request(method,false),context(suffix))).status,401);
    assert.equal(calls.length,0);
    if(method === 'POST') {
      assert.equal((await api.POST(request(method,true,'https://other.test'),context(suffix))).status,403);
      assert.equal(calls.length,0);
    }
    const response=await api[method](request(method),context(suffix));
    assert.equal(response.status,200);
    assert.equal(calls.length,1);
    assert.equal(calls[0].url,`https://backend.test/assessment/comprehensive-run/comprun-test/localized-editions/${suffix}`);
    assert.equal(calls[0].init.headers.get('X-NICO-Operator-Session'),'SYNTHETIC-SESSION');
    assert.equal(calls[0].init.redirect,'manual');
    assert.equal(response.headers.get('x-nico-artifact-sha256'),'test-digest');
    assert.equal(response.headers.get('Cache-Control'),'no-store, private, max-age=0');
  });
}
for (const suffix of ['fr','es-MX/delete','es-MX/review/extra','es-MX/../review']) {
  test(`unsupported localized operation rejected: ${suffix}`,async()=>{
    const {api,calls}=setup();
    assert.equal((await api.POST(request('POST'),context(suffix))).status,404);
    assert.equal(calls.length,0);
  });
}
