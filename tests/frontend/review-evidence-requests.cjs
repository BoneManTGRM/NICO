// Regression: a persisted request was counted but its ID was invisible, preventing resolution.
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
const Requests = require(path.resolve('apps/web/app/operations/reviewer-queue/EvidenceRequests.tsx')).default;
const request = {request_id: 'evidence_request_retained_001', candidate_id: 'NICO-SCAN-TEST', request_text: 'TEST — revisar ejecución y autorización <script>alert(1)</script>', owner: 'TEST fixture owner', status: 'open', requested_by: 'TEST Reviewer A', requested_at: '2026-09-09T01:00:00Z'};
function buttons(tree) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(buttons);
  return [...(tree.type === 'button' ? [tree] : []), ...buttons(tree.props?.children)];
}
for (const locale of ['en', 'es-MX']) {
  const selected = [];
  // Rehydration from an existing retained ledger must expose the exact ID, not only a count.
  const props = {requests: [null, {}, request], locale, busy: false, onResolve: id => selected.push(id)};
  const tree = Requests(props);
  const markup = renderToStaticMarkup(tree);
  assert.ok(markup.includes(request.request_id));
  assert.ok(markup.includes(request.candidate_id));
  assert.match(markup, /&lt;script&gt;/);
  assert.ok(!markup.includes('<script>'));
  const controls = buttons(tree);
  assert.equal(controls.length, 1);
  assert.equal(controls[0].props.type, 'button', 'selection must not submit a decision');
  controls[0].props.onClick();
  assert.deepEqual(selected, [request.request_id]);
  assert.equal(buttons(Requests({...props, busy: true}))[0].props.disabled, true);
  const resolved = {...request, status: 'resolved', resolution_note: 'TEST — evidencia vinculada', evidence_references: ['test://retained/source.py:7'], resolved_by: 'TEST Reviewer A', resolved_at: '2026-09-09T01:05:00Z'};
  const after = Requests({...props, requests: [resolved]});
  assert.equal(buttons(after).length, 0, 'resolved history must not invite duplicate resolution');
  const history = renderToStaticMarkup(after);
  assert.ok(history.includes(request.request_id));
  assert.ok(history.includes(resolved.resolution_note));
  assert.ok(history.includes(resolved.evidence_references[0]));
  assert.ok(history.includes(locale === 'en' ? 'Resolved' : 'Resuelta'));
}
assert.equal(Requests({requests: undefined, locale: 'en', busy: false, onResolve() {}}), null);
console.log('retained request reopening, exact-ID selection, busy guard, bilingual resolution history, and escaped evidence passed');
