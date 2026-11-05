'use strict';
// Real transport/retry modules with synthetic responses; no network or assessment.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
function harness(body, status) {
  const cache = new Map();
  const calls = [];
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    const filename = path.join(root, 'apps/web/app/assessment', name + '.ts');
    const module = {exports: {}};
    cache.set(name, module);
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
    }).outputText, {module, exports: module.exports, URL, Headers, AbortController,
      window: {location: new URL('https://unit.invalid/assessment'),
        setTimeout(fn, ms) {if (ms <= 5000) queueMicrotask(fn); return 1;}, clearTimeout() {}},
      fetch: async (url, init) => {calls.push({url, method: init.method});
        return Response.json(body, {status, headers: {'x-request-id': 'synthetic-request'}});},
      require(relative) {assert.ok(relative.startsWith('./')); return load(relative.slice(2));},
    }, {filename});
    return module.exports;
  }
  return {load, calls};
}
for (const locale of ['en', 'es-MX']) {
  for (const status of [401, 403, 422, 503]) {
    test(`null error retains HTTP classification and localized copy: ${locale}/${status}`, async () => {
      const h = harness(null, status);
      const {parseJson, AssessmentApiError} = h.load('assessmentTransport');
      const copy = h.load('assessmentCopy').copyFor(locale);
      await assert.rejects(parseJson(Response.json(null, {status, headers: {'x-request-id': 'synthetic-request'}}), copy), error => {
        assert.ok(error instanceof AssessmentApiError);
        assert.equal(error.status, status);
        assert.equal(error.code, 'assessment_request_failed');
        assert.equal(error.requestId, 'synthetic-request');
        assert.equal(error.retryable, status === 503);
        assert.equal(error.message, `${copy.backendError} (${status})`);
        return true;
      });
    });
  }
  test(`null 401 exact-run GET is not retried as a network failure: ${locale}`, async () => {
    const h = harness(null, 401);
    const copy = h.load('assessmentCopy').copyFor(locale);
    await assert.rejects(h.load('assessmentRunRequests').requestWithRetry(
      '/assessment/comprehensive-run/comprun_synthetic', {method: 'GET'}, copy), error => {
      assert.equal(error.status, 401); assert.equal(error.retryable, false);
      assert.equal(error.requestId, 'synthetic-request'); return true;
    });
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].method, 'GET');
  });
  test(`structured errors and successful gated result remain unchanged: ${locale}`, async () => {
    const h = harness(null, 401);
    const {parseJson} = h.load('assessmentTransport');
    const copy = h.load('assessmentCopy').copyFor(locale);
    await assert.rejects(parseJson(Response.json({detail: {code: 'synthetic_code', retryable: false,
      request_id: 'body-request', message: 'must not leak machine details'}}, {status: 503}), copy), error => {
      assert.equal(error.code, 'synthetic_code'); assert.equal(error.retryable, false);
      assert.equal(error.requestId, 'body-request'); assert.equal(error.message, copy.backendError); return true;
    });
    const result = {run_id: 'comprun_synthetic', human_review_required: true, client_delivery_allowed: false};
    assert.deepEqual(await parseJson(Response.json(result), copy), result);
  });
}
for (const locale of ['en', 'es-MX']) {
  for (const method of ['GET', 'POST']) {
    test(`null 503 preserves bounded recovery and no mutation replay: ${locale}/${method}`, async () => {
      const h = harness(null, 503);
      const copy = h.load('assessmentCopy').copyFor(locale);
      await assert.rejects(h.load('assessmentRunRequests').requestWithRetry(
        '/assessment/comprehensive-run/comprun_synthetic', {method}, copy), error => {
        assert.equal(error.status, 503); assert.equal(error.requestId, 'synthetic-request');
        assert.equal(error.code, method === 'GET' ? 'assessment_request_failed' : 'assessment_mutation_outcome_unknown');
        assert.equal(error.retryable, method === 'GET'); return true;
      });
      assert.equal(h.calls.length, method === 'GET' ? 3 : 1);
      assert.ok(h.calls.every(call => call.method === method));
    });
  }
}
