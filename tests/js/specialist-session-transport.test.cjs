'use strict';

// Exercise shipped route handlers, not a copy of their decision logic.
// NextResponse/cookies are a framework-boundary double. Redirect tests use real
// Node fetch and two loopback-only HTTP servers with synthetic credentials.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(ROOT, 'apps/web/package.json'));
const ts = fromWeb('typescript');
const ROUTE = path.join(ROOT, 'apps/web/app/api/nico/operator-session/route.ts');
const COOKIE = 'nico-specialist-session';
const PRIVATE_CACHE = 'no-store, private, max-age=0';
const TOKEN = 'test-only-session-not-a-real-credential';
const PASSWORD = 'test-only-password-not-a-real-credential';
const compiled = ts.transpileModule(fs.readFileSync(ROUTE, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
  reportDiagnostics: true,
});
assert.equal((compiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);

class FakeNextResponse extends Response {
  constructor(body, init) {
    super(body, init);
    this.cookieWrites = [];
    this.cookies = {set: (name, value, options) => this.cookieWrites.push({name, value, options})};
  }
  static json(body, init = {}) {
    const headers = new Headers(init.headers);
    headers.set('Content-Type', 'application/json');
    return new FakeNextResponse(JSON.stringify(body), {...init, headers});
  }
}
function load(fetchImpl, env = {}) {
  const module = {exports: {}};
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, URL, Headers, Response, AbortSignal,
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://nico.test', ...env}},
    fetch: fetchImpl,
    require(name) { assert.equal(name, 'next/server'); return {NextResponse: FakeNextResponse}; },
  }, {filename: ROUTE});
  return module.exports;
}
function request({session = TOKEN, origin = 'https://app.nico.test', body = {password: PASSWORD}} = {}) {
  return {
    nextUrl: new URL('https://app.nico.test/api/nico/operator-session'),
    headers: new Headers(origin ? {origin} : {}),
    cookies: {get: name => name === COOKIE && session ? {value: session} : undefined},
    json: async () => body,
  };
}
const upstream = (status, body = {status: 'authenticated'}, headers) => Response.json(body, {status, headers});
function assertPrivate(response) { assert.equal(response.headers.get('Cache-Control'), PRIVATE_CACHE); }
function assertRetained(response) { assert.equal(response.cookieWrites.length, 0, 'an indeterminate backend result must not erase the saved session'); }
function assertCleared(response) {
  assert.equal(response.cookieWrites.length, 1);
  assert.equal(response.cookieWrites[0].name, COOKIE);
  assert.equal(response.cookieWrites[0].value, '');
  assert.equal(response.cookieWrites[0].options.maxAge, 0);
}

