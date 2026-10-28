'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {harness, payload} = require('./helpers/review-work-panel.cjs');
for (const locale of ['en', 'es-MX']) {
  test(`${locale}: retained assistance pages all candidates without writes`, async () => {
    const queue = Array.from({length: 26}, (_, i) => ({candidate_id: `candidate_${i}`, record_index: i,
      recommendation: 'resolve_evidence_gaps', limitations: ['unresolved_proof_gaps'], source_url: null,
      input_sha256: 'a'.repeat(64), existing_review_profile_cluster_id: 'profile'}));
    const h = harness(locale, () => Response.json(payload({review_assistance: {
      artifact_schema: 'nico.candidate-review-assistance.v1', pending_record_count: 26, queue}})));
    await h.load();
    assert.match(h.html(), locale === 'en' ? /no new source investigation/ : /no se realizó una nueva investigación/);
    assert.equal(h.find(n => n.type === 'details' && n.props['data-review-assistance-candidate']).length, 25);
    const next = locale === 'en' ? 'Next' : 'Siguiente';
    h.find(n => n.type === 'button' && n.props.children === next)[0].props.onClick();
    assert.equal(h.find(n => n.type === 'details' && n.props['data-review-assistance-candidate']).length, 1);
    assert.match(h.html(), /candidate_25/);
    assert.equal(h.calls.length, 1, 'navigation must not submit dispositions or fetch source');
  });
}
