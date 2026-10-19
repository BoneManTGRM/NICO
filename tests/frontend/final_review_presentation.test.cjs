// Complete host-tree characterization captured on 856d57de before extraction.
// Includes every prop/aria/disabled/action attribute and exact technical JSON.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {harness, fixture, authorizedFixture, response, digest} = require('./helpers/final-review-traces.cjs');
const clone = value => JSON.parse(JSON.stringify(value));
const normalize = value => JSON.parse(JSON.stringify(value, (_key, item) => typeof item === 'function' ? '[callback]' : item));
function cases() {
  const authorized = authorizedFixture({body: {expected_artifact_identity: fixture(true).review_artifact_identity}});
  const derived = fixture(true);
  derived.operator_approved_edition.rendering_derivation = {version: 'v1', kind: 'presentation', new_human_approval: false,
    authoritative_approval_manifest_sha256: 'f'.repeat(64), original_approved_pdf_sha256: 'e'.repeat(64), extra: 'not in technical projection'};
  return {
    pending: fixture(), operator: fixture(true), specialist: fixture(true, false), authorized,
    authorizedSpecialist: {...fixture(true, false), client_delivery_allowed: true}, derived,
    missingPdf: {...fixture(), reports: {}}, missingPdfDigest: {...fixture(), review_artifact_identity: {...fixture().review_artifact_identity, artifact_digests: {}}},
    flagsAsStrings: {...fixture(), human_review_completed: 'true', client_delivery_allowed: 'true'},
    independentSpecialist: {...fixture(), human_review_completed: true}, independentDelivery: {...fixture(), client_delivery_allowed: true},
    customStatus: {...fixture(), review_status: 'custom_pending_state'},
    artifactFallbacks: {...fixture(), accepted_edition: {report_artifact_digest: 'edition-digest', accepted_edition_manifest_sha256: 'manifest', review: {approval_certificate_sha256: 'certificate'}},
      approved_delivery_package: {zip_sha256: 'package', certificate: {delivery_authorization_certificate_sha256: 'delivery-certificate'}}, reports: {pdf_filename: '<exact & retained>.pdf'}},
    contextDigest: {status: 'review_required', reports: {}, review_context: {artifact_digest: 'context-digest'}},
    emptyDigests: {status: 'review_required', reports: {pdf_filename: ''}, accepted_edition: {}, approved_delivery_package: {}},
  };
}
async function presentationOutputs() {
  const output = {};
  const save = (name, h) => {output[name] = normalize({tree: h.render(), trace: h.trace, requests: h.requests});};
  for (const locale of ['en', 'es-MX']) {
    const h = harness({locale}); save(`${locale}/initial`, h); await h.load(); save(`${locale}/loaded`, h);
    h.change(h.reviewerLabel, 'Human <Reviewer>'); h.change(h.roleLabel, 'Security reviewer');
    h.change(locale === 'en' ? 'Decision context' : 'Contexto de la decisión', 'Literal <note> & evidence');
    save(`${locale}/metadata`, h);
    await h.click(h.reviewLabel); save(`${locale}/downloaded`, h);
    h.change(locale === 'en' ? 'I reviewed this exact' : 'Revisé este informe', true); save(`${locale}/acknowledged`, h);
    h.change(locale === 'en' ? 'Operator password' : 'Contraseña del operador', ''); save(`${locale}/credentialRemoved`, h);
    h.change(locale === 'en' ? 'Report edition' : 'Edición del informe', 'es-MX'); save(`${locale}/editionChanged`, h);
    h.change(locale === 'en' ? 'Exact Comprehensive run ID' : 'ID exacto de ejecución Comprehensive', 'comprun_other'); save(`${locale}/runChanged`, h);
    for (const [name, value] of Object.entries(cases())) {
      const original = clone(value), c = harness({locale, get: async () => response(value)});
      await c.load(); save(`${locale}/${name}`, c); assert.deepEqual(value, original);
    }
    for (const decision of ['request_more_evidence', 'rejected']) {
      const c = harness({locale, post: async () => response({...fixture(), status: decision})});
      await c.load(); c.change(c.reviewerLabel, 'Reviewer'); c.change(c.roleLabel, 'Security reviewer');
      c.change(locale === 'en' ? 'Decision context' : 'Contexto de la decisión', 'Recorded reason');
      const label = decision === 'rejected' ? c.copy.reject : c.copy.requestEvidence;
      await c.click(label); save(`${locale}/decision/${decision}`, c);
      assert.equal(c.requests.filter(r => r.method === 'POST').length, 1);
      assert.equal(c.requests.at(-1).body.decision, decision);
    }
    let release;
    const busy = harness({locale, get: () => new Promise(resolve => {release = resolve;})});
    const pending = busy.load(); save(`${locale}/loading`, busy); release(response(fixture())); await pending;
    const failed = harness({locale, post: async () => ({ok: false, status: 403, json: async () => ({detail: 'private backend detail'})})});
    await failed.ready(); await failed.click(failed.approveLabel); save(`${locale}/errorWithPriorNotice`, failed);
    assert.ok(failed.elements().some(n => n.props.role === 'alert'));
    assert.ok(!failed.elements().some(n => n.props.className === 'success'));
  }
  return output;
}
module.exports = {presentationOutputs};
if (!process.env.NICO_CAPTURE_PRESENTATION) test('complete bilingual presentation and callback outputs match pre-extraction main', async () => {
  const expected = require('./final_review_presentation.json'), actual = await presentationOutputs();
  assert.deepEqual(Object.keys(actual), Object.keys(expected));
  for (const [name, value] of Object.entries(actual)) assert.equal(digest(JSON.stringify(value)), expected[name], name);
});

for (const locale of ['en', 'es-MX']) test(`${locale}: error suppresses a retained prior download notice`, async () => {
  const h = harness({locale}); await h.ready();
  assert.ok(h.elements().some(n => n.props.className === 'success'));
  h.change(locale === 'en' ? 'Operator password' : 'Contraseña del operador', '');
  const button = h.button(h.reviewLabel); assert.equal(button.props.disabled, true);
  // Adversarial direct invocation of the disabled button exercises the handler
  // guard, which sets an error while preserving the earlier notice in state.
  await button.props.onClick(); h.render();
  assert.ok(h.elements().some(n => n.props.role === 'alert'));
  assert.ok(!h.elements().some(n => n.props.className === 'success'));
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0);
});
