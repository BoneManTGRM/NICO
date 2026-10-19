'use strict';
// Isolated actual TSX renderer, not browser/production evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const source = fs.readFileSync(path.join(root, 'apps/web/app/assessment/AssessmentWorkspace.tsx'), 'utf8');
const parsed = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declarations = [];
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'renderReportActions') declarations.push(node.getText(parsed));
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.equal(declarations.length, 1);
const baseline = fs.readFileSync(path.join(__dirname, 'report_actions_before.txt'), 'utf8');
const compiled = ts.transpileModule(declarations[0] + '\n' + baseline.replace('function renderReportActions()', 'function beforeReportActions()'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
}).outputText;

test('complete rendered trees and callback identities match the pre-change renderer across 30,720 states', () => {
  const calls = [];
  const callbacks = Object.fromEntries(['copyMarkdown', 'downloadApprovedPdf', 'downloadPdf', 'persistReportLocale'].map(name => [name, (...args) => calls.push({name, args})]));
  const scope = {
    ...callbacks, exports: {}, workspaceStyles: {reportActionBar: 'fixture'}, immutableCommit: 'a'.repeat(40),
    report: {canonical_truth_sha256: 'b'.repeat(64)},
    copy: {copy: 'Copy', copied: 'Copied', downloadReviewPdf: 'Review PDF', downloadApprovedPdf: 'Approved PDF', newApprovalRequired: 'Approval required'},
    reportLanguageLabel: value => `label:${value}`,
    canonicalReportLanguage: value => value === 'es-MX' ? 'es-MX' : 'en',
    require(name) {
      assert.equal(name, 'react/jsx-runtime');
      return {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props})};
    },
  };
  vm.runInNewContext(compiled, scope);
  function normalize(value) {
    if (typeof value === 'function') return Object.entries(callbacks).find(([, callback]) => callback === value)?.[0] || 'localeFallback';
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalize(item)]));
    return value;
  }
  function buttons(node, output = []) {
    if (!node || typeof node !== 'object') return output;
    if (Array.isArray(node)) {node.forEach(child => buttons(child, output)); return output;}
    if (node.type === 'button') output.push(node);
    buttons(node.props?.children, output);
    return output;
  }
  let count = 0;
  for (const locale of ['en', 'es-MX'])
  for (const requestedReportLanguage of ['en', 'es-MX'])
  for (const result of [null, {run_id: ''}, {run_id: 'run /?&ñ', report_language: 'en'}, {run_id: 'run /?&ñ', report_language: 'es-MX'}])
  for (const acceptedPdfIdentity of [null, {reportLanguage: 'en'}, {reportLanguage: 'es-MX'}])
  for (const artifactAction of [null, 'pdf', 'markdown', '', undefined])
  for (const artifactStatus of ['', 'Preparing report'])
  for (let mask = 0; mask < 64; mask++) {
    const booleans = Object.fromEntries(['reportReady', 'pdfAvailable', 'markdownAvailable', 'exactApprovedPdfAvailable', 'approvedLocaleMismatch', 'copied'].map((key, bit) => [key, !!(mask & (1 << bit))]));
    Object.assign(scope, booleans, {locale, requestedReportLanguage, result, acceptedPdfIdentity, artifactAction, artifactStatus});
    calls.length = 0;
    const before = scope.beforeReportActions();
    const after = scope.renderReportActions();
    assert.equal(calls.length, 0, 'Rendering must not invoke action callbacks');
    assert.deepStrictEqual(normalize(after), normalize(before), `Complete output mismatch at case ${count}`);
    for (const button of buttons(after)) {
      const kind = button.props['data-assessment-pdf-kind'];
      const name = button.props['data-assessment-markdown-kind'] ? 'copyMarkdown'
        : kind === 'accepted-edition' ? 'downloadApprovedPdf'
        : kind === 'localized-draft-pending-approval' ? 'downloadPdf' : null;
      const event = {case: count}, second = {argument: 2};
      calls.length = 0;
      if (name) {
        assert.equal(button.props.onClick, callbacks[name], 'Direct callback identity must remain intact');
        button.props.onClick(event, second);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].name, name);
        assert.equal(calls[0].args.length, 2);
        assert.equal(calls[0].args[0], event);
        assert.equal(calls[0].args[1], second);
      } else {
        button.props.onClick(event, second);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].name, 'persistReportLocale');
        assert.deepStrictEqual(calls[0].args, ['en-US']);
      }
    }
    count++;
  }
  assert.equal(count, 30720);
});
