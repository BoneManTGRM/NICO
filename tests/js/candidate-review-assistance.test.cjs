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
for (const locale of ['en', 'es-MX']) {
  test(`${locale}: unknown labels and unsafe links cannot imply clearance`, async () => {
    const h = harness(locale, () => Response.json(payload({review_assistance: {
      artifact_schema: 'nico.candidate-review-assistance.v1', pending_record_count: 1,
      queue: [{candidate_id: 'A', record_index: 0, recommendation: '__proto__',
        limitations: ['constructor'], source_url: 'javascript:alert(1)', input_sha256: 'a'.repeat(64),
        existing_review_profile_cluster_id: ''}],
    }})));
    await h.load();
    assert.match(h.html(), locale === 'en' ? /Resolve evidence gaps before disposition/ : /Resolver brechas de evidencia antes de decidir/);
    assert.match(h.html(), locale === 'en' ? /Additional evidence review required/ : /Se requiere revisión adicional de evidencia/);
    assert.equal(h.find(n => n.type === 'a' && String(n.props.href).startsWith('javascript:')).length, 0);
    assert.equal(h.calls.length, 1);
  });
}
for (const locale of ['en', 'es-MX']) {
  test(`${locale}: persisted investigation shows evidence and limits without launching work`, async () => {
    const assistance = {artifact_schema: 'nico.candidate-review-assistance.v1', pending_record_count: 1,
      queue: [{candidate_id: 'A', record_index: 0, recommendation: 'resolve_evidence_gaps', limitations: [], source_url: null, input_sha256: 'a'.repeat(64), existing_review_profile_cluster_id: ''}],
      source_investigation: {available: true, candidate_count: 2, completed_count: 1,
        packets: [{candidate_id: 'A', rule_id: 'B101', completed: true, source_sha256: 'b'.repeat(64), line: 1, reason: 'exact_line_structure_only'}]}};
    const h = harness(locale, () => Response.json(payload({review_assistance: assistance})));
    await h.load();
    assert.match(h.html(), /1 \/ 2/);
    assert.match(h.html(), locale === 'en' ? /Counterevidence/ : /Contraevidencia/);
    assert.match(h.html(), locale === 'en' ? /Open questions/ : /Preguntas pendientes/);
    assert.equal(h.find(n => n.props['data-source-investigation'] === 'true').length, 1);
    assert.equal(h.calls.length, 1, 'read panel must not trigger new investigation');
  });
}
