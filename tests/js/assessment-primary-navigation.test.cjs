const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');

function navigation(initialUrl) {
  const state = [], effects = [], listeners = new Map();
  let index = 0, first = true;
  const window = {location: new URL(initialUrl),
    addEventListener(name, callback) { listeners.set(name, callback); },
    removeEventListener(name) { listeners.delete(name); }};
  window.history = {replaceState(_state, _title, url) {
    window.location = new URL(url, window.location);
    // Native replaceState does not dispatch popstate.
  }};
  const module = {exports: {}};
  const jsx = (type, props) => typeof type === 'function' ? type(props) : {type, props};
  const source = fs.readFileSync(path.join(root, 'apps/web/app/PrimaryNavigation.tsx'), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  vm.runInNewContext(code, {module, exports: module.exports, window, URL, URLSearchParams,
    require(name) {
      if (name === 'react') return {
        useState(value) { const slot = index++; if (!(slot in state)) state[slot] = value;
          return [state[slot], next => { state[slot] = next; }]; },
        useEffect(callback) { if (first) effects.push(callback); },
      };
      if (name === 'react/jsx-runtime') return {jsx, jsxs: jsx};
      if (name === 'next/navigation') return {usePathname: () => window.location.pathname};
      if (name === './OperatorWorkspaceLocale') return {default: () => null};
      if (name === './assessment/assessmentLocale') return {
        localePreservingHref: () => '/locale-fixture', persistUiLocale() {},
      };
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value)
    ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
  function render() { index = 0; return module.exports.default(); }
  render(); effects.forEach(callback => callback()); first = false;
  const links = nodes(render()).filter(node => node.type === 'a' &&
    (node.props.className === 'global-brand' || node.props['data-service'] === 'run-job'));
  assert.equal(links.length, 2);
  return {window, links};
}

for (const route of ['/assessment', '/es/assessment']) {
  for (const event of ['onFocus', 'onPointerDown', 'onClick']) {
    for (const action of ['new-run', 'reset']) {
      test(`${route}: ${event} refreshes both primary destinations after ${action} replaceState`, () => {
        const fixture = navigation(`https://nico.invalid${route}?tier=comprehensive&run_id=comprun_old#assessment`);
        const query = action === 'new-run'
          ? '?tier=comprehensive&run_id=comprun_new&report_locale=es-MX'
          : '?tier=comprehensive&new_assessment=123&report_locale=en-US';
        fixture.window.history.replaceState(null, '', `${route}${query}#evidence`);
        for (const link of fixture.links) {
          let href = link.props.href;
          assert.ok(href.includes('comprun_old'), 'fixture starts with the previously rendered run');
          assert.equal(typeof link.props[event], 'function', 'primary destination needs live URL refresh');
          link.props[event]({currentTarget: {setAttribute(name, value) {
            assert.equal(name, 'href'); href = value;
          }}});
          const target = new URL(href, fixture.window.location);
          assert.equal(target.pathname, route);
          assert.equal(target.hash, '#evidence');
          assert.equal(target.searchParams.get('run_id'), action === 'new-run' ? 'comprun_new' : null);
          assert.equal(target.searchParams.get('new_assessment'), action === 'reset' ? '123' : null);
          assert.equal(target.searchParams.get('report_locale'), action === 'new-run' ? 'es-MX' : 'en-US');
          assert.equal(target.searchParams.get('tier'), 'comprehensive');
        }
      });
    }
  }
}

test('primary destination uses live explicit Spanish locale and keeps the exact run', () => {
  const fixture = navigation('https://nico.invalid/assessment?tier=comprehensive');
  fixture.window.history.replaceState(null, '', '/assessment?lang=es-MX&run_id=comprun_live');
  for (const link of fixture.links) {
    let href;
    assert.equal(typeof link.props.onClick, 'function');
    link.props.onClick({currentTarget: {setAttribute(_name, value) { href = value; }}});
    const target = new URL(href, fixture.window.location);
    assert.equal(target.pathname, '/es/assessment');
    assert.equal(target.searchParams.get('run_id'), 'comprun_live');
    assert.equal(target.searchParams.has('lang'), false);
    assert.equal(target.hash, '#assessment');
  }
});
