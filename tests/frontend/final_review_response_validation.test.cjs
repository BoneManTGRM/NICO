const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ts = require(require.resolve('typescript', {paths: [path.resolve('apps/web')]}));
const {harness, fixture, authorizedFixture, response, stable, digest} = require('./helpers/final-review-traces.cjs');
const filename = 'apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx';
const source = fs.readFileSync(filename, 'utf8');
const compiled = ts.transpileModule(source + '\nexport {validateApprovalResponse, assertDeliveryResponseBinding, COPY};', {
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
}).outputText;
const context = {exports: {}, require: () => ({})};
vm.runInNewContext(compiled, context);
const {validateApprovalResponse, assertDeliveryResponseBinding, COPY} = context.exports;
const clone = value => JSON.parse(JSON.stringify(value));
function validBinding() {
  const reviewed = fixture(true), identity = reviewed.review_artifact_identity;
  const authorized = clone(authorizedFixture({body: {expected_artifact_identity: identity}}));
  return {reviewed, identity, authorized, edition: reviewed.operator_approved_edition, operator: true};
}
function checkBinding(c, locale = 'en') {
  return assertDeliveryResponseBinding(c.authorized, c.authorized.delivery_authorization || {}, c.reviewed,
    c.identity, c.edition, c.operator, COPY[locale]);
}
const bindingChanges = {
  deliveryFlag: c => {c.authorized.client_delivery_allowed = false;},
  receiptFormat: c => {c.authorized.delivery_authorization.delivery_authorization_certificate_sha256 = 'bad';},
  artifactIdentity: c => {c.authorized.delivery_authorization.authorized_artifact_identity.revision++;},
  parentCertificate: c => {c.authorized.delivery_authorization.approval_certificate_sha256 = 'e'.repeat(64);},
  approvalManifest: c => {c.authorized.delivery_authorization.original_approval_manifest_sha256 = 'e'.repeat(64);},
  sourceReviewIdentity: c => {c.authorized.operator_approved_edition.source_review_artifact_identity.revision++;},
  sourceCertificateIdentity: c => {c.authorized.operator_approved_edition.review.source_identity.extra = 'changed';},
  returnedCertificate: c => {c.authorized.operator_approved_edition.review.approval_certificate_sha256 = 'e'.repeat(64);},
};
for (const locale of ['en', 'es-MX']) {
  test(`${locale}: approval binding and existing legacy behavior`, () => {
    const pending = fixture(false).review_artifact_identity, reviewed = fixture(true);
    const before = clone(reviewed);
    assert.equal(validateApprovalResponse(reviewed, false, pending, COPY[locale]).operatorDecision, true);
    assert.deepEqual(reviewed, before);
    const wrong = clone(pending); wrong.revision++;
    assert.throws(() => validateApprovalResponse(reviewed, false, wrong, COPY[locale]), {message: COPY[locale].invalidPdf});
    assert.equal(validateApprovalResponse(reviewed, true, wrong, COPY[locale]).operatorDecision, true);
    assert.throws(() => validateApprovalResponse(fixture(false), false, pending, COPY[locale]), {message: COPY[locale].approvalFailed});
    assert.throws(() => validateApprovalResponse(fixture(true, false), false, pending, COPY[locale]), {message: COPY[locale].approvalFailed});
    assert.equal(validateApprovalResponse(fixture(true, false), true, pending, COPY[locale]).operatorDecision, false);
    assert.throws(() => validateApprovalResponse(fixture(false), true, pending, COPY[locale]), {message: COPY[locale].approvalFailed});
  });
  for (const [name, change] of Object.entries(bindingChanges)) test(`${locale}: delivery binding rejects ${name}`, () => {
    const c = validBinding(); change(c); const before = clone(c);
    assert.throws(() => checkBinding(c, locale), {message: COPY[locale].authorizationFailed});
    assert.deepEqual(c, before);
  });
  test(`${locale}: derived manifest precedence and legacy bypass stay exact`, () => {
    const c = validBinding(); checkBinding(c, locale);
    c.edition.rendering_derivation = {authoritative_approval_manifest_sha256: 'e'.repeat(64)};
    assert.throws(() => checkBinding(c, locale), {message: COPY[locale].authorizationFailed});
    c.authorized.delivery_authorization.original_approval_manifest_sha256 = 'e'.repeat(64); checkBinding(c, locale);
    c.edition.rendering_derivation.authoritative_approval_manifest_sha256 = '';
    assert.throws(() => checkBinding(c, locale), {message: COPY[locale].authorizationFailed});
    c.authorized.delivery_authorization.original_approval_manifest_sha256 = 'd'.repeat(64); checkBinding(c, locale);
    c.operator = false; c.authorized.delivery_authorization = {}; checkBinding(c, locale);
    c.authorized.client_delivery_allowed = false;
    assert.throws(() => checkBinding(c, locale), {message: COPY[locale].authorizationFailed});
  });
  test(`${locale}: multi-failure short circuit and error precedence`, () => {
    const reviewed = fixture(true), order = [];
    // This accessor records the existing second certificate read; an earlier
    // source mismatch must win before that decision check can execute.
    const cert = reviewed.operator_approved_edition.review;
    let reads = 0;
    Object.defineProperty(cert, 'decision', {get() {order.push(++reads); return reads === 1 ? 'approved' : 'rejected';}});
    assert.throws(() => validateApprovalResponse(reviewed, false, {}, COPY[locale]), {message: COPY[locale].invalidPdf});
    assert.deepEqual(order, [1]);
    const c = validBinding(); c.authorized.client_delivery_allowed = false;
    Object.defineProperty(c.authorized.delivery_authorization, 'delivery_authorization_certificate_sha256', {get() {throw new Error('later check read');}});
    assert.throws(() => checkBinding(c, locale), {message: COPY[locale].authorizationFailed});
  });
}


