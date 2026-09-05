// Execute actual middleware/components; stub only framework hooks and I/O.
// This is a deterministic component harness, not authenticated browser proof.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(root, 'apps/web/package.json'));
const ts = fromWeb('typescript');

function load(file, globals = {}, mocks = {}, cache = new Map()) {
  file = path.resolve(root, file);
  if (cache.has(file)) return cache.get(file).exports;
  const module = {exports: {}};
  cache.set(file, module);
  const source = fs.readFileSync(file, 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const localRequire = (name) => {
    if (Object.hasOwn(mocks, name)) return mocks[name];
    if (name.startsWith('.')) {
      const target = path.resolve(path.dirname(file), name);
      return load(fs.existsSync(target) ? target : target + '.ts', globals, mocks, cache);
    }
    throw new Error('Unexpected dependency: ' + name);
  };
  vm.runInNewContext(compiled, {
    module, exports: module.exports, require: localRequire,
    URL, URLSearchParams, console, ...globals,
  }, {filename: file});
  return module.exports;
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  const children = [node.props?.children].flat(Infinity);
  for (const child of children) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}

const flush = async () => {
  await new Promise(setImmediate);
  await new Promise(setImmediate);
};
const query = (next) => '?' + new URLSearchParams({next});
const saved = (locale) => (locale === 'es' ? '/es' : '') +
  '/assessment?tier=comprehensive&run_id=comprun_test_saved&customer_id=test-client';
const fallback = (locale) => (locale === 'es' ? '/es' : '') +
  '/assessment?tier=comprehensive#assessment';

async function component(locale, search, {mode = 'post', rejectGet = false, denied = false} = {}) {
  const state = [], effects = [], navigations = [], calls = [], unhandled = [];
  let cursor = 0, mounted = false;
  const track = (error) => unhandled.push(error);
  process.on('unhandledRejection', track);
  const window = {location: {
    search,
    replace: (url) => navigations.push(['replace', url]),
    assign: (url) => navigations.push(['assign', url]),
  }};
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in state)) state[i] = initial;
      return [state[i], (value) => {state[i] = typeof value === 'function' ? value(state[i]) : value;}];
    },
    useEffect(effect) { if (!mounted) effects.push(effect); },
  };
  const jsx = (type, props) => ({type, props});
  const fetch = async (url, options) => {
    calls.push([url, options]);
    assert.equal(url, '/api/nico/operator-session', 'login must never start/approve an assessment');
    if (options.method === 'GET') {
      if (rejectGet) throw new Error('test-only network interruption');
      return {ok: mode === 'existing', status: mode === 'existing' ? 200 : 401};
    }
    assert.equal(options.method, 'POST');
    assert.equal(JSON.parse(options.body).password, 'test-only-password');
    return {ok: !denied, status: denied ? 403 : 200};
  };
  try {
    const file = 'apps/web/app/' + (locale === 'es' ? 'es/' : '') + 'specialist-login/page.tsx';
    const Page = load(file, {window, document: {documentElement: {}}, fetch}, {
      react, 'react/jsx-runtime': {jsx, jsxs: jsx},
    }).default;
    const render = () => { cursor = 0; const tree = Page(); mounted = true; return tree; };
    let tree = render();
    effects.forEach((effect) => effect());
    await flush();
    tree = render();
    if (mode === 'post') {
      find(tree, (node) => node.type === 'input').props.onChange({target: {value: 'test-only-password'}});
      tree = render();
      await find(tree, (node) => node.type === 'form').props.onSubmit({preventDefault() {}});
      await flush();
      tree = render();
    }
    return {navigations, calls, unhandled, tree};
  } finally {
    process.off('unhandledRejection', track);
  }
}

function middlewareResponse(target, cookie) {
  const {middleware} = load('apps/web/middleware.ts', {}, {'next/server': {
    NextResponse: {next: () => ({next: true}), redirect: (url) => ({url: url.toString()})},
  }});
  const url = new URL(target, 'https://app.nicoaudit.com');
  url.clone = () => new URL(url);
  return middleware({nextUrl: url, cookies: {get: () => cookie ? {value: cookie} : undefined}});
}

