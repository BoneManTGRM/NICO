'use strict';

// Execute the shipped TS/TSX, replacing only framework/browser/network boundaries.
// These are deterministic unit tests, not a claim of real specialist authentication.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '../..');
const WEB = path.join(ROOT, 'apps/web');
const ts = require(require.resolve('typescript', {paths: [WEB, ...module.paths]}));

function loadSource(filename, bindings, cache = new Map()) {
  filename = path.resolve(filename);
  if (cache.has(filename)) return cache.get(filename).exports;
  const mod = {exports: {}};
  cache.set(filename, mod);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
    reportDiagnostics: true,
  });
  assert.equal((output.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  const sandbox = {
    URL, URLSearchParams, console, ...bindings.globals,
    module: mod, exports: mod.exports,
    require(name) {
      if (Object.hasOwn(bindings.modules, name)) return bindings.modules[name];
      assert.ok(name.startsWith('.'), `Unexpected external dependency: ${name}`);
      const base = path.resolve(path.dirname(filename), name);
      const found = [base, `${base}.ts`, `${base}.tsx`].find(p => fs.existsSync(p) && fs.statSync(p).isFile());
      assert.ok(found, `Missing production import: ${name}`);
      return loadSource(found, bindings, cache);
    },
  };
  vm.runInNewContext(output.outputText, sandbox, {filename});
  return mod.exports;
}

class RequestUrl extends URL {
  clone() { return new RequestUrl(this.href); }
}
const nextBoundary = {
  NextResponse: {
    next: () => new Response(null, {headers: {'x-middleware-next': '1'}}),
    redirect: url => new Response(null, {status: 307, headers: {location: url.toString()}}),
  },
};
function redirectFor(destination, hasCookie = false) {
  const {middleware} = loadSource(path.join(WEB, 'middleware.ts'), {globals: {}, modules: {'next/server': nextBoundary}});
  return middleware({nextUrl: new RequestUrl(destination, 'https://nico.test'), cookies: {get: () => hasCookie ? {value: 'test-cookie'} : undefined}});
}
function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return undefined;
  if (predicate(tree)) return tree;
  const children = tree.props?.children;
  for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
    const result = find(child, predicate);
    if (result) return result;
  }
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const queryFor = value => '?' + new URLSearchParams({returnTo: value});

function loginPage(locale, search, options = {}) {
  const states = [], effects = [], navigation = [], requests = [];
  let cursor = 0, mounted = false;
  const globals = {
    window: {location: {search, assign: value => navigation.push(['assign', value]), replace: value => navigation.push(['replace', value])}},
    document: {documentElement: {lang: 'en'}},
    fetch: (url, init) => {
      requests.push({url, ...init});
      if (init.method === 'GET' && options.getError) return Promise.reject(new Error('session check unavailable'));
      const status = init.method === 'GET' ? (options.getStatus ?? 401) : (options.postStatus ?? 200);
      return Promise.resolve({ok: status >= 200 && status < 300, status});
    },
  };
  const jsx = (type, props) => ({type, props});
  const modules = {
    react: {
      useState(initial) {
        const i = cursor++;
        if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial;
        return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value; }];
      },
      useEffect(effect) { if (!mounted) effects.push(effect); },
    },
    'react/jsx-runtime': {jsx, jsxs: jsx, Fragment: 'fragment'},
  };
  const file = locale === 'es' ? 'app/es/specialist-login/page.tsx' : 'app/specialist-login/page.tsx';
  const Component = loadSource(path.join(WEB, file), {globals, modules}).default;
  function render() { cursor = 0; const tree = Component(); mounted = true; return tree; }
  render();
  return {
    navigation, requests, globals, render,
    async mount() { effects.forEach(effect => effect()); await settle(); },
    async submit() {
      find(render(), node => node.type === 'input').props.onChange({target: {value: 'test-only-password'}});
      await find(render(), node => node.type === 'form').props.onSubmit({preventDefault() {}});
    },
  };
}

const SAVED = '/assessment?tier=comprehensive&run_id=comprun_saved_fixture';
const PROTECTED = ['/assessment', '/es/assessment', '/operations', '/es/operations', '/operator', '/final-review', '/coverage-targets', '/setup-readiness', '/setup-actions'];
for (const prefix of PROTECTED) {
  test(`middleware preserves the exact destination for ${prefix}`, () => {
    const destination = `${prefix}?tier=comprehensive&run_id=comprun_saved_fixture&tag=a%2Bb`;
    const response = redirectFor(destination);
    assert.equal(response.status, 307);
    const location = new URL(response.headers.get('location'));
    assert.equal(location.origin, 'https://nico.test');
    assert.equal(location.pathname, prefix.startsWith('/es/') ? '/es/specialist-login' : '/specialist-login');
    assert.equal(location.searchParams.get('returnTo'), destination);
    assert.equal(location.searchParams.size, 1);
  });
}
test('middleware leaves cookie-bearing requests at the existing authentication boundary', () => {
  assert.equal(redirectFor(SAVED, true).headers.get('x-middleware-next'), '1');
});

