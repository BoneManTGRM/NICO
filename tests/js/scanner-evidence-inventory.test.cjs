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

// Execute the page's mount effect and language button with an isolated location;
// locale navigation must preserve recovery identity and never issue a request.
function inventoryPage(href) {
  let location = new URL(href);
  let cursor = 0;
  let mounted = false;
  const state = [], effects = [];
  const React = fromWeb('react');
  const window = {location: {
    get href() { return location.href; }, get pathname() { return location.pathname; },
    get search() { return location.search; }, get hash() { return location.hash; },
    assign(value) { location = new URL(value, location); },
  }};
  function loadTs(filename) {
    const module = {exports: {}};
    const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX},
    }).outputText;
    vm.runInNewContext(source, {module, exports: module.exports, URL, URLSearchParams, window,
      fetch: () => assert.fail('language navigation must not send a request'),
      require(name) {
        if (name === 'react') return {...React,
          useState(initial) { const slot = cursor++; if (!(slot in state)) state[slot] = initial; return [state[slot], value => {state[slot] = value;}]; },
          useEffect(effect) { if (!mounted) effects.push(effect); },
        };
        return name.startsWith('.') ? loadTs(path.resolve(path.dirname(filename), `${name}.ts`)) : fromWeb(name);
      },
    }, {filename});
    return module.exports;
  }
  const Page = loadTs(path.join(ROOT, 'apps/web/app/operations/scanner-evidence/page.tsx')).default;
  Page(); mounted = true; effects.forEach(effect => effect()); cursor = 0;
  const tree = Page();
  function find(node, predicate) {
    if (!node || typeof node !== 'object') return undefined;
    if (predicate(node)) return node;
    return React.Children.toArray(node.props?.children).map(child => find(child, predicate)).find(Boolean);
  }
  return {heading: find(tree, node => node.type === 'h1').props.children,
    runId: find(tree, node => node.props?.id === 'scanner-evidence-run').props.value,
    toggle: () => find(tree, node => node.type === 'button' && node.props.type === 'button').props.onClick(),
    href: () => location.href};
}

test('inventory follows global lang links while retaining the exact saved run', () => {
  const page = inventoryPage('https://app.nico.test/operations/scanner-evidence?run_id=comprun_locale&lang=es-MX');
  assert.equal(page.heading, 'Evidencia conservada de los analizadores');
  assert.equal(page.runId, 'comprun_locale');
  const primary = inventoryPage('https://app.nico.test/operations/scanner-evidence?run_id=comprun_locale&lang=en&language=es-MX');
  assert.equal(primary.heading, 'Retained scanner evidence', 'standard lang takes precedence over the legacy alias');
});

test('inventory language navigation persists across remount and preserves recovery query and hash', () => {
  for (const localeQuery of ['lang=es-MX', 'language=es-MX']) {
    const page = inventoryPage(`https://app.nico.test/operations/scanner-evidence?run_id=comprun_locale&${localeQuery}&report_locale=es-MX#saved`);
    page.toggle();
    const englishUrl = new URL(page.href());
    assert.equal(englishUrl.searchParams.has('lang'), false);
    assert.equal(englishUrl.searchParams.has('language'), false);
    assert.equal(englishUrl.searchParams.get('run_id'), 'comprun_locale');
    assert.equal(englishUrl.searchParams.get('report_locale'), 'es-MX');
    assert.equal(englishUrl.hash, '#saved');
    const english = inventoryPage(page.href());
    assert.equal(english.heading, 'Retained scanner evidence');
    assert.equal(english.runId, 'comprun_locale');
    english.toggle();
    assert.equal(new URL(english.href()).searchParams.get('lang'), 'es-MX');
    const spanish = inventoryPage(english.href());
    assert.equal(spanish.heading, 'Evidencia conservada de los analizadores');
    assert.equal(spanish.runId, 'comprun_locale');
  }
});

test('private checkout recovery forwards exact owner-session request with origin enforcement', async () => {
  const calls=[];
  const api=load(async(url,init)=>{calls.push({url,init});return Response.json({same_run_and_scan_preserved:true},{status:202});});
  const denied=await api.POST(request('POST'),context(['scanner-checkout-recovery']));
  assert.equal(denied.status,403); assert.equal(calls.length,0);
  const req=request('POST'); req.headers.set('origin',req.nextUrl.origin);
  const body=Buffer.from(JSON.stringify({scan_id:'scan_snapshot_test',commit_sha:'a'.repeat(40),failure_fingerprint:'b'.repeat(64)}));
  req.arrayBuffer=async()=>body;
  assert.equal((await api.POST(req,context(['scanner-checkout-recovery']))).status,202);
  assert.equal(calls.length,1);
  assert.equal(calls[0].url.pathname,'/assessment/comprehensive-run/comprun_test/scanner-checkout-recovery');
  assert.equal(calls[0].init.body,body);
  assert.equal(calls[0].init.headers.get('X-NICO-Operator-Session'),'synthetic-owner-session');
  assert.equal(calls[0].init.redirect,'manual');
});
