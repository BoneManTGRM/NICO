'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const {harness, payload} = require('./helpers/review-work-panel.cjs');
const root = path.resolve(__dirname, '../..');
function python(code, input) {
  const result = spawnSync('python3', ['-c', code], {
    cwd: root, input, encoding: 'utf8', timeout: 10000,
    env: {PATH: process.env.PATH, PYTHONPATH: path.join(root, 'scripts')},
  });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  return result.stdout;
}
const fixture = JSON.parse(python("import json; from reviewer_binding_webkit_proof import fixture; print(json.dumps(fixture('a'*40,'dependency')))"));
for (const locale of ['en','es-MX']) {
  test(`${locale}: exact browser dependency fixture renders conservative evidence`, async () => {
    const results = [];
    assert.equal(fixture.review_assistance.queue.length, 13);
    for (const row of fixture.review_assistance.queue) {
      const assistance = structuredClone(fixture.review_assistance);
      assistance.queue = [row]; assistance.pending_record_count = 1;
      const h = harness(locale, () => Response.json(payload({review_assistance: assistance})));
      await h.load();
      results.push({case: row.candidate_id.slice('dependency-'.length), locale, text: h.html(),
        count: h.find(n => n.props['data-dependency-next-step'] === 'true').length});
      assert.equal(h.find(n => n.props['data-dependency-evidence'] === 'true').length, 1);
      assert.equal(h.calls.length, 1, 'render must not acquire source or submit a disposition');
    }
    python("import json,sys; from reviewer_binding_webkit_proof import validate_dependency_text; rows=json.load(sys.stdin); [validate_dependency_text(r['case'],r['locale'],r['text'],r['count']) for r in rows]", JSON.stringify(results));
  });
}