// Returned-certificate and parent mismatches are also constrained by requestJson;
// their individual extracted predicates are exercised directly above.
// These fixtures remain valid through requestJson's authenticated receipt check.
// Rehash every changed receipt and preserve its internal parent binding so the
// comparison against the prior approved response is the rejection under test.
for (const mismatch of ['artifactIdentity', 'approvalManifest', 'sourceReviewIdentity', 'sourceCertificateIdentity']) {
  test(`rehash-valid delivery response rejects prior-response mismatch: ${mismatch}`, async () => {
    const h = harness({get: async () => response(fixture(true)), post: async request => {
      const c = validBinding(); c.authorized = clone(authorizedFixture(request));
      bindingChanges[mismatch](c);
      const receipt = c.authorized.delivery_authorization;
      delete receipt.delivery_authorization_certificate_sha256;
      receipt.delivery_authorization_certificate_sha256 = digest(stable(receipt));
      return response(c.authorized);
    }});
    await h.load(); await h.click(h.approveLabel);
    assert.equal(h.downloads.length, 0);
    assert.match(h.text(), /Unable to authorize client delivery/);
    assert.equal(h.requests.filter(r => r.method === 'POST').length, 1);
    assert.ok(h.button(h.approveLabel));
  });
}

async function snapshot(h) {
  h.render();
  return {trace: h.trace, requests: h.requests, downloads: await Promise.all(h.downloads.map(async d =>
    ({filename: d.filename, bytes: Buffer.from(await d.blob.arrayBuffer()).toString('base64')}))),
    popups: h.popups.map(p => ({closed: p.closed, url: p.url || null}))};
}
async function traces() {
  const output = {};
  for (const locale of ['en', 'es-MX']) {
    const edition = locale === 'es-MX' ? 'es-MX' : 'source';
    for (const mode of ['fresh', 'reused', 'legacy', 'lostApproval', 'lostDelivery', 'corruptPdf', 'blockedPopup', 'ios', 'denied', 'duplicate', 'deliverySelection', 'reconcileSelection']) {
      let current = fixture(mode === 'reused' || mode === 'legacy', mode !== 'legacy', edition === 'es-MX' ? 'es-MX' : 'en');
      let h, release, startedResolve;
      const started = new Promise(resolve => {startedResolve = resolve;});
      const hOptions = {locale, edition, ios: ['ios', 'blockedPopup'].includes(mode), popupBlocked: mode === 'blockedPopup',
        get: async () => {
          if (mode === 'reconcileSelection' && current.client_delivery_allowed) {startedResolve(); await new Promise(resolve => {release = resolve;});}
          return response(current);
        },
        post: async request => {
          const delivery = request.url.endsWith('/authorize-delivery');
          if (mode === 'denied') return {ok: false, status: 403, json: async () => ({detail: 'denied'})};
          current = delivery ? authorizedFixture(request, mode === 'corruptPdf', mode !== 'legacy') : fixture(true, true, edition === 'es-MX' ? 'es-MX' : 'en');
          if ((mode === 'lostApproval' && !delivery) || (['lostDelivery', 'reconcileSelection'].includes(mode) && delivery)) throw new Error('lost response');
          if ((mode === 'duplicate' && !delivery) || (mode === 'deliverySelection' && delivery)) {startedResolve(); await new Promise(resolve => {release = resolve;});}
          return response(current);
        }};
      h = harness(hOptions);
      if (['reused', 'legacy'].includes(mode)) {await h.load(); h.change(h.reviewerLabel, 'Reviewer'); h.change(h.roleLabel, 'Security reviewer');}
      else if (mode === 'blockedPopup') {
        // A reserved context can fail at final presentation after a prior
        // exact review download; start from an already approved edition.
        current = fixture(true, true, edition === 'es-MX' ? 'es-MX' : 'en'); await h.load();
      } else await h.ready();
      if (['duplicate', 'deliverySelection', 'reconcileSelection'].includes(mode)) {
        const button = h.button(h.approveLabel); const pending = button.props.onClick(); await started;
        if (mode === 'duplicate') {await button.props.onClick(); release(); await pending;}
        else {h.change(locale === 'en' ? 'Exact Comprehensive run ID' : 'ID exacto de ejecución Comprehensive', 'comprun_other'); release(); await pending;
          h.render(); assert.equal(h.downloads.length, 1); assert.equal(h.button(h.approveLabel), undefined);
          assert.equal(h.requests.filter(r => r.method === 'POST').length, 2);
        }
      } else await h.click(h.approveLabel);
      output[`${locale}/${mode}`] = await snapshot(h);
    }
  }
  return JSON.parse(JSON.stringify(output));
}
module.exports = {traces, bindingChanges};
// Fingerprints cover complete traces captured on main 024a67b6 before extraction.
if (!process.env.NICO_CAPTURE_APPROVAL_TRACES) test('complete before/after approval traces match verified main', async () => {
  const expected = require('./final_review_response_traces.json');
  const actual = await traces();
  assert.deepEqual(Object.keys(actual), Object.keys(expected));
  for (const [name, value] of Object.entries(actual)) assert.equal(digest(JSON.stringify(value)), expected[name], name);
});
