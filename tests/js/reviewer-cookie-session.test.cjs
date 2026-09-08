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
const React = fromWeb('react');
function compile(filename) {
  return ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
}
function findAll(node, predicate) {
  if (!node || typeof node !== 'object') return [];
  if (typeof node.type === 'function') return findAll(node.type(node.props), predicate);
  return [...(predicate(node) ? [node] : []), ...React.Children.toArray(node.props?.children).flatMap(child => findAll(child, predicate))];
}
function page(name, fetchImpl, locale = 'en') {
  let cursor = 0, mounted = false;
  const state = [], effects = [];
  const location = new URL(`https://nico.test/operations/reviewer-queue?run_id=comprun_saved&lang=${locale}`);
  function load(filename) {
    const module = {exports: {}};
    vm.runInNewContext(compile(filename), {module, exports: module.exports, URL, URLSearchParams,
      window: {location}, document: {documentElement: {}}, fetch: fetchImpl,
      require(name) {
        if (name.endsWith('.css')) return {default: {}};
        if (name === 'react') return {...React,
          useState(initial) { const index = cursor++; if (!(index in state)) state[index] = initial; return [state[index], value => {state[index] = value;}]; },
          useEffect(effect) { if (!mounted) effects.push(effect); },
          useMemo(compute) { return compute(); },
        };
        return name.startsWith('.') ? load(path.resolve(path.dirname(filename), name + '.tsx')) : fromWeb(name);
      },
    }, {filename});
    return module.exports;
  }
  const Page = load(path.join(ROOT, 'apps/web/app/operations/reviewer-queue', name + '.tsx')).default;
  Page(); mounted = true; effects.forEach(effect => effect());
  const render = () => {cursor = 0; return Page();};
  return {render, find(predicate) {return findAll(render(), predicate);}};
}
for (const name of ['ReviewerQueue', 'ReviewQueueBrowser', 'ReviewWorkPanel']) {
  for (const status of [401, 403]) {
    test(`${name} saved run can request with cookie transport; ${status} remains an error`, async () => {
      const calls = [];
      const p = page(name, async (url, init) => {
        calls.push({url, init});
        return Response.json({detail: {code: 'specialist_authentication_required'}}, {status});
      });
      assert.equal(p.find(n => n.type === 'input' && n.props.type === 'password').length, 0);
      const load = p.find(n => n.type === 'button' && /^Load review/.test(String(n.props.children)))[0];
      assert.ok(load); assert.equal(load.props.disabled, false, 'saved session must not require a raw token');
      assert.equal(calls.length, 0, 'mount never submits a review');
      if (name === 'ReviewerQueue') await p.find(n => n.type === 'form')[0].props.onSubmit({preventDefault() {}});
      else await load.props.onClick();
      assert.equal(calls.length, 1);
      assert.match(String(calls[0].url), /\/api\/nico\/assessment\/comprehensive-run\/comprun_saved\/review-(queue|work)$/);
      assert.equal(calls[0].init.credentials, 'same-origin');
      assert.equal(new Headers(calls[0].init.headers).has('X-NICO-Admin-Token'), false);
      assert.equal(new Headers(calls[0].init.headers).has('X-NICO-Operator-Session'), false);
      assert.equal(calls[0].init.method || 'GET', 'GET');
      assert.equal(p.find(n => n.props.role === 'alert').length, 1);
      const link = p.find(n => n.type === 'a' && n.props.href.startsWith('/specialist-login?'))[0];
      const destination = new URL(link.props.href, 'https://nico.test').searchParams.get('returnTo');
      assert.equal(destination, '/operations/reviewer-queue?run_id=comprun_saved&lang=en');
    });
  }
}
test('review work cannot post without the human reviewer and role', async () => {
  let calls = 0;
  const p = page('ReviewWorkPanel', async () => {calls++; return Response.json({});});
  const form = p.find(n => n.type === 'form')[0];
  assert.ok(form);
  await form.props.onSubmit({preventDefault() {}});
  assert.equal(calls, 0);
});
for (const endpoint of ['review-queue', 'review-work']) {
  test(`${endpoint} proxy preserves missing-session and upstream scope denial`, async () => {
    const filename = path.join(ROOT, 'apps/web/app/api/nico/assessment/[...path]/route.ts');
    let calls = 0;
    const module = {exports: {}};
    vm.runInNewContext(compile(filename), {module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
      crypto: require('node:crypto').webcrypto,
      process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.test'}},
      fetch: async (url, init) => {
        calls++; assert.equal(init.headers.get('X-NICO-Operator-Session'), 'test-session');
        assert.equal(init.headers.has('X-NICO-Admin-Token'), false);
        return Response.json({detail: {code: 'production_proof_session_scope_forbidden'}}, {status: 403});
      },
    });
    const context = {params: Promise.resolve({path: ['comprehensive-run', 'comprun_saved', endpoint]})};
    const req = session => ({method: 'GET', headers: new Headers(), cookies: {get: () => session ? {value: session} : undefined}, nextUrl: new URL('https://nico.test')});
    assert.equal((await module.exports.GET(req(''), context)).status, 401);
    assert.equal(calls, 0);
    const denied = await module.exports.GET(req('test-session'), context);
    assert.equal(denied.status, 403);
    assert.equal((await denied.json()).detail.code, 'production_proof_session_scope_forbidden');
    assert.equal(calls, 1);
  });
}
for (const name of ['ReviewQueueBrowser', 'ReviewWorkPanel']) {
  test(`${name} renders authenticated review data and clears it on denied refresh`, async () => {
    let denied = false;
    const p = page(name, async () => denied
      ? Response.json({detail: 'session expired'}, {status: 401})
      : Response.json({run_id: 'comprun_saved', candidate_count: 7, dispositioned_candidate_count: 2, candidates: []}));
    await p.find(n => n.type === 'button' && /^Load review/.test(String(n.props.children)))[0].props.onClick();
    const refresh = p.find(n => n.type === 'button' && /^Refresh/.test(String(n.props.children)))[0];
    assert.ok(refresh, 'authenticated projection was rendered');
    denied = true;
    await refresh.props.onClick();
    assert.equal(p.find(n => n.type === 'button' && /^Refresh/.test(String(n.props.children))).length, 0);
    assert.equal(p.find(n => n.props.role === 'alert').length, 1);
  });
}
test('explicit human work submission retains reviewer and decision payload with cookie transport', async () => {
  const calls = [];
  const p = page('ReviewWorkPanel', async (url, init) => {calls.push({url, init}); return Response.json({run_id: 'comprun_saved'});});
  const inputFor = label => p.find(n => n.type === 'label' && React.Children.toArray(n.props.children).some(child => child === label))[0].props.children.find(child => child?.type === 'input');
  inputFor('Authorized reviewer').props.onChange({target: {value: 'Real test reviewer'}});
  inputFor('Reviewer / specialist role').props.onChange({target: {value: 'Security specialist'}});
  assert.equal(calls.length, 0, 'entering identity is not submission');
  await p.find(n => n.type === 'form')[0].props.onSubmit({preventDefault() {}});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.equal(new Headers(calls[0].init.headers).has('X-NICO-Admin-Token'), false);
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.reviewer, 'Real test reviewer');
  assert.equal(body.reviewer_role, 'Security specialist');
  assert.equal(body.action, 'disposition_candidate');
  assert.equal(body.authorization_confirmed, true);
  assert.equal(body.review_authorized, true);
});

