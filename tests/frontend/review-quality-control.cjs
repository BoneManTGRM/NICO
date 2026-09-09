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
const QC = require(path.resolve('apps/web/app/operations/reviewer-queue/QualityControlRecords.tsx')).default;
function buttons(tree) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(buttons);
  return [...(tree.type === 'button' ? [tree] : []), ...buttons(tree.props?.children)];
}
for (const locale of ['en', 'es-MX']) {
  const selected = [];
  const props = {locale, busy:false, onSelect:id=>selected.push(id),
    records:{'NICO-QC-TEST':{qc_outcome:'disagree',qc_note:'TEST — evidencia <script>bad()</script>',reviewer:'TEST QC B',reviewed_at:'2026-09-09T02:00:00Z'}},
    blockers:{'NICO-QC-TEST':'quality_control_disagreement'},
    events:[{action:'quality_control',reviewer:'TEST QC B',recorded_at:'2026-09-09T02:00:00Z',payload:{candidate_id:'NICO-QC-TEST',qc_outcome:'disagree',qc_note:'TEST — retained historical disagreement'}}]};
  const tree = QC(props), markup = renderToStaticMarkup(tree);
  assert.ok(markup.includes('TEST QC B') && markup.includes('NICO-QC-TEST'));
  assert.ok(markup.includes('retained historical disagreement'));
  assert.ok(markup.includes(locale === 'en' ? 'QC disagrees' : 'control de calidad discrepa'));
  assert.ok(markup.includes('&lt;script&gt;') && !markup.includes('<script>'));
  const controls = buttons(tree);
  assert.equal(controls.length,1);
  assert.equal(controls[0].props.type,'button');
  controls[0].props.onClick(); assert.deepEqual(selected,['NICO-QC-TEST']);
  assert.equal(buttons(QC({...props,busy:true}))[0].props.disabled,true);
  assert.equal(buttons(QC({...props,blockers:{}})).length,0);
  const stale = renderToStaticMarkup(QC({...props,blockers:{'NICO-QC-TEST':'quality_control_disposition_changed'}}));
  assert.ok(stale.includes(locale === 'en' ? 'decision changed' : 'decisión del revisor cambió'));
}
assert.equal(QC({records:null,blockers:null,events:null,locale:'en',busy:false,onSelect(){}}),null);
console.log('QC disagreement, changed-decision blocking, bilingual persisted notes/history, escaping, and exact selection passed');
