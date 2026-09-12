/**
 * Unit tests of the actual TSX handlers, not browser or production proof.
 * React hooks/DOM/network are isolated test doubles; SHA-256 uses real WebCrypto.
 * Run after npm ci in apps/web: node --test tests/frontend/final_review_approval.test.cjs
 */
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createHash, webcrypto} = require('node:crypto');
const ts = require(require.resolve('typescript', {paths: [path.resolve('apps/web'), __dirname]}));
const filename = path.resolve('apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx');
const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
  fileName: filename, reportDiagnostics: true,
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
});
assert.equal((compiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
function fixture(approved = false, operator = true) {
  const bytes = Buffer.from(`%PDF-1.7\nUNIT FIXTURE ONLY ${approved ? 'APPROVED' : 'PENDING'}\n%%EOF\n`);
  const value = {
    status: approved ? 'approved' : 'review_required',
    human_review_completed: approved,
    client_delivery_allowed: false,
    ...(approved ? {accepted_edition: {review: {decision: 'approved', approval_certificate_sha256: 'c'.repeat(64)}}} : {}),
    review_artifact_identity: {
      artifact_schema: 'nico.comprehensive_review_artifact_identity.v1',
      run_id: 'comprun_unit_fixture', revision: approved ? 18 : 17,
      report_artifact_digest: (approved ? 'b' : 'a').repeat(64),
      artifact_digests: {pdf: {sha256: digest(bytes), size_bytes: bytes.length}},
    },
    reports: {
      pdf_base64: bytes.toString('base64'),
      pdf_filename: approved ? 'NICO-APPROVED-FINAL.pdf' : 'NICO-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf',
    },
  };
  if (approved && operator) {
    const approvedIdentity = value.review_artifact_identity;
    value.status = 'review_required';
    value.human_review_completed = false;
    value.operator_approval_status = 'approved';
    value.operator_approved_edition = {
      review: {...value.accepted_edition.review, approval_basis: 'operator_report'},
      artifact_digests: approvedIdentity.artifact_digests,
      report_artifact_digest: approvedIdentity.report_artifact_digest,
      accepted_edition_manifest_sha256: 'd'.repeat(64),
      source_review_artifact_identity: fixture(false).review_artifact_identity,
      reports: {...value.reports, json: {human_review_completed: false, pending_qc: 9}},
    };
    delete value.accepted_edition;
    value.reports = fixture(false).reports; // Source report remains retained separately.
  }
  return value;
}
const finalReport = value => value.operator_approved_edition?.reports || value.reports;
const text = value => value == null || typeof value === 'boolean' ? ''
  : typeof value !== 'object' ? String(value)
  : Array.isArray(value) ? value.map(text).join('') : text(value.props?.children);
function nodes(value) {
  if (!value || typeof value !== 'object') return [];
  if (Array.isArray(value)) return value.flatMap(nodes);
  return [value, ...nodes(value.props?.children)];
}
function harness({locale = 'en', edition = 'source', post, get} = {}) {
  const slots = [], effects = [], requests = [], downloads = [], blobs = new Map();
  let cursor = 0, effectMounted = false, tree;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => {slots[index] = typeof value === 'function' ? value(slots[index]) : value;}];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = {current: initial};
      return slots[index];
    },
    useMemo: fn => fn(),
    useEffect(fn) {if (!effectMounted) effects.push(fn);},
  };
  const jsx = (type, props) => ({type, props});
  class TestURL extends URL {
    static createObjectURL(blob) {const id = `blob:unit-${blobs.size}`; blobs.set(id, blob); return id;}
    static revokeObjectURL() {}
  }
  const context = {
    exports: {}, console, URL: TestURL, URLSearchParams, Uint8Array, ArrayBuffer, Blob,
    window: {
      location: {origin: 'https://unit.invalid', search: `?run_id=comprun_unit_fixture&lang=${locale}&edition=${edition}`},
      crypto: webcrypto, atob, setTimeout: () => 0,
    },
    document: {
      documentElement: {}, body: {appendChild() {}},
      createElement() {return {href: '', download: '', remove() {}, click() {
        downloads.push({filename: this.download, blob: blobs.get(this.href)});
      }};},
    },
    fetch: async (url, options = {}) => {
      const request = {url, method: options.method || 'GET', body: options.body && JSON.parse(options.body), headers: options.headers};
      requests.push(request);
      if (request.method === 'POST' && post) return post(request);
      if (request.method === 'GET' && get) return get(request);
      return {ok: true, status: 200, json: async () => fixture(request.method === 'POST')};
    },
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return {jsx, jsxs: jsx, Fragment: 'fragment'};
      if (name.endsWith('.css')) return {default: {}};
      throw new Error(`Unexpected import ${name}`);
    },
  };
  vm.runInNewContext(compiled.outputText, context, {filename});
  function render() {cursor = 0; tree = context.exports.default(); return tree;}
  render(); effectMounted = true; effects.forEach(fn => fn()); render();
  function button(label) {return nodes(tree).find(n => n.type === 'button' && text(n) === label);}
  function field(label) {
    const parent = nodes(tree).find(n => n.type === 'label' && text(n).startsWith(label));
    const result = nodes(parent).find(n => ['input', 'select', 'textarea'].includes(n.type));
    assert.ok(result, `Missing field ${label}`); return result;
  }
  function change(label, value) {field(label).props.onChange({target: {value, checked: value}}); render();}
  async function click(label) {
    const item = button(label); assert.ok(item, `Missing button ${label}`);
    assert.ok(!item.props.disabled, `Disabled button ${label}`);
    await item.props.onClick(); render();
  }
  async function load() {
    change(locale === 'en' ? 'Operator password' : 'Contraseña del operador', 'unit-test-not-a-secret');
    await nodes(tree).find(n => n.type === 'form').props.onSubmit({preventDefault() {}}); render();
  }
  const reviewerLabel = locale === 'en' ? 'Reviewer name (optional)' : 'Nombre del revisor (opcional)';
  const roleLabel = locale === 'en' ? 'Reviewer role (optional)' : 'Función del revisor (opcional)';
  const reviewLabel = locale === 'en' ? 'Download report for review' : 'Descargar informe para revisión';
  const approveLabel = locale === 'en' ? 'Approve and download final PDF' : 'Aprobar y descargar PDF final';
  async function ready({reviewer = 'Unit Fixture Reviewer', role = 'Security reviewer'} = {}) {
    await load();
    if (reviewer !== undefined) change(reviewerLabel, reviewer);
    if (role !== undefined) change(roleLabel, role);
    await click(reviewLabel);
    change(locale === 'en' ? 'I reviewed this exact' : 'Revisé este informe', true);
  }
  return {button, field, change, click, load, ready, render, requests, downloads, reviewerLabel, roleLabel, reviewLabel, approveLabel,
    text: () => text(tree), elements: () => nodes(tree)};
}