async function main() {
  const [kind, locale = 'en'] = process.argv[2].split(':');
  const target = saved(locale);
  if (kind === 'middleware') {
    const response = middlewareResponse(target);
    const login = new URL(response.url);
    assert.equal(login.pathname, (locale === 'es' ? '/es' : '') + '/specialist-login');
    assert.equal(login.searchParams.get('next'), target, 'login redirect must preserve the exact saved run');
    const result = await component(locale, login.search);
    assert.equal(result.navigations[0]?.[1], target);
  } else if (kind === 'routes') {
    for (const route of ['/operations', '/es/operations', '/operator', '/final-review',
      '/coverage-targets', '/setup-readiness', '/setup-actions', '/assessment/child']) {
      const next = route + '?run_id=comprun_test_saved';
      assert.equal(new URL(middlewareResponse(next).url).searchParams.get('next'), next);
    }
  } else if (kind === 'cookie') {
    assert.equal(middlewareResponse(target, 'opaque-test-only-cookie').next, true);
  } else if (kind === 'existing' || kind === 'post') {
    const result = await component(locale, query(target), {mode: kind});
    assert.equal(result.navigations.length, 1);
    assert.equal(result.navigations[0][0], kind === 'existing' ? 'replace' : 'assign');
    assert.equal(result.navigations[0][1], target, 'successful login must restore the requested run');
  } else if (kind === 'language') {
    const result = await component(locale, query(target), {mode: 'form'});
    const link = find(result.tree, (node) => node.type === 'a');
    const href = new URL(link.props.href, 'https://app.nicoaudit.com');
    const other = locale === 'es' ? 'en' : 'es';
    assert.equal(href.pathname, (other === 'es' ? '/es' : '') + '/specialist-login');
    assert.equal(href.searchParams.get('next'), saved(other), 'language switch must retain saved-run identity');
    const resumed = await component(other, href.search);
    assert.equal(resumed.navigations[0]?.[1], saved(other));
  } else if (kind === 'network') {
    const result = await component(locale, query(target), {mode: 'form', rejectGet: true});
    assert.equal(result.unhandled.length, 0, 'session-check failure must not escape as an unhandled rejection');
    assert.equal(result.navigations.length, 0);
    assert.ok(find(result.tree, (node) => node.type === 'form'));
  } else if (kind === 'denied') {
    const result = await component(locale, query(target), {denied: true});
    assert.equal(result.navigations.length, 0);
    assert.ok(find(result.tree, (node) => node.props?.role === 'alert'));
    assert.equal(find(result.tree, (node) => node.type === 'button').props.disabled, false);
  } else if (kind === 'default') {
    const result = await component(locale, '');
    assert.equal(result.navigations[0]?.[1], fallback(locale));
  } else if (kind === 'nested') {
    for (const next of ['/operations/queue?run_id=one#review', '/operator', '/final-review?run_id=one',
      '/coverage-targets', '/setup-actions', '/setup-readiness', '/es/operations/queue?run_id=one']) {
      const result = await component(locale, query(next));
      assert.equal(result.navigations[0]?.[1], next);
    }
  } else if (kind === 'duplicate') {
    const result = await component(locale, query(target) + '&next=' + encodeURIComponent('/operator'));
    assert.equal(result.navigations[0]?.[1], fallback(locale));
  } else if (kind === 'unsafe') {
    for (const next of ['https://evil.invalid/assessment', '//evil.invalid/assessment', '/\\evil.invalid',
      'javascript:alert(1)', 'data:text/html,test', '%2f%2fevil.invalid', '/%2f%2fevil.invalid',
      '/assessment/../operator', '/assessment/%2e%2e/operator', '/specialist-login',
      '/api/nico/operator-session', '/assessment-evil', '/assessment\\../operator',
      '/assessment\n?run_id=one', '/assessment?x=' + 'x'.repeat(8192)]) {
      for (const mode of ['existing', 'post']) {
        const result = await component(locale, query(next), {mode});
        assert.equal(result.navigations[0]?.[1], fallback(locale), 'unsafe destination: ' + JSON.stringify(next.slice(0, 80)));
      }
    }
  } else {
    throw new Error('Unknown case ' + kind);
  }
  console.log('PASS ' + process.argv[2]);
}
main().catch((error) => {console.error(error); process.exitCode = 1;});
