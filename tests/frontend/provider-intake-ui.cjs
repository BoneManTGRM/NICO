// Defect: existing operator intake cannot be reached from ordinary operations UI.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const appRequire = createRequire(path.resolve('apps/web/package.json'));
const ts = appRequire('typescript');
const React = appRequire('react');
const {renderToStaticMarkup} = appRequire('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true},
  }).outputText, filename);
};
require.extensions['.css'] = module => { module.exports = {}; };
const Page = require(path.resolve('apps/web/app/operations/page.tsx')).default;
const markup = renderToStaticMarkup(React.createElement(Page));
assert.match(markup, /href="\/operations\/provider-intake"/, 'ordinary operations must expose authorized repository intake');
console.log('ordinary operations exposes repository intake');

const {payloadFor, readAttempt, submitIntake, ATTEMPT_KEY} = require(path.resolve('apps/web/app/operations/provider-intake/intake.ts'));
const Intake = require(path.resolve('apps/web/app/operations/provider-intake/provider-intake.tsx')).ProviderIntake;
const form = renderToStaticMarkup(React.createElement(Intake));
assert.match(form, /type="password"/);
assert.match(form, /name="expected_commit_sha"/);
const source = {repository: 'owner/private-fixture', expected_commit_sha: 'a'.repeat(40), customer_id: 'fixture-customer', project_id: 'fixture-project', authorized_by: 'AI test operator', authorization_scope: 'Synthetic test only', authorization_confirmed: true, report_language: 'en', execution_mode: 'internal_test'};
for (const field of ['client_name', 'project_name', 'primary_technical_contact', 'access_method']) assert.ok(form.includes(`name="${field}"`));
const finalInput = {...source, client_name: 'SYNTHETIC SOFTWARE-TEST INFORMATION client', project_name: 'SYNTHETIC SOFTWARE-TEST INFORMATION project', primary_technical_contact: 'Synthetic contact, no real person', access_method: 'Server-held read-only GitHub access'};
const finalPayload = payloadFor(finalInput);
assert.equal(finalPayload.client_name, finalInput.client_name);
assert.deepEqual(finalPayload.human_evidence.stakeholder_context.evidence.authorized_scope, [source.authorization_scope]);
assert.deepEqual(finalPayload.human_evidence.stakeholder_context.evidence.primary_technical_contact, [finalInput.primary_technical_contact]);
for (const field of ['client_name', 'project_name', 'primary_technical_contact', 'access_method']) assert.throws(() => payloadFor({...finalInput, [field]: ''}), /engagement_identity_required/);
assert.throws(() => payloadFor({...source, execution_mode: 'production_engagement'}), /engagement_identity_required/);
function storage() {
  const records = new Map();
  return {getItem: key => records.get(key) ?? null, setItem: (key,value) => records.set(key,value), removeItem: key => records.delete(key)};
}
const run = 'comprun_' + 'b'.repeat(32);
const receipt = {operation: 'operator_provider_intake_started', run_id: run, repository_snapshot: {run_id: run, repository: 'owner/private-fixture', commit_sha: 'a'.repeat(40), status: 'attached', exact_commit_verified: true}};
(async () => {
  assert.throws(() => payloadFor({...source, authorization_confirmed: false}), /authorization_required/);
  assert.throws(() => payloadFor({...source, expected_commit_sha: 'main'}), /invalid_source/);
  assert.throws(() => payloadFor({...source, repository: 'https://github.com/owner/repo'}), /invalid_source/);
  for (const repository of ['owner/.github', 'owner/widget.git', 'owner/widget.git-tools']) {
    await assert.rejects(submitIntake({...source, repository}, 'credential', storage(), async () => {assert.fail('rewritten source must never be sent');}), /invalid_source/);
  }
  const store = storage(); let calls = 0;
  const send = async (url, init) => {
    calls++;
    assert.equal(url, '/api/nico/providers/operator/comprehensive-intake');
    assert.equal(init.headers['X-NICO-Admin-Token'], 'synthetic-test-credential');
    assert.equal(init.redirect, 'error');
    assert.equal(readAttempt(store).state, 'pending');
    const body = JSON.parse(init.body);
    assert.equal(body.expected_commit_sha, 'a'.repeat(40));
    assert.equal(body.provider, 'github');
    assert.equal(body.authorized, true);
    assert.equal(body.authorization_confirmed, true);
    assert.equal(body.execution_mode, 'internal_test');
    assert.equal(body.admin_token, undefined);
    return Response.json(receipt);
  };
  const result = await submitIntake({...source, admin_token: 'must-not-cross'}, 'synthetic-test-credential', store, send);
  assert.equal(result.state, 'received'); assert.equal(result.runId, run);
  assert.deepEqual(readAttempt(store), result);
  assert.ok(!store.getItem(ATTEMPT_KEY).includes('synthetic-test-credential'));
  await assert.rejects(submitIntake(source, 'credential', store, send), /existing_attempt/);
  assert.equal(calls, 1);
  const pending = storage(); let finish;
  const outstanding = submitIntake(source, 'credential', pending, () => new Promise(resolve => {finish = resolve;}));
  await assert.rejects(submitIntake(source, 'credential', pending, send), /existing_attempt/);
  finish(Response.json(receipt)); await outstanding;
  for (const fakeSend of [async () => {throw new Error('connection lost');}, async () => Response.json({...receipt, repository_snapshot: {...receipt.repository_snapshot, commit_sha: 'c'.repeat(40)}}), async () => Response.json({detail: {code: 'provider_unavailable'}}, {status: 503})]) {
    const uncertain = storage();
    assert.equal((await submitIntake(source, 'credential', uncertain, fakeSend)).state, 'uncertain');
    await assert.rejects(submitIntake(source, 'credential', uncertain, send), /existing_attempt/);
  }
  const mismatch = await submitIntake(source, 'credential', storage(), async () => Response.json({...receipt, repository_snapshot: {...receipt.repository_snapshot, commit_sha: 'c'.repeat(40)}}));
  assert.equal(mismatch.runId, run, 'retain a syntactically valid run ID for recovery even when the source receipt conflicts');
  const rejectedStore = storage();
  const rejected = await submitIntake(source, 'credential', rejectedStore, async () => Response.json({detail: {code: 'provider_credential_reference_missing', phase: 'provider_preflight', assessment_started: false}}, {status: 409, headers: {'X-NICO-Correlation-ID': 'corr_12345678'}}));
  assert.equal(rejected.httpStatus, 409, 'retain rejection status for reconciliation');
  assert.equal(rejected.failureCode, 'provider_credential_reference_missing');
  assert.equal(rejected.correlationId, 'corr_12345678');
  assert.deepEqual(readAttempt(rejectedStore), rejected);
  assert.equal(rejected.state, 'uncertain', 'diagnostic evidence must not silently unlock resubmission');
  await assert.rejects(submitIntake(source, 'credential', rejectedStore, send), /existing_attempt/);
  const unsafe = await submitIntake(source, 'credential', storage(), async () => Response.json({detail: {code: 'secret-token-must-not-retain', message: 'private response text'}}, {status: 422, headers: {'X-NICO-Correlation-ID': 'unsafe value'}}));
  assert.equal(unsafe.httpStatus, 422);
  assert.equal(unsafe.failureCode, undefined);
  assert.equal(unsafe.correlationId, undefined);
  const proxy = require(path.resolve('apps/web/app/api/nico/providers/operator/comprehensive-intake/route.ts'));
  const originalFetch = global.fetch;
  const previousEnv = Object.fromEntries(['NICO_API_URL', 'NICO_BACKEND_URL', 'NEXT_PUBLIC_NICO_API_URL'].map(key => [key, process.env[key]]));
  try {
    process.env.NICO_API_URL = 'https://nico.synthetic.invalid';
    delete process.env.NICO_BACKEND_URL; delete process.env.NEXT_PUBLIC_NICO_API_URL;
    global.fetch = async (url, init) => {
      assert.equal(init.headers['X-NICO-Correlation-ID'], '9901e29d-a7fc-4a14-b1cb-dab6a0fcf945');
      assert.equal(init.headers['X-Request-ID'], init.headers['X-NICO-Correlation-ID']);
      return Response.json({detail: {code: 'provider_credential_reference_missing'}}, {status: 409, headers: {'X-NICO-Correlation-ID': init.headers['X-NICO-Correlation-ID']}});
    };
    const req = new Request('https://app.synthetic.invalid/api/nico/providers/operator/comprehensive-intake', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-NICO-Admin-Token': 'synthetic-only', 'X-Request-ID': '9901e29d-a7fc-4a14-b1cb-dab6a0fcf945'}, body: JSON.stringify(source)});
    req.nextUrl = new URL(req.url);
    const response = await proxy.POST(req);
    assert.equal(response.status, 409);
    assert.equal(response.headers.get('X-NICO-Correlation-ID'), '9901e29d-a7fc-4a14-b1cb-dab6a0fcf945');
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
  } finally {
    global.fetch = originalFetch;
    for (const [key, value] of Object.entries(previousEnv)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
  }
  const denied = storage();
  await assert.rejects(submitIntake(source, 'credential', denied, async () => Response.json({detail:{code:'authorized_nico_operator_required'}}, {status:403})), /admin_required/);
  assert.equal(readAttempt(denied), null);
  await assert.rejects(submitIntake(source, '', storage(), send), /admin_required/);
  await assert.rejects(submitIntake(source, 'credential', {getItem: () => null, setItem: () => {throw new Error('storage unavailable');}}, send), /storage unavailable/);
  assert.equal(calls, 1);
  console.log('intake authorization, source binding, credential isolation, receipt validation, pre-write locking, reload recovery, and uncertain-response duplicate prevention passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