const UNSAFE = [
  'https://evil.example/x', '//evil.example/x', '///evil.example/x', '/\\evil.example/x',
  'javascript:alert(1)', 'data:text/html,x', '%2F%2Fevil.example', '/%2fevil.example',
  '/%5cevil.example', '/assessment/../../evil', '/assessment/%2e%2e/%2e%2e/evil',
  '/assessment\\..\\evil', '/specialist-login', '/es/specialist-login', '/api/nico/operator-session',
  '/assessment-other', ' /assessment', '/assessment\n', '/assessment?x=%0d%0aLocation:evil',
  '/assessment?x=\t', '/assessment/%252e%252e/evil', '/assessment?x=%',
];
for (const locale of ['en', 'es']) {
  const fallback = `${locale === 'es' ? '/es' : ''}/assessment?tier=comprehensive#assessment`;
  const target = `${locale === 'es' ? '/es' : ''}${SAVED}&note=a%2Bb#review`;
  test(`${locale}: fresh login returns to the saved assessment without a new intake`, async () => {
    const page = loginPage(locale, queryFor(target));
    await page.mount(); await page.submit();
    assert.deepEqual(page.navigation, [['assign', target]]);
    assert.deepEqual(page.requests.map(r => [r.url, r.method]), [['/api/nico/operator-session', 'GET'], ['/api/nico/operator-session', 'POST']]);
    assert.equal(page.requests[1].body, JSON.stringify({password: 'test-only-password'}));
    assert.equal(find(page.render(), n => n.type === 'input').props.value, '');
  });
  test(`${locale}: an existing valid session returns to the same saved assessment`, async () => {
    const page = loginPage(locale, queryFor(target), {getStatus: 200});
    await page.mount();
    assert.deepEqual(page.navigation, [['replace', target]]);
    assert.equal(page.requests.length, 1);
  });
  test(`${locale}: switching login language preserves the saved destination`, async () => {
    const page = loginPage(locale, queryFor(target)); await page.mount();
    const link = new URL(find(page.render(), n => n.type === 'a').props.href, 'https://nico.test');
    assert.equal(link.pathname, locale === 'es' ? '/specialist-login' : '/es/specialist-login');
    assert.equal(link.searchParams.get('returnTo'), target);
  });
  test(`${locale}: bad passwords do not navigate or discard the password`, async () => {
    const page = loginPage(locale, queryFor(target), {postStatus: 403});
    await page.mount(); await page.submit();
    assert.deepEqual(page.navigation, []);
    assert.equal(find(page.render(), n => n.type === 'input').props.value, 'test-only-password');
    assert.ok(find(page.render(), n => n.props?.role === 'alert'));
    assert.equal(find(page.render(), n => n.type === 'button').props.disabled, false);
  });
  test(`${locale}: a failed session check leaves manual login usable without an unhandled rejection`, async () => {
    const page = loginPage(locale, queryFor(target), {getError: true});
    await page.mount(); await page.submit();
    assert.deepEqual(page.navigation, [['assign', target]]);
  });
  for (const value of UNSAFE) {
    test(`${locale}: rejects unsafe return target ${JSON.stringify(value)} at both navigation seams`, async () => {
      const page = loginPage(locale, queryFor(value), {getStatus: 200});
      await page.mount(); await page.submit();
      assert.deepEqual(page.navigation, [['replace', fallback], ['assign', fallback]]);
      const link = new URL(find(page.render(), n => n.type === 'a').props.href, 'https://nico.test');
      assert.notEqual(link.searchParams.get('returnTo'), value);
    });
  }
  for (const search of ['', '?returnTo=', `${queryFor(target)}&returnTo=%2Foperations`]) {
    test(`${locale}: missing, empty, or ambiguous destination uses the locale fallback: ${search}`, async () => {
      const page = loginPage(locale, search, {getStatus: 200});
      await page.mount(); await page.submit();
      assert.deepEqual(page.navigation, [['replace', fallback], ['assign', fallback]]);
    });
  }
  for (const destination of ['/operations?run_id=comprun_saved_fixture', '/final-review?run_id=comprun_saved_fixture#review', '/assessment?note=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1']) {
    test(`${locale}: permits internal protected destinations and encoded query data: ${destination}`, async () => {
      const page = loginPage(locale, queryFor(destination));
      await page.mount(); await page.submit();
      assert.deepEqual(page.navigation, [['assign', destination]]);
    });
  }
}
