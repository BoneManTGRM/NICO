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
const {sectionPresentation, toneKey} = modules('assessmentStatus.ts');
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
function workspace({locale = 'en', scanner = 'complete', running = true, report = false, compactMobile = false, phase = null, issue = null, sections = null} = {}) {
  const result = {run_id: 'comprun_presentation_fixture', commit_sha: commit, terminal: !running,
    current_stage: 'cross_format_truth_verification', human_review_required: true, client_delivery_allowed: false,
    record: {stage_results: {dependency_security_static_analysis: {status: scanner}}},
    assessment: {executive_summary: headline + narrative, maturity_signal: {level: 'Exceptional', score: 93},
      sections: sections || [{id: 'code_audit', score: 96, status: 'strong'}]},
    ...(report ? {reports: {report_id: 'report_fixture', pdf_available: true}} : {})};
  const controller = {service: 'comprehensive', repository: 'owner/control', client: '', project: '',
    authorized: true, humanEvidence: {}, engagementFieldStates: {client_name: {state: 'not_supplied'}, project_name: {state: 'not_supplied'}}, phase: phase || (running ? 'running' : 'review_required'),
    result, running, protectedRunId: result.run_id, message: '', error: '', issue, attempt: 1, elapsed: 1};
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
  test(`${locale}: pending section assurance and risk stay cautionary without changing lifecycle colors`, () => {
    const copy = copyFor(locale);
    for (const status of ['review_required', 'Review Required', 'review-required', 'human_review_required']) {
      const view = sectionPresentation({score: 96, assurance_status: status, risk_disposition: status}, copy);
      assert.equal(view.assuranceLabel, copy.phases.review_required);
      assert.equal(view.riskLabel, copy.phases.review_required);
      assert.equal(view.assuranceTone, 'yellow');
      assert.equal(view.riskTone, 'yellow');
    }
    assert.equal(toneKey('review_required'), 'green', 'completed draft lifecycle color remains unchanged');
    assert.equal(sectionPresentation({risk_disposition: 'critical'}, copy).riskTone, 'red');
    assert.equal(sectionPresentation({risk_disposition: 'unknown'}, copy).riskTone, 'gray');
  });
  test(`${locale}: retained evidence linkage and required human review have distinct localized assurance`, () => {
    const copy = copyFor(locale);
    const linked = sectionPresentation({score: 96, status: 'strong', assurance_status: 'evidence_bound'}, copy);
    assert.equal(linked.assuranceLabel, locale === 'en' ? 'Evidence linked' : 'Vinculada a evidencia');
    assert.equal(linked.assuranceTone, 'gray');
    assert.notEqual(linked.assuranceLabel, copy.verifiedLabel);
    const review = sectionPresentation({score: 96, status: 'strong', assurance_status: 'human_review_required'}, copy);
    assert.equal(review.assuranceLabel, copy.phases.review_required);
    assert.equal(review.assuranceTone, 'yellow');
    assert.equal(sectionPresentation({score: 96, assurance_label: 'review_limited'}, copy).assuranceLabel, copy.reviewLimitedLabel);
  });
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

test('bilingual workspace has no English-only generation exclusion', () => {
  for (const locale of ['en', 'es-MX']) {
    const tree=workspace({locale});
    const hero=nodes(tree).find(n=>n.type==='section' && String(n.props.className).includes('hero'));
    assert.doesNotMatch(text(hero), /unavailable for now|no está disponible por ahora/);
    assert.ok(!nodes(hero).some(n=>n.type==='button' && /Use English report|Usar informe en inglés/.test(text(n))));
  }
});

for (const locale of ['en', 'es-MX']) {
  for (const status of ['__proto__', 'constructor']) {
    test(`${locale}: inherited-name assessment statuses render as unknown text`, () => {
      const React = fromWeb('react');
      const {renderToStaticMarkup} = fromWeb('react-dom/server');
      const copy = copyFor(locale);
      const section = Object.freeze({score: 96, assurance_status: status, risk_disposition: status});
      const before = JSON.stringify(section);
      const view = sectionPresentation(section, copy);
      const expected = locale === 'es-MX' ? copy.unknownStatus : status === '__proto__' ? 'Proto' : 'Constructor';
      const rendered = renderToStaticMarkup(React.createElement('div', null,
        React.createElement('span', null, view.assuranceLabel),
        React.createElement('span', null, view.riskLabel)));
      assert.equal(view.assuranceLabel, expected);
      assert.equal(view.riskLabel, expected);
      assert.ok(rendered.includes(expected));
      assert.equal(view.assuranceTone, 'gray');
      assert.equal(view.riskTone, 'gray');
      assert.equal(view.score, '96/100');
      assert.equal(JSON.stringify(section), before);
    });
  }
}

for (const locale of ['en', 'es-MX']) {
  test(`${locale}: browser poll pause badge stays distinct from server timeout`, () => {
    const copy = copyFor(locale);
    const paused = workspace({locale, running: false, phase: 'timed_out', issue: {
      code: 'assessment_poll_budget_exhausted', runCreated: true, retryable: true,
      title: copy.pollingPausedTitle, message: copy.pollingPausedMessage,
    }});
    const badges = nodes(paused).filter(n => n.type === 'span').map(text);
    assert.ok(badges.includes(copy.pollingPausedTitle));
    assert.ok(!badges.includes(copy.phases.timed_out));
    const timeout = workspace({locale, running: false, phase: 'timed_out'});
    const serverBadges = nodes(timeout).filter(n => n.type === 'span').map(text);
    assert.ok(serverBadges.includes(copy.phases.timed_out));
    assert.ok(!serverBadges.includes(copy.pollingPausedTitle));
  });
}

test('exact generated static and unscored summaries translate without upgrading changed claims', () => {
  const summary = 'Static-analysis evidence is reported separately from analyzer execution coverage. TypeScript analysis completed with verified retained evidence for the exact commit.';
  assert.match(localizeExactSpanishText(summary), /TypeScript se completó/);
  assert.match(localizeExactSpanishText('Unscored controls are excluded from maturity; any resulting mean change is not evidence of improved source quality.'), /no demuestra una mejora/);
  assert.equal(localizeExactSpanishText(summary.replace('completed with verified', 'failed without verified')), null);
});

for (const locale of ['en', 'es-MX']) {
  test(`${locale}: architecture and delivery evidence remain visible without score invention`, () => {
    const render = modules('UnscoredSectionEvidence.tsx').default;
    for (const id of ['architecture_debt', 'velocity_complexity']) {
      const section = {id, score: null, presented_score: null, exclude_from_maturity: true,
        evidence: ['Files analyzed for complexity: 14 of 1140.', 'CC <= 20: 8/10'],
        unavailable: ['Retained exact-source score input unavailable.'],
        findings: ['Delivery capacity is not scored because architecture has no valid exact-source score input.'],
        score_input_provenance: {reason: 'measured_score_missing'},
        score_contract: {operational_trend: {commits_returned: 0, jobs_observed: 20, pull_requests_returned: null}}};
      const before = JSON.stringify(section);
      const output = render({section, locale});
      const content = text(output);
      for (const retained of [...section.evidence, ...section.unavailable, ...section.findings]) assert.ok(content.includes(retained));
      assert.match(content, locale === 'en' ? /Partial evidence remains partial/ : /La evidencia parcial sigue siendo parcial/);
      assert.match(content, locale === 'en' ? /human-review requirements/ : /requisitos de revisión humana/);
      if (id === 'velocity_complexity') {
        assert.match(content, locale === 'en' ? /not measured delivery velocity/ : /no mediciones de velocidad/);
        const values = nodes(output).filter(n => n.type === 'dd').map(text);
        assert.deepEqual(values, [], 'legacy counters have no availability provenance and must not become observed activity');
      }
      assert.equal(JSON.stringify(section), before);
      assert.equal(nodes(output).filter(n => ['button', 'input', 'form', 'a'].includes(n.type)).length, 0);
    }
  });
  test(`${locale}: missing and malformed measurements never become zeros or complete coverage`, () => {
    const render = modules('UnscoredSectionEvidence.tsx').default;
    for (const section of [
      {id: 'architecture_debt'},
      {id: 'architecture_debt', evidence: [null, {}, 0, ''], score_input_provenance: {reason: '__proto__'}},
      {id: 'velocity_complexity', score_contract: {operational_trend: {commits_returned: -1, jobs_observed: '20', merged_pull_requests: NaN, pull_requests_returned: 2.5}}},
    ]) {
      const output = render({section, locale});
      assert.match(text(output), locale === 'en' ? /No measurements are inferred/ : /No se infieren mediciones/);
      assert.equal(nodes(output).filter(n => n.type === 'dd').length, 0);
      assert.doesNotMatch(text(output), /100%|\[object Object\]|NaN/);
    }
    assert.equal(render({section: {id: 'code_audit', score: 96}, locale}), null);
  });
}

for (const locale of ['en', 'es-MX']) {
  test(`${locale}: installed workspace shows both evidence sections with null score badges`, () => {
    const sections = ['architecture_debt', 'velocity_complexity'].map(id => ({id, score: null, presented_score: null, exclude_from_maturity: true, evidence: ['Retained bounded population: 14/1140.']}));
    const output = workspace({locale, sections, running: false, report: true});
    assert.equal(nodes(output).filter(n => n.props?.['data-section-evidence']).length, 2);
    assert.match(text(output), /14\/1140/);
    assert.match(text(output), locale === 'en' ? /NOT SCORED/i : /SIN PUNTUACI/i);
    assert.equal(sections.every(s => s.score === null && s.exclude_from_maturity === true), true);
  });
}

test('legacy delivery contract default zeros are not represented as observed activity', () => {
  // _immutable_delivery_score({}, {}) uses int(source.get(key) or 0); these
  // are the actual empty-input contract values, not proof of zero activity.
  const section = {id: 'velocity_complexity', score_contract: {operational_trend: {
    commits_returned: 0, pull_requests_returned: 0, merged_pull_requests: 0,
    jobs_observed: 0, job_success_rate: undefined, score_effect: 'none'}}};
  for (const locale of ['en', 'es-MX']) {
    const output = modules('UnscoredSectionEvidence.tsx').default({section, locale});
    assert.equal(nodes(output).filter(n => n.type === 'dd').length, 0);
    assert.match(text(output), locale === 'en' ? /No measurements are inferred/ : /No se infieren mediciones/);
  }
});

for (const locale of ['en', 'es-MX']) {
  test(`${locale}: retained measurement table preserves missingness, provenance and review status`, () => {
    const records = [
      {label_en: 'Maximum CC', label_es: 'Complejidad máxima', value: 2, unit: 'CC', validation: 'partial'},
      {label_en: 'Nesting', label_es: 'Anidamiento', value: null, unit: 'levels', validation: 'unavailable'},
      {label_en: 'Hotspots', label_es: 'Puntos de complejidad', value: 50, unit: 'entries', validation: 'pending_review'},
    ].map(row => ({...row, population: 'partial:python:python_ast', provenance: 'source_function_measurements', commit_sha: 'a'.repeat(40)}));
    const section = {id: 'architecture_debt', score: null, exclude_from_maturity: true,
      score_input_provenance: {reason: 'measured_score_missing'},
      retained_measurements: {artifact_schema: 'nico.retained-section-measurements.v1', records}};
    const before = JSON.stringify(section);
    const output = modules('UnscoredSectionEvidence.tsx').default({section, locale});
    const content = text(output);
    assert.equal(nodes(output).filter(n => n.type === 'table').length, 1);
    assert.ok(content.includes('2 CC') && content.includes('50 entries'));
    assert.ok(content.includes('a'.repeat(40)) && content.includes('partial:python:python_ast'));
    assert.match(content, locale === 'en' ? /not a confirmed defect/ : /no es un defecto confirmado/);
    assert.match(content, locale === 'en' ? /Unavailable/ : /No disponible/);
    assert.ok(content.includes('complexity_evidence.complexity_score'));
    assert.equal(JSON.stringify(section), before);
    assert.equal(nodes(output).filter(n => ['button', 'input', 'form', 'a'].includes(n.type)).length, 0);
  });
}
