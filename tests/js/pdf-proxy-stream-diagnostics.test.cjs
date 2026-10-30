'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const source = fs.readFileSync(path.join(root, 'apps/web/app/api/nico/assessment/[...path]/route.ts'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
const secret = 'SYNTHETIC-PRIVATE-CONTENT';
function setup(fetcher, brokenLogger = false) {
  let now = 1000;
  const logs = [], calls = [], deadlines = [];
  const module = {exports: {}};
  vm.runInNewContext(compiled, {module, exports: module.exports, URL, Headers, Response,
    ReadableStream, DOMException, Date: class extends Date {static now() {return now;}},
    AbortSignal: {timeout(ms) {deadlines.push(ms); return new AbortController().signal;}},
    crypto: require('node:crypto').webcrypto,
    console: {info(line) {if (brokenLogger) throw new Error(secret); logs.push(JSON.parse(line));}},
    process: {env: {NODE_ENV: 'production', NICO_API_URL: 'https://backend.invalid'}},
    fetch: async (url, init) => {calls.push({url, init}); now = 1005; return fetcher();},
  });
  const request = {method: 'GET', nextUrl: new URL('https://app.invalid/api/nico/assessment'),
    headers: new Headers({'x-request-id': secret, authorization: secret}),
    cookies: {get: () => ({value: secret})}};
  const invoke = (suffix = ['report', 'pdf']) => module.exports[request.method](request,
    {params: Promise.resolve({path: ['comprehensive-run', secret, ...suffix]})});
  return {logs, calls, deadlines, request, invoke, clock(value) {now = value;}};
}
function privacy(logs) {
  assert.ok(!JSON.stringify(logs).includes(secret));
  for (const row of logs) assert.deepEqual(Object.keys(row).sort(), [
    'event', 'trace_id', 'outcome', 'elapsed_ms', 'headers_ms', 'first_byte_read_ms',
    'upstream_body_bytes', ...(row.upstream_status === undefined ? [] : [
      'upstream_status', 'declared_content_length', 'content_encoding', 'transfer_encoding']),
  ].sort());
}
test('real stream stays incremental and preserves bytes, auth, metadata and deadline', async () => {
  let controller;
  const body = new ReadableStream({start(c) {controller = c;}}, {highWaterMark: 0});
  const s = setup(() => new Response(body, {headers: {'content-type': 'application/pdf',
    'content-length': '5', 'x-nico-client-delivery-allowed': 'false', 'x-nico-artifact-sha256': 'a'.repeat(64)}}));
  const response = await s.invoke();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-length'), '5');
  assert.equal(response.headers.get('x-nico-client-delivery-allowed'), 'false');
  assert.equal(response.headers.get('x-nico-artifact-sha256'), 'a'.repeat(64));
  assert.equal(response.headers.get('cache-control'), 'no-store, private, max-age=0');
  assert.equal(s.calls[0].init.headers.get('x-nico-operator-session'), secret);
  assert.equal(s.calls[0].init.redirect, 'manual');
  assert.deepEqual(s.deadlines, [240000]);
  assert.equal(response.headers.get('x-nico-proxy-headers-ms'), '5');
  assert.equal(response.headers.get('x-nico-proxy-trace-id'), s.logs[0].trace_id);
  assert.equal(s.logs.length, 1);
  const reader = response.body.getReader();
  s.clock(1008); controller.enqueue(new Uint8Array([37, 80]));
  assert.deepEqual((await reader.read()).value, new Uint8Array([37, 80]));
  s.clock(1012); controller.enqueue(new Uint8Array([68, 70, 10]));
  assert.deepEqual((await reader.read()).value, new Uint8Array([68, 70, 10]));
  s.clock(1017); controller.close();
  assert.equal((await reader.read()).done, true);
  assert.equal(s.logs.length, 2);
  assert.equal(s.logs[1].outcome, 'upstream_complete');
  assert.equal(s.logs[1].headers_ms, 5);
  assert.equal(s.logs[1].first_byte_read_ms, 8);
  assert.equal(s.logs[1].elapsed_ms, 17);
  assert.equal(s.logs[1].upstream_body_bytes, 5);
  privacy(s.logs);
});
test('late stream failure keeps HTTP200 and fails the body read with safe partial metrics', async () => {
  let controller;
  const s = setup(() => new Response(new ReadableStream({start(c) {controller = c;}}, {highWaterMark: 0}),
    {headers: {'content-length': '2009397', 'content-encoding': 'gzip', 'transfer-encoding': 'chunked'}}));
  const response = await s.invoke();
  const reader = response.body.getReader();
  controller.enqueue(new TextEncoder().encode(secret));
  await reader.read();
  s.clock(1020); controller.error(new Error(secret));
  await assert.rejects(reader.read());
  assert.equal(response.status, 200); // A post-header failure cannot become a JSON502.
  assert.equal(s.calls.length, 1);
  assert.equal(s.logs[1].outcome, 'body_error');
  assert.equal(s.logs[1].upstream_body_bytes, secret.length);
  assert.equal(s.logs[1].declared_content_length, 2009397);
  assert.equal(s.logs[1].content_encoding, 'gzip');
  assert.equal(s.logs[1].transfer_encoding, 'chunked');
  privacy(s.logs);
});
test('stalled stream has headers without completion; cancellation propagates once', async () => {
  let cancelled = 0, pulls = 0;
  const s = setup(() => new Response(new ReadableStream({pull() {pulls++;}, cancel() {cancelled++;}}, {highWaterMark: 0})));
  const response = await s.invoke();
  assert.equal(pulls, 0);
  const reader = response.body.getReader();
  const waiting = reader.read();
  await Promise.resolve();
  assert.equal(s.logs.length, 1);
  s.clock(1030); await reader.cancel(secret); await waiting;
  assert.equal(cancelled, 1);
  assert.equal(s.logs.length, 2);
  assert.equal(s.logs[1].outcome, 'consumer_cancelled');
  assert.equal(s.logs[1].upstream_body_bytes, 0);
  assert.equal(s.logs[1].first_byte_read_ms, null);
  privacy(s.logs);
});
test('metadata is bounded and never copies arbitrary upstream header values', async () => {
  const s = setup(() => new Response(secret, {headers: {'content-length': secret,
    'content-encoding': secret, 'transfer-encoding': secret, 'set-cookie': secret}}));
  const response = await s.invoke(); await response.text();
  assert.equal(response.headers.get('set-cookie'), null);
  assert.equal(s.logs[1].declared_content_length, null);
  assert.equal(s.logs[1].content_encoding, 'other');
  assert.equal(s.logs[1].transfer_encoding, 'other');
  privacy(s.logs);
});
test('declared length and observed bytes stay separate; no success or delivery inferred', async () => {
  const s = setup(() => new Response('12345', {headers: {'content-length': '2', 'content-encoding': 'gzip'}}));
  const response = await s.invoke(); assert.equal(await response.text(), '12345');
  assert.equal(s.logs[1].declared_content_length, 2);
  assert.equal(s.logs[1].upstream_body_bytes, 5);
  assert.equal(s.logs[1].outcome, 'upstream_complete'); // EOF only; no integrity/approval assertion.
  privacy(s.logs);
});
test('pre-header timeout retains existing response and exposes no error text in diagnostics', async () => {
  const s = setup(() => {throw new DOMException(secret, 'TimeoutError');});
  const response = await s.invoke();
  assert.equal(response.status, 504);
  assert.equal((await response.json()).detail.timeout_ms, 240000);
  assert.equal(s.logs.length, 1);
  assert.equal(s.logs[0].outcome, 'before_response_error');
  assert.equal(s.logs[0].headers_ms, null);
  privacy(s.logs);
});
test('logger failure cannot break streaming and null body remains null', async () => {
  const s = setup(() => new Response('pdf'), true);
  assert.equal(await (await s.invoke()).text(), 'pdf');
  const empty = setup(() => new Response(null, {status: 204}));
  assert.equal((await empty.invoke()).body, null);
  assert.equal(empty.logs[1].outcome, 'no_body');
});
test('unauthenticated and non-PDF requests produce no transfer telemetry', async () => {
  const s = setup(() => new Response('json'));
  s.request.cookies.get = () => undefined;
  assert.equal((await s.invoke()).status, 401);
  assert.equal(s.calls.length, 0); assert.equal(s.logs.length, 0);
  s.request.cookies.get = () => ({value: secret});
  assert.equal((await s.invoke(['report', 'json'])).status, 200);
  assert.equal(s.logs.length, 0);
});


