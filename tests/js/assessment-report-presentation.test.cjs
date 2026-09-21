// Synthetic presentation fixtures: real TS/TSX modules, no assessment or approval.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const ROOT = path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(ROOT, 'apps/web/package.json'));
const ts = fromWeb('typescript');
const DIR = path.join(ROOT, 'apps/web/app/assessment');
const commit = 'a'.repeat(40);
const narrative = `NICO completed a native Comprehensive Technical Assessment for owner/control at immutable commit ${commit}. The evidence-bound maturity signal is Exceptional (93/100). 7 client-review section(s) disclose unavailable, limited, or stakeholder-dependent evidence. Every automated stage represented in this package completed without a terminal execution failure. The package is a review-gated automated draft: automated evidence and recommendations are not client approval or delivery authorization.`;
const headline = 'Source/security evidence assurance: limited. Technical maturity is not a repository-wide security rating. Eligible source analyzed: 14 / 1140 (1.23%); observed supported source: 14 / 2401 (0.58%). Unsampled eligible files: 1126. ';

function loadModules(controller = {}, compactMobile = false) {
  const cache = new Map();
  const jsx = (type, props) => typeof type === 'function' ? type(props) : {type, props};
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename).exports;
    const module = {exports: {}};
    cache.set(filename, module);
    const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    }}).outputText;
    vm.runInNewContext(code, {module, exports: module.exports, console, URL, URLSearchParams,
      process: {env: {}}, window: {location: new URL('https://unit.invalid/assessment')},
      require(name) {
        if (name.endsWith('.css')) return {default: {}};
        if (name === 'react') return {useMemo: f => f(), useEffect() {}, useRef: v => ({current: v}),
          useState: v => [typeof v === 'function' ? v() : v, () => {}]};
        if (name === 'react/jsx-runtime') return {jsx, jsxs: jsx, Fragment: 'fragment'};
        if (name === './useAssessmentRun') return {useAssessmentRun: () => controller};
        if (name === './useAssessmentClientMode') return {useAssessmentClientMode: () => ({hydrated: true, compactMobile})};
        if (name === './StrategicEvidenceForm') return {default: () => null};
        if (!name.startsWith('.')) throw new Error(`Unexpected dependency: ${name}`);
        const base = path.resolve(path.dirname(filename), name);
        return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx');
      },
    }, {filename});
    return module.exports;
  }
  return name => load(path.join(DIR, name));
}
const modules = loadModules();
const {localizeExactSpanishText} = modules('AssessmentSpanishLocalization.ts');
const {sectionPresentation} = modules('assessmentStatus.ts');
const {copyFor} = modules('assessmentCopy.ts');
function text(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node !== 'object') return String(node);
  return Array.isArray(node) ? node.map(text).join(' ') : text(node.props?.children);
}
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  return Array.isArray(node) ? node.flatMap(nodes) : [node, ...nodes(node.props?.children)];
}
function workspace({locale = 'en', scanner = 'complete', running = true, report = false, compactMobile = false} = {}) {
  const result = {run_id: 'comprun_presentation_fixture', commit_sha: commit, terminal: !running,
    current_stage: 'cross_format_truth_verification', human_review_required: true, client_delivery_allowed: false,
    record: {stage_results: {dependency_security_static_analysis: {status: scanner}}},
    assessment: {executive_summary: headline + narrative, maturity_signal: {level: 'Exceptional', score: 93},
      sections: [{id: 'code_audit', score: 96, status: 'strong'}]},
    ...(report ? {reports: {report_id: 'report_fixture', pdf_available: true}} : {})};
  const controller = {service: 'comprehensive', repository: 'owner/control', client: '', project: '',
    authorized: true, humanEvidence: {}, engagementFieldStates: {client_name: {state: 'not_supplied'}, project_name: {state: 'not_supplied'}}, phase: running ? 'running' : 'review_required',
    result, running, protectedRunId: result.run_id, message: '', error: '', issue: null, attempt: 1, elapsed: 1};
  const render = loadModules(controller, compactMobile)('AssessmentWorkspace.tsx').default;
  return render({locale});
}

