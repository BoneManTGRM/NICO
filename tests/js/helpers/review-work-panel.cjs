'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const ROOT = path.resolve(__dirname, '../../..');
const web = createRequire(path.join(ROOT, 'apps/web/package.json'));
const ts = web('typescript'), React = web('react');
const {renderToStaticMarkup} = web('react-dom/server');
const RUN = 'comprun_saved';
const ACTIONS = ['assign', 'disposition_candidate', 'disposition_group', 'quality_control', 'request_evidence',
  'resolve_evidence_request', 'stakeholder_evidence', 'start_session', 'stop_session', 'complete_empirical_study'];
function payload(change = {}) {
  return {run_id: RUN, repository: 'owner/repo', commit_sha: 'a'.repeat(40), evidence_ledger_id: 'ledger',
    candidate_count: 2, dispositioned_candidate_count: 1, remaining_candidate_count: 1,
    quality_control_required_count: 2, quality_control_completed_count: 1, open_evidence_request_count: 1,
    candidates: [{candidate_id: 'candidate_a'}, {candidate_id: 'candidate_b'}], clusters: [], queue_counts: {},
    workload_metrics: {}, quality_control_sampling: {}, unresolved_high_impact_candidate_ids: ['candidate_a'],
    ledger: {audit_events: [{action: 'quality_control', reviewer: 'Independent reviewer', recorded_at: 'timestamp',
      payload: {candidate_id: 'candidate_a', qc_outcome: 'disagree', qc_note: 'Retained QC note'}}],
    quality_control: {candidate_a: {qc_outcome: 'disagree', reviewer: 'Independent reviewer', qc_note: 'Retained QC note'}},
    evidence_requests: [{request_id: 'request_a', candidate_id: 'candidate_a', status: 'open', request_text: 'Exact proof', owner: 'Owner'},
      {request_id: 'request_b', candidate_id: 'candidate_b', status: 'resolved', resolution_note: 'Proof retained', evidence_references: ['evidence://one']}]},
    quality_control_blockers: {candidate_a: 'quality_control_disagreement'},
    empirical_measurement: {status: 'verified_within_four_hours', combined_specialist_hours: 3.5,
      four_combined_specialist_hours_empirically_proven: true},
    ready_for_final_approval: false, human_review_required: true, client_delivery_allowed: false, ...change};
}
function harness(locale, respond = () => Response.json(payload()), props = {}) {
  let cursor = 0, mounted = false;
  const state = [], effects = [], cache = new Map(), calls = [], changed = [], navigations = [];
  const location = {href: `https://nico.test/operations/reviewer-queue?run_id=${RUN}&lang=${locale}&keep=yes#work`,
    assign(value) {navigations.push(value);}};
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const module = {exports: {}};
    const source = fs.readFileSync(filename, 'utf8');
    const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX}}).outputText;
    vm.runInNewContext(code, {module, exports: module.exports, URL, URLSearchParams, window: {location},
      fetch: async (url, init) => {const call = {url, init}; calls.push(call); return respond(call);},
      require(name) {
        if (name.endsWith('.css')) return {default: new Proxy({}, {get: (_target, key) => String(key)})};
        if (name === 'react') return {...React,
          useState(initial) {const i = cursor++; if (!(i in state)) state[i] = initial;
            return [state[i], value => {state[i] = value;}];},
          useRef(initial) {const i = cursor++; if (!(i in state)) state[i] = {current: initial}; return state[i];},
          useEffect(effect) {if (!mounted) effects.push(effect);}, useMemo(fn) {return fn();}};
        if (!name.startsWith('.')) return web(name);
        const base = path.resolve(path.dirname(filename), name);
        return load(['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync));
      },
    }, {filename});
    cache.set(filename, module.exports); return module.exports;
  }
  const Panel = load(path.join(ROOT, 'apps/web/app/operations/reviewer-queue/ReviewWorkPanel.tsx')).default;
  const panelProps = {runId: RUN, onChanged: run => changed.push(run), ...props};
  function expand(node) {
    if (!node || typeof node !== 'object') return node;
    if (Array.isArray(node)) return node.map(expand);
    if (typeof node.type === 'function') return expand(node.type(node.props));
    return React.cloneElement(node, {}, ...React.Children.toArray(node.props.children).map(expand));
  }
  function render() {cursor = 0; return expand(Panel(panelProps));}
  render(); mounted = true; effects.forEach(effect => effect());
  function all(node, predicate) {
    if (!node || typeof node !== 'object') return [];
    return [...(predicate(node) ? [node] : []), ...React.Children.toArray(node.props.children).flatMap(child => all(child, predicate))];
  }
  const find = predicate => all(render(), predicate);
  const control = name => find(node => ['input', 'textarea', 'select'].includes(node.type) && node.props.value === name);
  return {calls, changed, navigations, render, find, control,
    html: () => renderToStaticMarkup(render()),
    async load() {await find(n => n.type === 'button' && n.props.onClick && /^(Load review|Cargar trabajo|Refresh|Actualizar)/.test(String(n.props.children)))[0].props.onClick();},
    action(value) {find(n => n.type === 'select')[0].props.onChange({target: {value}});},
    authorize() {const inputs = find(n => n.type === 'input'); inputs[1].props.onChange({target: {value: ' Reviewer '}}); inputs[2].props.onChange({target: {value: ' Specialist '}});},
    fill() {find(n => ['input', 'textarea'].includes(n.type) && !n.props.readOnly).forEach((n, i) => n.props.onChange({target: {value: ` field ${i} \n extra `}}));},
    async submit() {await find(n => n.type === 'form')[0].props.onSubmit({preventDefault() {}});},
  };
}
async function characterize() {
  const output = {};
  for (const locale of ['en', 'es-MX']) {
    const save = (name, h) => {output[`${locale}/${name}`] = JSON.parse(JSON.stringify({html: h.html(), calls: h.calls, changed: h.changed}));};
    const initial = harness(locale); save('initial', initial);
    const h = harness(locale); await h.load(); save('loaded', h); h.authorize();
    for (const action of ACTIONS) {h.action(action); h.fill(); save(`action/${action}`, h); await h.submit(); save(`submitted/${action}`, h);}
    const variants = {
      empty: {candidate_count: 0, dispositioned_candidate_count: 0, remaining_candidate_count: 0, candidates: [],
        quality_control_required_count: 0, quality_control_completed_count: 0, open_evidence_request_count: 0,
        ledger: {}, quality_control_blockers: {}, empirical_measurement: {}, unresolved_high_impact_candidate_ids: []},
      ready: {ready_for_final_approval: true, unresolved_high_impact_candidate_ids: []},
      malformedEscalations: {unresolved_high_impact_candidate_ids: 'candidate_a'},
      empiricalUnknown: {empirical_measurement: {status: 'future_status', combined_specialist_hours: 0, four_combined_specialist_hours_empirically_proven: 'true'}},
      empiricalOver: {empirical_measurement: {status: 'measured_over_four_hours', combined_specialist_hours: 4.1, four_combined_specialist_hours_empirically_proven: false}},
      malformedAudit: {ledger: {audit_events: {length: 99}}},
      wrongRun: {run_id: 'comprun_other'}, wrongSha: {commit_sha: 'invalid'}, delivery: {client_delivery_allowed: true},
      noReview: {human_review_required: false}, wrongCount: {candidate_count: 3}, invalidCandidates: {candidates: [{}]},
    };
    for (const [name, change] of Object.entries(variants)) {const h = harness(locale, () => Response.json(payload(change))); await h.load(); save(name, h);}
    for (const status of [401, 403, 500]) {const h = harness(locale, () => Response.json({detail: 'private backend detail'}, {status})); await h.load(); save(`error/${status}`, h);}
    let release;
    const busy = harness(locale, () => new Promise(resolve => {release = resolve;}));
    const pending = busy.load(); save('busy', busy); release(Response.json(payload())); await pending;
  }
  // Copy before later request arrays can change earlier observations.
  return JSON.parse(JSON.stringify(output));
}
module.exports = {harness, payload, characterize, ACTIONS, RUN};
