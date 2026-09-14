/** Behavioral tests of the installed fetch bridge; isolated DOM/network, no live proof. */
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(require.resolve('typescript', {paths: [path.resolve('apps/web')]}));
const filename = path.resolve('apps/web/app/AssessmentFailureResponseBridge.tsx');
const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
}).outputText;
const runId = 'comprun_unit_publication';
const route = `/api/nico/assessment/comprehensive-run/${runId}/continue`;
async function observe(payload, requestRoute = route, httpStatus = 200) {
  const events = [];
  const original = new Response(JSON.stringify(payload), {status: httpStatus});
  const window = {location: {origin: 'https://unit.invalid'},
    fetch: async () => original, dispatchEvent: event => events.push(event.detail)};
  const context = {exports: {}, window, URL, Response,
    CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
    require: name => {
      if (name === 'react') return {useEffect: fn => fn()};
      if (name === './AssessmentApiTransportBridge') return {
        ASSESSMENT_FAILURE_EVENT: 'nico:assessment-request-failed', boundedWorkerFailure: () => null,
      };
      throw new Error(`Unexpected import: ${name}`);
    },
  };
  vm.runInNewContext(compiled, context, {filename});
  context.exports.default();
  const response = await window.fetch(requestRoute);
  return {original, response, body: await response.clone().json(), failures: events.filter(Boolean)};
}
const active = {run_id: runId, terminal: false, status: 'running',
  current_stage: 'final_comprehensive_report_generation', client_delivery_allowed: false,
  record: {status: 'running', terminal: false, stage_results: {
    final_comprehensive_report_generation: {status: 'running', reason: 'final_report_background_publication_in_progress'},
  }}};

for (const stale of [{}, {status: 'blocked'},
  {report_contract: {status: 'blocked', reason: 'final_report_not_yet_published'}}]) {
  test(`active publication remains unchanged with ${JSON.stringify(stale)}`, async () => {
    const payload = {...active, ...stale};
    const result = await observe(payload);
    assert.equal(result.response, result.original);
    assert.deepEqual(result.body, payload);
    assert.equal(result.failures.length, 0);
  });
}
test('missing explicit Comprehensive terminal authority cannot emit failure', async () => {
  const payload = {run_id: runId, status: 'blocked', record: {terminal: true}};
  const result = await observe(payload);
  assert.equal(result.response, result.original);
  assert.equal(result.failures.length, 0);
});
test('nested detail cannot override the active canonical response', async () => {
  const result = await observe({...active, detail: {status: 'blocked', terminal: true}});
  assert.equal(result.response, result.original);
  assert.equal(result.failures.length, 0);
});
for (const status of ['blocked', 'failed', 'error', 'interrupted', 'rejected']) {
  test(`explicit terminal ${status} remains blocked with exact diagnostics`, async () => {
    const result = await observe({...active, terminal: true, status,
      failure_stage: 'scanner_reconciliation', failure_code: 'unit_failure', failure_reason: 'Unit scanner failed'});
    assert.equal(result.body.status, status);
    assert.equal(result.body.run_id, runId);
    assert.equal(result.body.failure_code, 'unit_failure');
    assert.equal(result.body.failure_reason, 'Unit scanner failed');
    assert.equal(result.body.client_delivery_allowed, false);
    assert.equal(result.response.headers.get('X-NICO-Terminal-Failure'), 'true');
    assert.equal(result.failures.length, 1);
  });
}
test('terminal artifact mismatch still blocks delivery and names integrity failure', async () => {
  const result = await observe({...active, terminal: true, status: 'blocked',
    response_projection: {review_package_invalidated_by_artifact_mismatch: true}});
  assert.equal(result.body.failure_stage, 'final_report_artifact_integrity');
  assert.equal(result.body.failure_code, 'comprehensive_report_artifact_integrity_invalid');
  assert.equal(result.body.client_delivery_allowed, false);
  assert.equal(result.failures.length, 1);
});
test('normal pending human approval emits no failure', async () => {
  const result = await observe({...active, terminal: true, status: 'review_required',
    report_contract: {status: 'blocked', reason: 'pending_human_approval'}});
  assert.equal(result.response, result.original);
  assert.equal(result.failures.length, 0);
});
test('Comprehensive transport failure cannot invent a durable terminal result', async () => {
  const result = await observe({status: 'failed', terminal: true, run_id: runId}, route, 502);
  assert.equal(result.response.status, 502);
  assert.equal(result.failures.length, 0);
});
test('legacy Express terminal response retains its existing contract', async () => {
  const result = await observe({status: 'failed', run_id: 'exprun_unit', failure_code: 'legacy_failure'},
    '/api/nico/assessment/express-run/exprun_unit/status');
  assert.equal(result.body.failure_code, 'legacy_failure');
  assert.equal(result.failures.length, 1);
});
