'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const filename = path.join(root, 'apps/web/app/operations/reviewer-queue/reviewActionPayload.ts');
const mod = {exports: {}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText, {module: mod, exports: mod.exports}, {filename});
const {buildReviewActionPayload} = mod.exports;
const fields = Object.freeze(Object.fromEntries([
  'reviewer', 'reviewerRole', 'targetId', 'disposition', 'rationale', 'residualRisk',
  'residualRiskOwner', 'escalationResolution', 'escalationOwner', 'assignee', 'specialistRole',
  'qcOutcome', 'qcNote', 'requestText', 'requestOwner', 'resolutionNote', 'evidenceReferences',
  'stakeholderStatement', 'sourceRole', 'evidenceReference',
].map(key => [key, key === 'evidenceReferences' ? '  evidencia://uno\r\n\n evidencia://uno \n prueba:ñ  '
  : ` ${key}:ñ \n retained `])));
const actions = ['assign', 'disposition_candidate', 'disposition_group', 'quality_control', 'request_evidence',
  'resolve_evidence_request', 'stakeholder_evidence', 'start_session', 'stop_session', 'complete_empirical_study'];
for (const action of actions) {
  test(`${action}: pure payload construction is repeatable and does not retain mutable output`, () => {
    const before = JSON.stringify(fields);
    const first = buildReviewActionPayload(action, fields);
    const expected = JSON.stringify(first);
    first.reviewer = 'changed';
    if (first.evidence_references) first.evidence_references.push('changed');
    assert.equal(JSON.stringify(buildReviewActionPayload(action, fields)), expected);
    assert.equal(JSON.stringify(fields), before);
    if (action === 'resolve_evidence_request') {
      assert.deepEqual(JSON.parse(expected).evidence_references, ['evidencia://uno', 'evidencia://uno', 'prueba:ñ']);
    }
  });
}
