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
function fixture(approved = false) {
  const bytes = Buffer.from(`%PDF-1.7\nUNIT FIXTURE ONLY ${approved ? 'APPROVED' : 'PENDING'}\n%%EOF\n`);
  return {
    status: approved ? 'approved' : 'review_required',
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
}
const text = value => value == null || typeof value === 'boolean' ? ''
  : typeof value !== 'object' ? String(value)
  : Array.isArray(value) ? value.map(text).join('') : text(value.props?.children);
function nodes(value) {
  if (!value || typeof value !== 'object') return [];
  if (Array.isArray(value)) return value.flatMap(nodes);
  return [value, ...nodes(value.props?.children)];
}
function harness({locale = 'en', edition = 'source', post} = {}) {
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
  const reviewLabel = locale === 'en' ? 'Download report for review' : 'Descargar informe para revisión';
  const approveLabel = locale === 'en' ? 'Approve and download final PDF' : 'Aprobar y descargar PDF final';
  async function ready() {
    await load();
    change(locale === 'en' ? 'Authorized reviewer' : 'Revisor autorizado', 'Unit Fixture Reviewer');
    change(locale === 'en' ? 'Reviewer role' : 'Función del revisor', 'Security reviewer');
    await click(reviewLabel);
    change(locale === 'en' ? 'I reviewed this exact' : 'Revisé este informe', true);
  }
  return {button, field, change, click, load, ready, render, requests, downloads, reviewLabel, approveLabel,
    text: () => text(tree), elements: () => nodes(tree)};
}

test('pending approval is visible and actionable, not hidden by missing reviewer metadata', async () => {
  const h = harness(); await h.load();
  assert.ok(h.button(h.approveLabel)); assert.equal(h.button(h.approveLabel).props.disabled, true);
  assert.match(h.text(), /Enter your reviewer name and select your authorized role/);
  assert.equal(h.field('I reviewed this exact').props.disabled, true);
  assert.equal(h.button(h.reviewLabel).props.disabled, false);
  await h.click(h.reviewLabel);
  assert.equal(h.downloads[0].filename, fixture().reports.pdf_filename);
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
  assert.equal(h.field('I reviewed this exact').props.disabled, false);
});

test('checkbox alone cannot approve without exact download and reviewer identity', async () => {
  const h = harness(); await h.load();
  h.change('Authorized reviewer', 'Unit Fixture Reviewer'); h.change('Reviewer role', 'Security reviewer');
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
    assert.equal(h.downloads.length, 2); assert.equal(h.downloads[1].filename, fixture(true).reports.pdf_filename);
    assert.equal(digest(Buffer.from(await h.downloads[1].blob.arrayBuffer())), fixture(true).review_artifact_identity.artifact_digests.pdf.sha256);
    assert.equal(h.button(h.approveLabel), undefined);
    assert.ok(h.button(locale === 'en' ? 'Authorize client delivery' : 'Autorizar entrega al cliente').props.disabled);
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
  const h = harness({post: async () => {const value = fixture(true); value.reports.pdf_base64 = fixture().reports.pdf_base64;
    return {ok: true, status: 200, json: async () => value};}});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.equal(h.button(h.approveLabel), undefined);
  assert.match(h.text(), /Approval was recorded, but the approved PDF download failed/);
  assert.ok(h.button('Download approved final PDF'));
  await h.click('Download approved final PDF');
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 1);
  assert.equal(h.downloads.length, 1);
  assert.equal(h.field('I reviewed the downloaded APPROVED FINAL PDF').props.disabled, true);
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

test('legitimate review/QC rejection remains blocked with its server explanation', async () => {
  const h = harness({post: async () => ({ok: false, status: 422, json: async () => ({detail: {code: 'review_work_not_ready_for_approval', message: 'Independent quality control remains incomplete.'}})})});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Independent quality control remains incomplete/);
});

test('HTTP 200 pending response never masquerades as an approved download', async () => {
  const h = harness({post: async () => ({ok: true, status: 200, json: async () => fixture(false)})});
  await h.ready(); await h.click(h.approveLabel);
  assert.equal(h.downloads.length, 1); assert.ok(h.button(h.approveLabel));
  assert.match(h.text(), /Unable to record human approval/);
});