function mutationProxy(fetchImpl) {
  const filename = path.join(ROOT, 'apps/web/app/api/nico/assessment/[...path]/route.ts');
  const module = {exports: {}};
  vm.runInNewContext(compile(filename), {module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
    crypto: require('node:crypto').webcrypto,
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.test'}}, fetch: fetchImpl,
  });
  return module.exports;
}
function mutationRequest({cookie = 'test-session', origin = 'https://nico.test', session = '', admin = ''} = {}) {
  const headers = new Headers({'Content-Type': 'application/json'});
  if (origin !== undefined && origin !== '') headers.set('Origin', origin);
  if (session) headers.set('X-NICO-Operator-Session', session);
  if (admin) headers.set('X-NICO-Admin-Token', admin);
  return {method: 'POST', headers, cookies: {get: () => cookie ? {value: cookie} : undefined},
    nextUrl: new URL('https://nico.test/api/nico/assessment/comprehensive-run/comprun_saved/review-work'),
    arrayBuffer: async () => new TextEncoder().encode('{"action":"request_evidence"}').buffer};
}
const mutationContext = () => ({params: Promise.resolve({path: ['comprehensive-run', 'comprun_saved', 'review-work']})});
for (const origin of ['', 'null', 'not-an-origin', 'https://nico.test.attacker.test', 'https://sibling.nico.test', 'http://nico.test', 'https://nico.test:444', 'https://nico.test/']) {
  test(`cookie mutation rejects untrusted or missing Origin ${JSON.stringify(origin)} before upstream`, async () => {
    const api = mutationProxy(async () => assert.fail('untrusted cookie mutation reached upstream'));
    const result = await api.POST(mutationRequest({origin}), mutationContext());
    assert.equal(result.status, 403);
    const body = await result.text();
    assert.equal(body.includes('test-session'), false);
    assert.equal(result.headers.get('Cache-Control'), 'no-store, private, max-age=0');
  });
}
test('cookie mutation accepts exact same Origin while preserving session and body', async () => {
  let calls = 0;
  const api = mutationProxy(async (url, init) => {
    calls++; assert.equal(init.headers.get('X-NICO-Operator-Session'), 'test-session');
    assert.equal(init.headers.has('X-NICO-Admin-Token'), false);
    assert.equal(new TextDecoder().decode(init.body), '{"action":"request_evidence"}');
    return Response.json({status: 'test-only'});
  });
  assert.equal((await api.POST(mutationRequest(), mutationContext())).status, 200);
  assert.equal(calls, 1);
});
for (const credentials of [{session: 'api-session'}, {admin: 'api-admin'}]) {
  test(`header-only API mutation keeps its existing transport ${Object.keys(credentials)[0]}`, async () => {
    let calls = 0;
    const api = mutationProxy(async (url, init) => {
      calls++;
      assert.equal(init.headers.get(credentials.session ? 'X-NICO-Operator-Session' : 'X-NICO-Admin-Token'), credentials.session || credentials.admin);
      return Response.json({status: 'test-only'});
    });
    assert.equal((await api.POST(mutationRequest({cookie: '', origin: '', ...credentials}), mutationContext())).status, 200);
    assert.equal(calls, 1);
  });
}
test('conflicting cookie and header sessions still fail before upstream', async () => {
  const api = mutationProxy(async () => assert.fail('identity conflict reached upstream'));
  assert.equal((await api.POST(mutationRequest({session: 'different-session'}), mutationContext())).status, 409);
});