test('pending approval remains actionable with blank reviewer metadata', async () => {
  const h = harness(); await h.load();
  assert.ok(h.button(h.approveLabel)); assert.equal(h.button(h.approveLabel).props.disabled, true);
  assert.match(h.text(), /Reviewer name and role are optional for approval/);
  assert.equal(h.field('I reviewed this exact').props.disabled, true);
  assert.equal(h.button(h.reviewLabel).props.disabled, false);
  await h.click(h.reviewLabel);
  assert.equal(h.downloads[0].filename, fixture().reports.pdf_filename);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
  assert.equal(h.field('I reviewed this exact').props.disabled, false);
  h.change('I reviewed this exact', true);
  assert.equal(h.button(h.approveLabel).props.disabled, false);
});

test('blank reviewer metadata can approve and returns an approved final PDF', async () => {
  const h = harness(); await h.ready({reviewer: '', role: ''});
  await h.click(h.approveLabel);
  const posts = h.requests.filter(r => r.method === 'POST');
  assert.equal(posts.length, 1);
  assert.equal(posts[0].body.reviewer, '');
  assert.equal(posts[0].body.reviewer_role, '');
  assert.equal(posts[0].body.decision, 'approved');
  assert.equal(h.downloads.length, 2);
  assert.equal(h.downloads[1].filename, finalReport(fixture(true)).pdf_filename);
  assert.equal(h.button(h.approveLabel), undefined);
  assert.equal(h.button('Authorize client delivery'), undefined);
});

test('test reviewer metadata can exercise approval through an approved final PDF', async () => {
  const h = harness(); await h.ready({reviewer: 'test', role: 'test'});
  await h.click(h.approveLabel);
  const posts = h.requests.filter(r => r.method === 'POST');
  assert.equal(posts.length, 1);
  assert.equal(posts[0].body.reviewer, 'test');
  assert.equal(posts[0].body.reviewer_role, 'test');
  assert.equal(posts[0].body.decision, 'approved');
  assert.equal(h.downloads.length, 2);
  assert.equal(h.downloads[1].filename, finalReport(fixture(true)).pdf_filename);
});

