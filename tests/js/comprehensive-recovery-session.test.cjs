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
function nodes(n, predicate) {
  if (!n || typeof n !== 'object') return [];
  return [...(predicate(n) ? [n] : []), ...React.Children.toArray(n.props?.children).flatMap(x => nodes(x, predicate))];
}
function component(relative, props, fetchImpl, backend = 'https://backend.test') {
  let cursor = 0, mounted = false;
  const state = [], effects = [], cache = new Map();
  const location = new URL('https://nico.test/operations/recovery?run_id=comprun_saved');
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const module = {exports: {}};
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
    }}).outputText;
    vm.runInNewContext(compiled, {module, exports: module.exports, URL, URLSearchParams, window: {location},
      process: {env: {NEXT_PUBLIC_NICO_API_URL: backend}}, fetch: fetchImpl,
      require(name) {
        if (name.endsWith('.css')) return {default: {}};
        if (name === 'react') return {...React,
          useState(initial) {const i = cursor++; if (!(i in state)) state[i] = initial; return [state[i], v => {state[i] = v;}];},
          useEffect(effect) {if (!mounted) effects.push(effect);}, useMemo(fn) {return fn();},
        };
        if (!name.startsWith('.')) return fromWeb(name);
        const base = path.resolve(path.dirname(filename), name);
        const target = [base + '.tsx', base + '.ts'].find(fs.existsSync);
        return load(target);
      },
    }, {filename});
    cache.set(filename, module.exports);
    return module.exports;
  }
  const Component = load(path.join(ROOT, relative)).default;
  const render = () => {cursor = 0; return Component(props);};
  render(); mounted = true; effects.forEach(fn => fn());
  return {find: predicate => nodes(render(), predicate)};
}
const settle = () => new Promise(resolve => setImmediate(resolve));
for (const backend of ['https://backend.test', '']) {
  test(`Comprehensive recovery uses the existing session with backend config ${backend || 'absent'}`, async () => {
    const calls = [];
    const p = component('apps/web/app/operations/recovery/page.tsx', {}, async () => {}, backend);
    const child = p.find(n => typeof n.type === 'function' && n.type.name === 'ComprehensiveRecoveryPanel')[0];
    assert.ok(child);
    assert.equal(child.props.apiUrl, '/api/nico');
    assert.equal(p.find(n => n.type === 'button' && n.props.type === 'submit')[0].props.disabled, false);
    const run = {run_id:'comprun_saved', repository:'owner/repo', commit_sha:'a'.repeat(40), status:'blocked', terminal:true, client_delivery_allowed:false, current_stage:'repository_and_delivery_evidence'};
    const panel = component('apps/web/app/operations/ComprehensiveRecoveryPanel.tsx', child.props, async (url, init) => {calls.push({url,init}); return Response.json(run);});
    assert.equal(calls.length, 0, 'mount must not resume automatically');
    panel.find(n => n.type === 'button' && n.props.children === 'Reload exact run state')[0].props.onClick();
    await settle();
    assert.equal(calls[0].url, '/api/nico/assessment/comprehensive-run/comprun_saved');
    assert.equal(calls[0].init.credentials, 'same-origin');
    const resume = panel.find(n => n.type === 'button' && n.props.children === 'Resume same Comprehensive run ID')[0];
    assert.equal(resume.props.disabled, false);
    resume.props.onClick(); await settle();
    assert.equal(calls[1].url, '/api/nico/assessment/comprehensive-run/comprun_saved/continue');
    assert.equal(calls[1].init.credentials, 'same-origin');
    assert.equal(calls[1].init.method, 'POST');
    assert.equal(calls[1].init.body, '{"max_stages":1}');
    assert.equal(new Headers(calls[1].init.headers).has('X-NICO-Admin-Token'), false);
    assert.equal(panel.find(n => n.props['data-delivery-state'] === 'blocked').length, 1);
  });
}
for (const status of [401,403]) {
  test(`denied recovery ${status} cannot enable continuation`, async () => {
    const p = component('apps/web/app/operations/ComprehensiveRecoveryPanel.tsx', {apiUrl:'/api/nico', targetRunId:'comprun_saved', refreshKey:''}, async () => Response.json({detail:{code:'specialist_authentication_required'}},{status}));
    p.find(n => n.type === 'button' && n.props.children === 'Reload exact run state')[0].props.onClick(); await settle();
    assert.equal(p.find(n => n.type === 'button' && n.props.children === 'Resume same Comprehensive run ID')[0].props.disabled, true);
  });
}

for (const allowed of [true, false]) {
  test(`private checkout requires explicit inspection and eligible exact identity (${allowed})`, async () => {
    const calls=[];
    const p=component('apps/web/app/operations/PrivateCheckoutRecovery.tsx', {runId:'comprun_saved',spanish:false,returnPath:'/assessment'}, async (url,init)=>{
      calls.push({url,init});
      return Response.json({run_id:'comprun_saved',scan_id:'scan_snapshot_saved',commit_sha:'a'.repeat(40),failure_fingerprint:'b'.repeat(64),retry_allowed:allowed});
    });
    assert.equal(calls.length,0);
    assert.equal(p.find(n=>n.type==='button').length,1);
    p.find(n=>n.type==='button')[0].props.onClick(); await settle();
    assert.equal(calls[0].init.method,'GET');
    assert.equal(calls[0].init.credentials,'same-origin');
    const retry=p.find(n=>n.type==='button' && n.props.children==='Retry this private checkout once');
    assert.equal(retry.length,allowed?1:0);
    if(allowed){
      retry[0].props.onClick(); await settle();
      assert.equal(calls[1].init.method,'POST');
      assert.deepEqual(JSON.parse(calls[1].init.body),{scan_id:'scan_snapshot_saved',commit_sha:'a'.repeat(40),failure_fingerprint:'b'.repeat(64)});
    }
  });
}
for (const response of [Response.json({retry_allowed:true},{status:403}),Response.json({run_id:'comprun_other',retry_allowed:true})]) {
  test('denied or mismatched private checkout cannot offer retry',async()=>{
    const p=component('apps/web/app/operations/PrivateCheckoutRecovery.tsx',{runId:'comprun_saved',spanish:false,returnPath:'/assessment'},async()=>response);
    p.find(n=>n.type==='button')[0].props.onClick(); await settle();
    assert.equal(p.find(n=>n.type==='button').length,1);
  });
}