test('prepared PDF keeps authenticated streaming checksum and 240-second diagnostics',async()=>{
  const s=setup(()=>new Response('%PDF synthetic',{headers:{'content-type':'application/pdf',
    'x-nico-artifact-sha256':'a'.repeat(64),'x-nico-client-delivery-allowed':'false'}}));
  const response=await s.invoke(['review-pdf','es-MX','pdf']);await response.text();
  assert.equal(response.status,200);assert.deepEqual(s.deadlines,[240000]);
  assert.equal(s.calls[0].init.headers.get('x-nico-operator-session'),secret);
  assert.equal(response.headers.get('x-nico-artifact-sha256'),'a'.repeat(64));
  assert.equal(response.headers.get('x-nico-client-delivery-allowed'),'false');
  assert.equal(s.logs.at(-1).outcome,'upstream_complete');privacy(s.logs);
});
test('preparation status is authenticated with a 30-second deadline',async()=>{
  const s=setup(()=>new Response('{}'));await s.invoke(['review-pdf','en']);
  assert.deepEqual(s.deadlines,[30000]);assert.equal(s.calls.length,1);
  assert.equal(s.calls[0].init.headers.get('x-nico-operator-session'),secret);
});
for(const suffix of [['review-pdf','en'],['review-pdf','es-MX','cancel']])test('preparation mutation preserves cookie CSRF '+suffix.join('/'),async()=>{
  const s=setup(()=>new Response('{}'));s.request.method='POST';s.request.arrayBuffer=async()=>new ArrayBuffer(0);
  assert.equal((await s.invoke(suffix)).status,403);assert.equal(s.calls.length,0);
  s.request.headers.set('origin','https://app.invalid');assert.equal((await s.invoke(suffix)).status,200);
  assert.equal(s.calls.length,1);
});
test('prepared PDF and cancellation reject wrong methods without upstream work',async()=>{
  const s=setup(()=>new Response('{}'));
  assert.equal((await s.invoke(['review-pdf','en','cancel'])).status,405);
  s.request.method='POST';assert.equal((await s.invoke(['review-pdf','en','pdf'])).status,405);
  assert.equal(s.calls.length,0);
});