test('checkbox alone cannot approve without exact downloaded artifact', async () => {
  const h = harness(); await h.load();
  h.change('I reviewed this exact', true); // Direct adversarial event, bypassing disabled UI.
  await h.button(h.approveLabel).props.onClick(); h.render();
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
  assert.match(h.text(), /Download and review this exact report/);
});

for (const [locale, edition] of [['en', 'source'], ['es-MX', 'es-MX']]) {
  test(`${locale}: explicit approval downloads returned approved bytes, never authorizes delivery`, async () => {
    const h = harness({locale, edition}); await h.ready();
    await h.click(h.approveLabel);
    const posts = h.requests.filter(r => r.method === 'POST'); assert.equal(posts.length, 1);
    assert.ok(posts[0].url.endsWith(edition === 'source' ? '/comprun_unit_fixture/review' : '/comprun_unit_fixture/localized-editions/es-MX/review'));
    assert.deepEqual(posts[0].body.expected_artifact_identity, fixture().review_artifact_identity);
    assert.equal(posts[0].body.decision, 'approved');
    assert.equal(h.downloads.length, 2); assert.equal(h.downloads[1].filename, finalReport(fixture(true)).pdf_filename);
    assert.equal(digest(Buffer.from(await h.downloads[1].blob.arrayBuffer())), fixture(true).review_artifact_identity.artifact_digests.pdf.sha256);
    assert.equal(h.button(h.approveLabel), undefined);
    assert.equal(h.button(locale === 'en' ? 'Authorize client delivery' : 'Autorizar entrega al cliente'), undefined);
    assert.ok(h.elements().filter(n => n.type === 'button' && n.props['data-nico-pdf-action'] === 'true').length);
  });
}

test('409 stale-artifact rejection does not produce an approved PDF or success', async () => {
  const h = harness({post: async () => ({ok: false, status: 409, json: async () => ({detail: {code: 'stale_review_artifact_identity', message: 'Reload and review the current exact artifacts.'}})})});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Reload and review the current exact artifacts/);
});

test('approved PDF corruption preserves recorded approval and offers download-only retry', async () => {
  const h = harness({post: async () => {const value = fixture(true); value.operator_approved_edition.reports.pdf_base64 = fixture().reports.pdf_base64;
    return {ok: true, status: 200, json: async () => value};}});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.equal(h.button(h.approveLabel), undefined);
  assert.match(h.text(), /Approval was recorded, but the approved PDF download failed/);
  assert.ok(h.button('Download approved final PDF'));
  await h.click('Download approved final PDF');
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 1);
  assert.equal(h.downloads.length, 1);
  assert.equal(h.button('Authorize client delivery'), undefined);
});

test('rapid duplicate approval calls produce only one mutation', async () => {
  let resolvePost;
  const h = harness({post: () => new Promise(resolve => {resolvePost = resolve;})}); await h.ready();
  const handler = h.button(h.approveLabel).props.onClick;
  const first = handler(); const duplicate = handler();
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 1);
  resolvePost({ok: true, status: 200, json: async () => fixture(true)});
  await Promise.all([first, duplicate]); h.render(); assert.equal(h.downloads.length, 2);
});

test('changing the run discards downloaded identity and review acknowledgement', async () => {
  const h = harness(); await h.ready();
  h.change('Exact Comprehensive run ID', 'comprun_different_fixture');
  assert.equal(h.button(h.approveLabel), undefined); assert.equal(h.downloads.length, 1);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
});

test('changing the edition discards the previously reviewed report', async () => {
  const h = harness(); await h.ready(); h.change('Report edition', 'es-MX');
  assert.equal(h.button(h.approveLabel), undefined);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
});

test('server rejection remains visible and never becomes false success', async () => {
  const h = harness({post: async () => ({ok: false, status: 422, json: async () => ({detail: {code: 'review_work_not_ready_for_approval', message: 'Independent quality control remains incomplete.'}})})});
  await h.ready({reviewer: 'test', role: 'test'}); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Independent quality control remains incomplete/);
});

