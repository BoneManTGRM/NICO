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
    assert.equal(h.find(n => n.type === 'a' && n.props.children === (locale === 'en' ? 'Open exact source location' : 'Abrir ubicación del código exacto')).length, 0);
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

const exactSource = `https://github.com/BoneManTGRM/NICO/blob/${'a'.repeat(40)}/nico/example.py`;
for (const locale of ['en', 'es-MX']) {
  const unsafeSources = [
    'javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)',
    'JaVaScRiPt:alert(1)', 'DATA:text/html,test', 'VBScript:msgbox(1)',
    '//github.com/owner/repo', 'http://github.com/owner/repo',
    `https://github.com.evil.invalid/owner/repo/blob/${'a'.repeat(40)}/file.py`,
    `https://github.com@evil.invalid/owner/repo/blob/${'a'.repeat(40)}/file.py`,
    ' https://github.com/owner/repo', 'file:///tmp/example.py',
  ];
  for (const sourceUrl of [...unsafeSources, exactSource, `${exactSource}#L12`]) {
    test(`${locale}: source locator allowlist ${sourceUrl}`, async () => {
      const h = harness(locale, () => Response.json(payload({review_assistance: {
        artifact_schema: 'nico.candidate-review-assistance.v1', pending_record_count: 1,
        queue: [{candidate_id: 'A', record_index: 0, recommendation: 'resolve_evidence_gaps',
          limitations: [], source_url: sourceUrl, input_sha256: 'a'.repeat(64), existing_review_profile_cluster_id: ''}],
      }})));
      await h.load();
      const links = h.find(n => n.type === 'a' && n.props.children === (locale === 'en' ? 'Open exact source location' : 'Abrir ubicación del código exacto'));
      if ([exactSource, `${exactSource}#L12`].includes(sourceUrl)) {
        assert.equal(links.length, 1);
        assert.equal(links[0].props.href, sourceUrl);
        assert.equal(links[0].props.target, '_blank');
        assert.equal(links[0].props.rel, 'noopener noreferrer');
      } else {
        assert.equal(links.length, 0, 'unsupported source URL must produce no source anchor');
      }
      assert.equal(h.calls.length, 1, 'display must not fetch source or submit a disposition');
    });
  }
}