test('GET without a session fails closed and cannot be cached', async () => {
  const api = load(async () => { throw new Error('must not contact backend'); });
  const response = await api.GET(request({session: ''}));
  assert.equal(response.status, 401); assertCleared(response); assertPrivate(response);
});
for (const env of [{NICO_API_URL: ''}, {NICO_BACKEND_URL: 'https://conflicting.test'}]) {
  test('GET with missing/ambiguous backend retains session but grants no access: ' + JSON.stringify(env), async () => {
    let calls = 0;
    const api = load(async () => { calls++; return upstream(200); }, env);
    const response = await api.GET(request());
    assert.equal(response.status, 503); assertRetained(response); assertPrivate(response);
    assert.equal(calls, 0);
  });
}
for (const method of ['GET', 'POST']) {
  test(method + ' network failure is not an invalid credential', async () => {
    const api = load(async () => { throw new TypeError('test-only network interruption'); });
    const response = await api[method](request());
    assert.equal(response.status, 502); assertRetained(response); assertPrivate(response);
    assert.notEqual((await response.json()).status, 'authenticated');
  });
  for (const status of [500, 502, 503, 504]) {
    test(`${method} upstream ${status} retains the session and blocks access`, async () => {
      const api = load(async () => upstream(status, {secret: PASSWORD}));
      const response = await api[method](request());
      assert.equal(response.status, 503); assertRetained(response); assertPrivate(response);
      assert.equal((await response.text()).includes(PASSWORD), false);
    });
  }
  for (const status of [401, 403]) {
    test(`${method} explicit ${status} denial clears the session`, async () => {
      const api = load(async () => upstream(status));
      const response = await api[method](request());
      assert.equal(response.status, method === 'GET' ? 401 : 403);
      assertCleared(response); assertPrivate(response);
    });
  }
  test(method + ' rate limit preserves Retry-After without clearing credentials', async () => {
    const api = load(async () => upstream(429, {status: 'blocked'}, {'Retry-After': '60'}));
    const response = await api[method](request());
    assert.equal(response.status, 429); assert.equal(response.headers.get('Retry-After'), '60');
    assertRetained(response); assertPrivate(response);
  });
}
for (const body of [{status: 'unauthenticated'}, {status: 'ready'}, null]) {
  test('GET requires positive authenticated payload, not only HTTP 200: ' + JSON.stringify(body), async () => {
    const api = load(async () => upstream(200, body));
    const response = await api.GET(request());
    assert.equal(response.status, 503); assertRetained(response); assertPrivate(response);
  });
}
test('GET rejects malformed JSON without granting access or deleting the session', async () => {
  const api = load(async () => new Response('<html>not the session service</html>'));
  const response = await api.GET(request());
  assert.equal(response.status, 503); assertRetained(response); assertPrivate(response);
});
test('GET validated session stays authenticated without returning its token', async () => {
  let calls = 0;
  const api = load(async (url, init) => {
    calls++; assert.equal(url.pathname, '/assessment/comprehensive-operator/session');
    assert.equal(init.headers['X-NICO-Operator-Session'], TOKEN);
    assert.equal(init.cache, 'no-store');
    return upstream(200, {status: 'authenticated', scope: 'nico_specialist_operation'});
  });
  const response = await api.GET(request());
  assert.equal(response.status, 200); assertRetained(response); assertPrivate(response);
  assert.deepEqual(await response.json(), {status: 'authenticated'}); assert.equal(calls, 1);
});
test('POST successful exchange returns only public metadata and keeps secure cookie flags', async () => {
  let calls = 0;
  const api = load(async (url, init) => {
    calls++; assert.equal(url.pathname, '/assessment/comprehensive-operator/session');
    assert.equal(init.headers['X-NICO-Admin-Token'], PASSWORD);
    return upstream(200, {status: 'authenticated', session_token: TOKEN, expires_in: 3600});
  });
  const response = await api.POST(request());
  assert.equal(response.status, 200); assertPrivate(response); assert.equal(calls, 1);
  assert.deepEqual(await response.json(), {status: 'authenticated', expires_in: 3600});
  const cookie = response.cookieWrites[0];
  assert.equal(cookie.name, COOKIE); assert.equal(cookie.value, TOKEN);
  assert.equal(cookie.options.httpOnly, true); assert.equal(cookie.options.secure, true);
  assert.equal(cookie.options.sameSite, 'strict'); assert.equal(cookie.options.path, '/');
  assert.equal(cookie.options.maxAge, 3600);
});
for (const method of ['POST', 'DELETE']) {
  test(method + ' rejects cross-origin writes without touching the session', async () => {
    let calls = 0;
    const api = load(async () => { calls++; return upstream(200); });
    const response = await api[method](request({origin: 'https://other.test'}));
    assert.equal(response.status, 403); assertRetained(response); assertPrivate(response);
    assert.equal(calls, 0);
  });
}
test('POST rejects empty credentials without a backend call', async () => {
  let calls = 0;
  const api = load(async () => { calls++; return upstream(200); });
  const response = await api.POST(request({body: {password: ''}}));
  assert.equal(response.status, 422); assert.equal(calls, 0); assertPrivate(response);
});
test('DELETE performs explicit sign-out and cannot be cached', async () => {
  const api = load(async () => { throw new Error('must not contact backend'); });
  const response = await api.DELETE(request());
  assert.equal(response.status, 200); assertCleared(response); assertPrivate(response);
});

async function server(handler) {
  const instance = http.createServer(handler);
  await new Promise((resolve, reject) => {
    instance.once('error', reject); instance.listen(0, '127.0.0.1', resolve);
  });
  return instance;
}
async function close(instance) {
  instance.closeAllConnections();
  await new Promise(resolve => instance.close(resolve));
}
for (const method of ['GET', 'POST']) {
  test(method + ' never follows an upstream redirect carrying credentials (real loopback HTTP)', async () => {
    let redirectHits = 0, backendHits = 0, credentialForwarded = false;
    const destination = await server((req, res) => {
      redirectHits++;
      credentialForwarded = req.headers[method === 'GET' ? 'x-nico-operator-session' : 'x-nico-admin-token'] === (method === 'GET' ? TOKEN : PASSWORD);
      res.writeHead(200, {'Content-Type': 'application/json'});
      res.end(JSON.stringify({status: 'authenticated', session_token: TOKEN, expires_in: 3600}));
    });
    let backend;
    try {
      backend = await server((_req, res) => {
        backendHits++;
        res.writeHead(307, {Location: `http://127.0.0.1:${destination.address().port}/redirect-target`}); res.end();
      });
      const api = load(fetch, {NODE_ENV: 'test', NICO_API_URL: `http://127.0.0.1:${backend.address().port}`});
      const response = await api[method](request());
      assert.equal(credentialForwarded, false, 'synthetic credential reached the second origin');
      assert.equal(redirectHits, 0, 'custom credential headers must never be forwarded to a redirect target');
      assert.equal(backendHits, 1);
      assert.equal(response.status, 503); assertRetained(response); assertPrivate(response);
    } finally {
      if (backend) await close(backend);
      await close(destination);
    }
  });
}