// Production 34288471305 retained the Markdown bytes but its same-origin response
// lost this upstream lifecycle fact. Exercise both shipped forwarding handlers.
for (const authenticated of [true, false]) {
  for (const completed of ['false', 'true', null]) {
    test(`report proxy preserves explicit review completion (${authenticated}, ${completed})`, async () => {
      const filename = path.join(ROOT, 'apps/web/app/api/nico', authenticated ? 'assessment/[...path]/route.ts' : '[...path]/route.ts');
      const module = {exports: {}};
      const upstreamHeaders = {'x-nico-client-delivery-allowed': 'false', 'x-nico-approval-status': 'pending_human_approval'};
      if (completed !== null) upstreamHeaders['x-nico-human-review-completed'] = completed;
      let calls = 0;
      vm.runInNewContext(compile(filename), {module, exports: module.exports, URL, Headers, Response, AbortSignal, DOMException,
        crypto: require('node:crypto').webcrypto,
        process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.test'}},
        fetch: async () => {calls++; return new Response('exact retained report bytes', {headers: upstreamHeaders});},
      });
      const segments = ['comprehensive-run', 'comprun_saved', 'report', 'markdown'];
      const response = await module.exports.GET({method: 'GET', headers: new Headers(),
        cookies: {get: () => ({value: 'synthetic-review-session'})}, nextUrl: new URL('https://nico.test')},
        {params: Promise.resolve({path: authenticated ? segments : ['assessment', ...segments]})});
      assert.equal(response.status, 200);
      assert.equal(calls, 1);
      assert.equal(response.headers.get('x-nico-human-review-completed'), completed);
      assert.equal(response.headers.get('x-nico-client-delivery-allowed'), 'false');
      assert.equal(response.headers.get('x-nico-approval-status'), 'pending_human_approval');
      assert.equal(await response.text(), 'exact retained report bytes');
    });
  }
}
