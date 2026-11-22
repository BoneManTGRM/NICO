const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(require.resolve('typescript', {paths: [path.resolve('apps/web')]}));
function load(name) {
  const filename = path.resolve('apps/web/app/assessment', name);
  const source = readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const exported = {};
  vm.runInNewContext(output, {exports: exported, require, URLSearchParams});
  return exported;
}
const {scannerExecutionSummaryFor, draftScannerReviewNoticeFor} = load('assessmentEvidence.ts');
const {copyFor} = load('assessmentCopy.ts');
const run_id = 'comprun_'+'7'.repeat(32);
const commit_sha = 'a'.repeat(40);
const summary = {schema:'nico.scanner-execution-ui-summary.v1', run_id, commit_sha,
  status:'partial', percent:89, completed_count:8, execution_required_count:9,
  applicable_count:9, applicability_unproven_count:0};
function result(patch) {
  return {run_id, commit_sha, terminal:true, scanner_execution_summary:{...summary,...patch}};
}
test('finished draft with failed scan is explicit in both languages', () => {
  assert.match(draftScannerReviewNoticeFor(result(), 'en'), /^Draft generated · Scanner coverage incomplete/);
  assert.match(draftScannerReviewNoticeFor(result(), 'es-MX'), /^Borrador generado · Cobertura incompleta/);
});
test('complete evidence does not show a scanner warning', () => {
  assert.equal(draftScannerReviewNoticeFor(result({status:'complete', completed_count:9, percent:100}), 'en'), null);
});
test('unbound or malformed counters never claim complete', () => {
  for (const patch of [{run_id:'other'}, {commit_sha:'b'.repeat(40)}, {completed_count:-1},
                       {completed_count:10}, {completed_count:undefined}, {percent:Infinity},
                       {status:'complete'}, {status:'complete', completed_count:9, percent:89}]) {
    assert.equal(scannerExecutionSummaryFor(result(patch)), null);
    assert.match(draftScannerReviewNoticeFor(result(patch), 'en'), /not verified/);
  }
});
test('valid unknown state still warns; generic review copy does not claim analysis is complete', () => {
  assert.match(draftScannerReviewNoticeFor(result({status:'unknown',percent:null}), 'en'), /not verified/);
  assert.doesNotMatch(copyFor('en').comprehensiveReview, /technical analysis .* complete/i);
  assert.doesNotMatch(copyFor('es-MX').comprehensiveReview, /análisis técnico .* completos/i);
});