test('storage compatibility uses existing authenticated GET proxy and bounded read deadline', async () => {
  const s = setup(() => Response.json({probe_complete: true, lifecycle_qualified: false}));
  s.request.nextUrl.search = '?storage_compatibility=true';
  const response = await s.invoke(['review-pdf', 'es-MX']);
  assert.equal(response.status, 200);
  assert.equal(s.calls.length, 1);
  assert.ok(String(s.calls[0].url).endsWith('/review-pdf/es-MX?storage_compatibility=true'));
  assert.deepEqual(s.deadlines, [30000]);
  assert.equal(s.calls[0].init.method, 'GET');
  assert.equal((await response.json()).lifecycle_qualified, false);
});

test('retained binding metadata uses existing authenticated bounded GET proxy', async () => {
  const body = JSON.stringify({schema:'nico.pdf-retained-binding.v1',status:'unavailable',binding:null,
    snapshot_validated:false,lifecycle_qualified:false,activation_authorized:false});
  const s=setup(()=>new Response(body,{headers:{'content-type':'application/json'}}));
  s.request.nextUrl.search='?retained_binding=true';
  const result=await s.invoke(['review-pdf','es-MX']);
  assert.equal(await result.text(),body);
  assert.ok(String(s.calls[0].url).endsWith('/review-pdf/es-MX?retained_binding=true'));
  assert.equal(s.calls[0].init.method,'GET');
  assert.equal(s.calls[0].init.headers.get('x-nico-operator-session'),secret);
  assert.equal(s.calls[0].init.redirect,'manual');
  assert.deepEqual(s.deadlines,[30000]);
  assert.equal(result.headers.get('cache-control'),'no-store, private, max-age=0');
  privacy(s.logs);
});

test('disabled canary ledger diagnostic preserves authenticated GET and bounded proxy', async () => {
  const body=JSON.stringify({schema:'nico.pdf-canary-ledger-read.v1',status:'unavailable',query_complete:false,
    scoped_rows_present:null,exact_source_row_present:null,rows:[]});
  const s=setup(()=>new Response(body,{headers:{'content-type':'application/json'}}));
  s.request.nextUrl.search='?canary_ledger=true';
  const response=await s.invoke(['review-pdf','es-MX']);
  assert.equal(await response.text(),body);
  assert.ok(String(s.calls[0].url).endsWith('/review-pdf/es-MX?canary_ledger=true'));
  assert.equal(s.calls[0].init.method,'GET');
  assert.equal(s.calls[0].init.headers.get('x-nico-operator-session'),secret);
  assert.equal(s.calls[0].init.redirect,'manual');
  assert.deepEqual(s.deadlines,[30000]);
  assert.equal(response.headers.get('cache-control'),'no-store, private, max-age=0');
  privacy(s.logs);
});

test('admission error preserves safe correlation header and one upstream call',async()=>{
  const trace='c'.repeat(32);
  const s=setup(()=>Response.json({detail:'review_pdf_commit_outcome_unknown'},
    {status:503,headers:{'x-nico-admission-trace':trace}}));
  s.request.method='POST';s.request.headers.set('origin',s.request.nextUrl.origin);s.request.arrayBuffer=async()=>new TextEncoder().encode('{}').buffer;
  const result=await s.invoke(['review-pdf','es-MX']);
  assert.equal(result.status,503);assert.equal(result.headers.get('x-nico-admission-trace'),trace);
  assert.equal((await result.json()).detail,'review_pdf_commit_outcome_unknown');
  assert.equal(s.calls.length,1);
});