test('HTTP 200 pending response never masquerades as an approved download', async () => {
  const h = harness({post: async () => ({ok: true, status: 200, json: async () => fixture(false)})});
  await h.ready({reviewer: '', role: ''}); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Unable to record report approval/);
});

for (const value of ['', 'TEST', 'test', ' TeSt ']) {
  test(`operator metadata ${JSON.stringify(value)} remains optional data and never completes QC`, async () => {
    const h = harness(); await h.ready({reviewer: value, role: value});
    h.change('Decision context', value);
    await h.click(h.approveLabel);
    const post = h.requests.find(r => r.method === 'POST');
    assert.equal(post.body.reviewer, value);
    assert.equal(post.body.reviewer_role, value);
    assert.equal(post.body.decision_reason, value);
    assert.equal(post.body.approval_kind, 'operator_report');
    assert.equal(post.body.exact_report_acknowledged, true);
    assert.equal(post.body.review_authorized, true);
    assert.equal(post.body.authorization_confirmed, true);
    assert.match(h.text(), /Specialist reviewNot completed/);
    assert.match(h.text(), /does not mark that work complete or authorize client delivery/);
    assert.match(h.text(), /"human_review_completed": false/);
    assert.doesNotMatch(h.text(), /pdf_base64|UNIT FIXTURE ONLY/);
    assert.equal(h.button('Authorize client delivery'), undefined);
  });
}

test('approved operator reload downloads the operator edition without another approval', async () => {
  const h = harness({get: async () => ({ok: true, status: 200, json: async () => fixture(true)})});
  await h.load();
  assert.equal(h.button(h.approveLabel), undefined);
  await h.click('Download approved final PDF');
  assert.equal(h.downloads.length, 1);
  assert.equal(h.downloads[0].filename, finalReport(fixture(true)).pdf_filename);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
  assert.equal(digest(Buffer.from(await h.downloads[0].blob.arrayBuffer())), fixture(true).review_artifact_identity.artifact_digests.pdf.sha256);
});

test('operator status without its bound receipt never hides pending approval', async () => {
  const h = harness({post: async () => {const value = fixture(false); value.operator_approval_status = 'approved';
    return {ok: true, status: 200, json: async () => value};}});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1);
  assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Unable to record report approval/);
});

test('legacy specialist approved edition retains its separate delivery controls', async () => {
  const h = harness({get: async () => ({ok: true, status: 200, json: async () => fixture(true, false)})});
  await h.load();
  assert.equal(h.button(h.approveLabel), undefined);
  assert.match(h.text(), /Specialist reviewCompleted/);
  assert.ok(h.button('Authorize client delivery').props.disabled);
  await h.click('Download approved final PDF');
  assert.equal(h.downloads.length, 1);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
});

function loadHelpers(relative, additions = {}) {
  const location = path.resolve(relative);
  const output = ts.transpileModule(readFileSync(location, 'utf8'), {
    fileName: location,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
  });
  const context = {exports: {}, URL, URLSearchParams, ...additions};
  context.require = additions.require || (() => ({}));
  vm.runInNewContext(output.outputText, context, {filename: location});
  return context.exports;
}

test('final review navigation preserves exact run and locale without copying credentials', () => {
  const {finalReviewHref} = loadHelpers('apps/web/app/PrimaryNavigation.tsx');
  const url = new URL(finalReviewHref('/operations/final-review?lang=es-MX',
    '?run_id=comprun_unit_fixture&edition=es-MX&admin_token=never-forward&customer_id=internal'), 'https://unit.invalid');
  assert.equal(url.searchParams.get('run_id'), 'comprun_unit_fixture');
  assert.equal(url.searchParams.get('service'), 'comprehensive');
  assert.equal(url.searchParams.get('lang'), 'es-MX');
  assert.equal(url.searchParams.get('edition'), 'es-MX');
  assert.equal(url.searchParams.has('admin_token'), false);
  assert.equal(new URL(finalReviewHref('/operations/final-review', '', 'comprun_visible_fixture'), 'https://unit.invalid').searchParams.get('run_id'), 'comprun_visible_fixture');
  assert.equal(finalReviewHref('/operations/final-review', '?run_id=invalid'), '/operations/final-review');
  assert.equal(finalReviewHref('/operations', '?run_id=comprun_unit_fixture'), '/operations');
});

