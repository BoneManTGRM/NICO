const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(require.resolve('typescript', {paths: [path.resolve('apps/web')]}));
const filename = path.resolve('apps/web/app/assessment/assessmentEvidence.ts');
const output = ts.transpileModule(readFileSync(filename, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
const exportsObject = {};
vm.runInNewContext(output, {exports: exportsObject, require, URLSearchParams});
const stateFor = exportsObject.internalReviewStateFor;
for (const nested of [false, true]) test(`operator approval stays separate from specialist completion; nested=${nested}`, () => {
  const data = {status: 'review_required', operator_approval_status: 'approved', human_review_completed: false, client_delivery_allowed: true};
  const result = stateFor(nested ? {record: data} : data);
  assert.equal(result.operatorApprovalCompleted, true);
  assert.equal(result.completed, false);
  assert.equal(result.approvalCompleted, false);
  assert.equal(result.deliveryAllowed, true);
});
test('authorization alone or invalidated approval cannot imply approval', () => {
  for (const status of [undefined, 'invalidated_source_or_artifact_changed']) {
    assert.equal(stateFor({operator_approval_status: status, client_delivery_allowed: true}).operatorApprovalCompleted, false);
  }
});