test('Spanish preserves both real sampled populations, limits, identity, and review boundary', () => {
  const output = localizeExactSpanishText(headline + narrative);
  assert.ok(output, 'the current coverage-prefixed summary must translate');
  for (const value of ['14 / 1140 (1.23%)', '14 / 2401 (0.58%)', '1126', commit, 'owner/control', '93/100']) assert.ok(output.includes(value), value);
  assert.match(output, /Garantía de evidencia de código y seguridad: limitada/);
  assert.match(output, /no es una calificación de seguridad/);
  assert.match(output, /no constituyen aprobación del cliente ni autorización de entrega/);
});
test('unverified scope and incomplete scanners do not become passing coverage', () => {
  const output = localizeExactSpanishText('Source/security evidence assurance: unverified. Technical maturity is not a repository-wide security rating. Scanner execution is incomplete. ' + narrative);
  assert.ok(output);
  assert.match(output, /no verificada/);
  assert.match(output, /ejecución de analizadores está incompleta/);
  assert.doesNotMatch(output, /100%|Código elegible analizado/);
});
test('supported scope, zero and unknown denominators retain their distinct meanings', () => {
  const output = localizeExactSpanishText('Source/security evidence assurance: available for the supported scope. Technical maturity is not a repository-wide security rating. Eligible source analyzed: 0 / 0 (unverified); observed supported source: None / None (unverified). ' + narrative);
  assert.ok(output);
  assert.match(output, /disponible para el alcance compatible/);
  assert.match(output, /0 \/ 0 \(no verificado\)/);
  assert.match(output, /no verificado \/ no verificado \(no verificado\)/);
  assert.doesNotMatch(output, /100%|sin muestrear/);
});
test('legacy summary still translates and unrecognized assurances fail closed', () => {
  assert.ok(localizeExactSpanishText(narrative));
  assert.equal(localizeExactSpanishText(headline.replace('limited.', 'fully secure.') + narrative), null);
  assert.equal(localizeExactSpanishText(headline + narrative + ' Approved for delivery.'), null);
});
for (const locale of ['en', 'es-MX']) {
  test(`${locale}: score bands never supply missing evidence assurance`, () => {
    for (const score of [20, 96]) {
      const section = {score, status: score > 80 ? 'strong' : 'critical', presented_status: 'STRONG'};
      const before = JSON.stringify(section);
      const view = sectionPresentation(section, copyFor(locale));
      assert.equal(view.score, `${score}/100`);
      assert.equal(view.assuranceLabel, copyFor(locale).notVerified);
      assert.equal(view.assuranceTone, 'gray');
      assert.equal(JSON.stringify(section), before);
    }
    assert.equal(sectionPresentation({score: 96, assurance_status: 'verified'}, copyFor(locale)).assuranceLabel, copyFor(locale).verifiedLabel);
    assert.equal(sectionPresentation({score: 96, assurance_status: 'review_limited', status: 'strong'}, copyFor(locale)).assuranceLabel, copyFor(locale).reviewLimitedLabel);
  });
  for (const compactMobile of [false, true]) {
    test(`${locale} ${compactMobile ? 'compact' : 'desktop'}: report progress follows scanner completion without granting approval`, () => {
      const copy = copyFor(locale);
      const tree = workspace({locale, compactMobile});
      const article = nodes(tree).find(n => n.type === 'article' && text(n).startsWith(copy.report + ' '));
      assert.ok(article, 'actual workspace package card is rendered');
      assert.ok(!text(article).includes(copy.awaitingScanner), text(article));
      assert.ok(!text(article).includes(copy.phases.complete), text(article));
      assert.match(text(tree), locale === 'en' ? /Internal approval required/ : /Requiere aprobación interna/);
      const waiting = nodes(workspace({locale, scanner: 'running', compactMobile})).find(n => n.type === 'article' && text(n).startsWith(copy.report + ' '));
      assert.ok(text(waiting).includes(copy.awaitingScanner));
      const complete = nodes(workspace({locale, running: false, report: true, compactMobile})).find(n => n.type === 'article' && text(n).startsWith(copy.report + ' '));
      assert.ok(text(complete).includes(copy.phases.complete));
    });
  }
}
test('the mounted Spanish workspace displays the preserved limited-assurance summary', () => {
  const tree = workspace({locale: 'es-MX', running: false, report: true});
  assert.match(text(tree), /14 \/ 1140 \(1.23%\)/);
  assert.doesNotMatch(text(tree), /No se devolvió un resumen ejecutivo localizado/);
});