test('workflow banner retains the reviewed run and edition in both languages', () => {
  const navigation = loadHelpers('apps/web/app/PrimaryNavigation.tsx');
  for (const lang of ['en', 'es-MX']) {
    const jsx = (type, props) => ({type, props});
    const search = `?run_id=comprun_unit_fixture&edition=es-MX&lang=${lang}&admin_token=never-forward`;
    const component = loadHelpers('apps/web/app/WorkflowCallout.tsx', {require: name => {
      if (name === 'react') return {useEffect() {}, useState: () => [search, () => {}]};
      if (name === 'react/jsx-runtime') return {jsx, jsxs: jsx};
      if (name === 'next/navigation') return {usePathname: () => '/operations/final-review'};
      if (name === './PrimaryNavigation') return navigation;
      throw new Error(`Unexpected import ${name}`);
    }});
    const link = nodes(component.default()).find(n => n.type === 'a' && /Final Review|Revisión final/.test(text(n)));
    const target = new URL(link.props.href, 'https://unit.invalid');
    assert.equal(target.pathname, '/operations/final-review');
    assert.equal(target.searchParams.get('run_id'), 'comprun_unit_fixture');
    assert.equal(target.searchParams.get('edition'), 'es-MX');
    assert.equal(target.searchParams.get('service'), 'comprehensive');
    assert.equal(target.searchParams.has('admin_token'), false);
    if (lang === 'es-MX') assert.equal(target.searchParams.get('lang'), lang);
  }
});

test('optional client metadata does not block owner review navigation but remains unready for delivery', () => {
  const {finalReviewReadiness} = loadHelpers('apps/web/app/AssessmentFinalReviewAction.tsx');
  const value = {run_id: 'comprun_unit_fixture', status: 'review_required', client_delivery_allowed: false,
    record: {identity: {customer_id: 'internal', project_id: 'internal'}},
    stage_results: {cross_format_truth_verification: {status: 'passed', failed_checks: []}}};
  const readiness = finalReviewReadiness(value);
  assert.equal(readiness.ready, true);
  assert.equal(readiness.clientDeliveryIdentityReady, false);
  value.stage_results.cross_format_truth_verification.failed_checks.push('artifact_mismatch');
  assert.equal(finalReviewReadiness(value).ready, false);
});

async function hydrationHarness(mutation, status) {
  const calls = [];
  const originalFetch = async (input, init) => {
    calls.push({url: String(input), method: init.method});
    return Response.json(init.method === 'POST' ? mutation : status);
  };
  const window = {fetch: originalFetch, location: {href: 'https://unit.invalid/operations/final-review', origin: 'https://unit.invalid'}, setTimeout: fn => {fn(); return 0;}};
  const helpers = loadHelpers('apps/web/app/operations/final-review/FinalReviewApprovedReportHydration.tsx', {
    window, Request, require: name => name === 'react' ? {useEffect: fn => fn()} : {},
  });
  helpers.default();
  const response = await window.fetch('https://unit.invalid/api/nico/assessment/comprehensive-run/comprun_unit_fixture/localized-editions/es-MX/review', {
    method: 'POST', headers: {'X-NICO-Admin-Token': 'unit-fixture'},
    body: JSON.stringify({decision: 'approved', approval_kind: 'operator_report', exact_report_acknowledged: true}),
  });
  return {calls, response: await response.json()};
}

test('operator mutation with approved bytes needs no redundant hydration read', async () => {
  const h = await hydrationHarness(fixture(true), fixture(false));
  assert.equal(h.calls.length, 1);
  assert.equal(h.response.operator_approval_status, 'approved');
  assert.equal(h.response.human_review_completed, false);
});

test('operator hydration reads only the same exact locale and preserves specialist truth', async () => {
  const missing = fixture(true); delete missing.operator_approved_edition.reports;
  const h = await hydrationHarness(missing, fixture(true));
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].method, 'GET');
  assert.ok(h.calls[1].url.endsWith('/comprun_unit_fixture/localized-editions/es-MX'));
  assert.equal(h.response.human_review_completed, false);
  assert.equal(h.response.client_delivery_allowed, false);
  assert.equal(finalReport(h.response).pdf_filename, finalReport(fixture(true)).pdf_filename);
});


test('operator approval for another reviewed identity is never accepted or downloaded', async () => {
  const h = harness({post: async () => {const value = fixture(true);
    value.operator_approved_edition.source_review_artifact_identity.run_id = 'comprun_other_fixture';
    return {ok: true, status: 200, json: async () => value};}});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1);
  assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /failed browser integrity validation/);
});
