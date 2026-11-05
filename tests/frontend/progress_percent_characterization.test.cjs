'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const source = fs.readFileSync(path.join(root, 'apps/web/app/assessment/assessmentProgress.ts'), 'utf8');
// Frozen whole-module source from main 4e792d86, captured before the cleanup.
const baseline = fs.readFileSync(path.join(__dirname, 'progress_percent_before.txt'), 'utf8');
function load(text) {
  const scope = {exports: {}};
  vm.runInNewContext(ts.transpileModule(text, {compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  }}).outputText, scope);
  return scope.exports;
}
const before = load(baseline), after = load(source);
function outcome(fn, phase, result, running) {
  try { return {value: fn(phase, result, running)}; }
  catch (error) { return {error: error.name, message: error.message}; }
}
function freeze(value) {
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}
const values = [undefined, null, -Infinity, Infinity, NaN, -100, -0, 0, 0.005, 0.5, 37, 99.999, 100, 200,
  '', '0', '37.5', 'bad', false, true, [], {}, Symbol('unsupported-number')];
const profiles = [[undefined, undefined, undefined, undefined]];
for (const value of values) {
  profiles.push([value, value, value, value]);
  for (let slot = 0; slot < 4; slot++) {
    const profile = [undefined, undefined, undefined, undefined];
    profile[slot] = value;
    profiles.push(profile);
  }
}
profiles.push([0, 52, 20, 75], [80, 0, 92, 0], [undefined, undefined, undefined, 100]);
const stages = [undefined, null, '', 'unknown', 'unknown_stage', 'unknown stage', 'none', 'null', 'undefined', 'n/a', 'na', 'invalid', ...before.COMPREHENSIVE_STAGE_IDS, ' AUTHORIZATION-AND-SCOPE ', ' CLIENT-ACCEPTANCE-PENDING '];
const phases = ['idle', 'checking', 'starting', 'running', 'failed', 'timed_out', 'unavailable', 'complete', 'review_required'];
const completed = [[], ['first'], Array.from(before.COMPREHENSIVE_STAGE_IDS), Array(30).fill('extra')];

test('actual progressPercent matches complete pre-change outputs for stage and numeric boundaries', () => {
  let count = 0;
  function compare(phase, result, running) {
    freeze(result);
    assert.deepStrictEqual(outcome(after.progressPercent, phase, result, running),
      outcome(before.progressPercent, phase, result, running), `case ${count}`);
    count++;
  }
  for (const phase of phases) for (const running of [false, true]) {
    compare(phase, null, running);
    for (const stage of stages) for (const profile of profiles) for (const completion of completed) {
      const [top, nested, canonical, active] = profile;
      compare(phase, {current_stage: stage, progress_percent: top, canonical_progress_percent: canonical,
        active_stage_progress_percent: active, completed_stages: completion,
        record: {progress_percent: nested}}, running);
      compare(phase, {progress_percent: top, canonical_progress_percent: canonical,
        active_stage_progress_percent: active, record: {current_stage: stage, progress_percent: nested,
          completed_stages: completion}}, running);
    }
    for (let length = 0; length <= before.COMPREHENSIVE_STAGE_IDS.length; length++) {
      for (const status of ['complete', 'completed', 'success', 'passed', 'verified', 'review_required', 'failed', 'unknown']) {
        const stage_results = Object.fromEntries(before.COMPREHENSIVE_STAGE_IDS.slice(0, length).map(id => [id, {status}]));
        compare(phase, {current_stage: 'unknown_stage', record: {stage_results}}, running);
        if (length > 1) {
          compare(phase, {record: {stage_results: {...stage_results, [before.COMPREHENSIVE_STAGE_IDS[0]]: {status: 'failed'}}}}, running);
        }
      }
    }
  }
  assert.equal(count, 640674);
});

const witnesses = [
  ['running', null, true], ['running', null, false],
  ['running', {current_stage: 'authorization_and_scope'}, true],
  ['running', {current_stage: 'immutable_repository_snapshot'}, true],
  ['running', {current_stage: 'authorization_and_scope', progress_percent: 42}, true],
  ['complete', null, false], ['review_required', null, false],
];
const predicate = 'running && stageIndex <= 0 && display === 0';
for (const [name, replacement] of [
  ['lost_running_guard', 'stageIndex <= 0 && display === 0'],
  ['lost_zero_stage', 'running && stageIndex < 0 && display === 0'],
  ['lost_unknown_stage', 'running && stageIndex === 0 && display === 0'],
  ['lost_display_guard', 'running && stageIndex <= 0'],
  ['wrong_stage_range', 'running && stageIndex >= 0 && display === 0'],
]) test(`negative control catches ${name}`, () => {
  assert.equal(source.split(predicate).length - 1, 1);
  const mutant = load(source.replace(predicate, replacement));
  assert(witnesses.some(args => JSON.stringify(outcome(mutant.progressPercent, ...args)) !== JSON.stringify(outcome(before.progressPercent, ...args))));
});
