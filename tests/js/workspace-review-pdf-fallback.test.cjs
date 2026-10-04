// Owned isolated fixtures execute the real Workspace function and production helper.
'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {webcrypto, createHash} = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/web/package.json'))('typescript');
const workspacePath = path.join(root, 'apps/web/app/assessment/AssessmentWorkspace.tsx');
const workspace = fs.readFileSync(workspacePath, 'utf8');
const parsed = ts.createSourceFile(workspacePath, workspace, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const handlers = [], renderers = [];
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'downloadPdf') handlers.push(node);
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'renderReportActions') renderers.push(node);
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.equal(handlers.length, 1, 'Execute exactly the actual Workspace pending-PDF handler');
const actualHandler = workspace.slice(handlers[0].getStart(parsed), handlers[0].end);
const transpile = source => ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
}).outputText;
assert.equal(renderers.length,1,'Execute the actual report action renderer');
const actualRenderer=workspace.slice(renderers[0].getStart(parsed),renderers[0].end);
const compiledHandler = transpile(actualHandler+'\n'+actualRenderer) + '\nmodule.exports = {downloadPdf,renderReportActions};';
const compiledGuard = transpile(fs.readFileSync(path.join(root, 'apps/web/app/AssessmentReviewPdfDownload.tsx'), 'utf8'));
const run = 'comprun_owned_workspace_fixture';
const commit = 'a'.repeat(40), truth = 'b'.repeat(64);
const pdf = Buffer.from('%PDF-1.7\nOWNED SYNTHETIC BYTE-INTEGRITY FIXTURE\n%%EOF\n');
const hash = createHash('sha256').update(pdf).digest('hex');

function setup({source=commit, canonicalTruth=truth, overrides={}, language='en', fetchImpl, mismatch=false, withGuard=false}={}) {
  const calls=[], downloads=[], errors=[], actions=[], statuses=[], effects=[], listeners=new Map();
  let renderControls;
  class Element {
    constructor() {this.isConnected=true;this.attrs={};this.style={};}
    getAttribute(name) {return this.attrs[name] ?? null;}
    setAttribute(name,value) {this.attrs[name]=String(value);}
    removeAttribute(name) {delete this.attrs[name];}
    closest(selector) {return selector==='button'?button:container;}
    appendChild(node) {statuses.push(node);}
    querySelector() {return statuses.at(-1)||null;}
    blur() {}
    click() {downloads.push({url:this.href,filename:this.download});}
    remove() {this.isConnected=false;}
  }
  class HTMLButtonElement extends Element {constructor(){super();this.disabled=false;}}
  const container = new Element();
  container.attrs={'data-run-id':run,'data-commit-sha':source,'data-canonical-truth-sha256':canonicalTruth,
    'data-assessment-report-ready':'true','data-assessment-pdf-available':'true'};
  const button=new HTMLButtonElement();
  button.attrs={'data-assessment-pdf-kind':'localized-draft-pending-approval','data-report-language':'en',
    'data-assessment-action-disabled':'false'};
  const blobs=new Map();
  class FixtureURL extends URL {
    static createObjectURL(blob) {const key='blob:owned-'+blobs.size;blobs.set(key,blob);return key;}
    static revokeObjectURL(key) {blobs.delete(key);}
  }
  const timers=[];
  const document={activeElement:null,documentElement:{lang:'en'},body:{appendChild(){}},
    createElement:()=>new Element(),querySelectorAll:()=>[],
    addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>listeners.delete(name)};
  const window={scrollY:0,location:new URL('https://unit.invalid/assessment'),
    setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout(){}};
  const context=vm.createContext({document,window,URL:FixtureURL,Blob,Headers,Response,
    AbortSignal,AbortController,DOMException,Uint8Array,Element,HTMLButtonElement,Error,
    crypto:webcrypto,result:{run_id:run},report:{canonical_truth_sha256:canonicalTruth},
    immutableCommit:source,requestedReportLanguage:language,pdfAvailable:true,reportReady:true,
    artifactAction:null,approvedLocaleMismatch:mismatch,locale:'en',
    exactApprovedPdfAvailable:false,acceptedPdfIdentity:null,markdownAvailable:true,
    copied:false,artifactStatus:'',workspaceStyles:{reportActionBar:'fixture'},
    copyMarkdown(){},downloadApprovedPdf(){},
    reportLanguageLabel:value=>value,
    copy:{runIdMissing:'Run identity missing',pdfMissing:'Bound PDF unavailable',copy:'Copy',
      downloadReviewPdf:'Download review PDF',downloadApprovedPdf:'Download approved PDF',newApprovalRequired:'New approval required'},
    setArtifactAction(value){actions.push(value);context.artifactAction=value;renderControls?.();},
    setError(value){if(value)errors.push(value);},restoreArtifactScroll(){},
    apiUrl:value=>'/api/nico'+value,filenameFromResponse:(response,fallback)=>fallback,
    localizedArtifactError:async response=>Error('HTTP '+response.status),
    downloadBlob(blob,filename){downloads.push({blob,filename});},
    fetch:async(url,init)=>{calls.push({url,init});if(fetchImpl)return fetchImpl(url,init);return new Response(pdf,{headers:{
      'content-type':'application/pdf','x-nico-run-id':run,'x-nico-commit-sha':commit,
      'x-nico-report-language':language,'x-nico-assessment-rerun':'false',
      'x-nico-approval-status':'pending_human_approval','x-nico-delivery-status':'blocked_pending_human_approval',
      'x-nico-client-delivery-allowed':'false','x-nico-pdf-sha256':hash,'x-nico-artifact-sha256':hash,
      'x-nico-canonical-truth-sha256':truth,...overrides,
    }});},
    require(name) {
      if(name==='react') return {useEffect:fn=>effects.push(fn),useRef:value=>({current:value})};
      if(name==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
      if(name==='./assessment/assessmentLocale') return {reportLanguageForRequest:value=>value};
      throw Error('Unexpected import '+name);
    },module:{exports:{}},exports:{},
  });
  context.exports=context.module.exports;
  vm.runInContext(compiledGuard,context);
  const guard=context.module.exports;
  Object.assign(context,guard);
  context.module={exports:{}};context.exports=context.module.exports;
  vm.runInContext(compiledHandler,context);
  const actual=context.module.exports;
  let pending;
  renderControls=()=>{
    const tree=actual.renderReportActions();
    const children=tree.props.children.flat(Infinity).filter(Boolean);
    pending=children.find(child=>child.props?.['data-assessment-pdf-kind']==='localized-draft-pending-approval');
    assert.ok(pending,'Use the actual rendered pending-review action');
    for(const [name,value]of Object.entries(tree.props))if(name.startsWith('data-'))container.attrs[name]=String(value);
    for(const [name,value]of Object.entries(pending.props))if(name.startsWith('data-'))button.attrs[name]=String(value);
    button.disabled=pending.props.disabled;button.textContent=pending.props.children;
  };
  renderControls();
  if(withGuard){guard.default();for(const effect of effects)effect();}
  const handler=async(event={currentTarget:button})=>{
    let intercepted=false;
    listeners.get('click')?.({target:button,preventDefault(){intercepted=true;},stopPropagation(){},stopImmediatePropagation(){}});
    if(!intercepted)return pending.props.onClick(event);
    for(let i=0;i<1000&&button.getAttribute('aria-busy')==='true';i++)await new Promise(resolve=>setTimeout(resolve,5));
  };
  return {handler,button,container,context,calls,downloads,errors,actions,blobs,timers,statuses,renderControls};
}

for (const missing of ['source','truth']) {
  test('actual Workspace fallback rejects missing '+missing+' binding before retrieval',async()=>{
    const s=setup(missing==='source'?{source:'',withGuard:true}:{canonicalTruth:'',withGuard:true});
    await s.handler({currentTarget:s.button});
    assert.equal(s.calls.length,0);
    assert.equal(s.downloads.length,0);
    assert.equal(s.errors.length,1);
  });
}
for (const mismatch of ['digest','MIME','truth']) {
  test('actual Workspace fallback rejects wrong '+mismatch+' despite pending headers',async()=>{
    const overrides=mismatch==='digest'?{'x-nico-pdf-sha256':'c'.repeat(64),'x-nico-artifact-sha256':'c'.repeat(64)}
      :mismatch==='MIME'?{'content-type':'text/html'}:{'x-nico-canonical-truth-sha256':'c'.repeat(64)};
    const s=setup({overrides});
    await s.handler({currentTarget:s.button});
    assert.equal(s.calls.length,1);
    assert.equal(s.downloads.length,0);
    assert.equal(s.errors.length,1);
  });
}
test('actual Workspace fallback retrieves one verified bound draft with a body deadline',async()=>{
  const s=setup();
  await s.handler({currentTarget:s.button});
  assert.equal(s.calls.length,1);
  assert.equal(s.calls[0].init.method,'GET');
  assert.equal(s.calls[0].init.cache,'no-store');
  assert.ok(s.calls[0].init.signal,'The actual fallback must retain a body-inclusive cancellation deadline');
  assert.equal(s.downloads.length,1);
  assert.equal(s.errors.length,0);
});

for(const language of ['en','es-MX'])test('actual rendered Workspace '+language+' fallback preserves exact verified bytes',async()=>{
  const s=setup({language});await s.handler();
  assert.equal(s.calls.length,1);assert.equal(s.downloads.length,1);
  const blob=s.blobs.get(s.downloads[0].url);
  assert.deepEqual(Buffer.from(await blob.arrayBuffer()),pdf);
  assert.match(s.downloads[0].filename,new RegExp('-'+language+'-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf$'));
});
for(const header of [
  {'x-nico-approval-status':'approved_final'}, {'x-nico-client-delivery-allowed':'true'},
  {'x-nico-accepted-pdf-sha256':hash}, {'x-nico-assessment-rerun':'true'},
])test('actual Workspace fallback rejects approval or lifecycle mismatch '+JSON.stringify(header),async()=>{
  const s=setup({overrides:header});await s.handler();
  assert.equal(s.downloads.length,0);assert.equal(s.errors.length,1);
});
for(const declaration of [undefined,'false','true'])test('locale reapproval remains mandatory: '+declaration,async()=>{
  const s=setup({mismatch:true,overrides:declaration===undefined?{}:{'x-nico-localized-artifact-requires-new-approval':declaration}});
  await s.handler();assert.equal(s.downloads.length,declaration==='true'?1:0);
});
const validResponse=()=>new Response(pdf,{headers:{
  'content-type':'application/pdf','x-nico-run-id':run,'x-nico-commit-sha':commit,
  'x-nico-report-language':'en','x-nico-assessment-rerun':'false',
  'x-nico-approval-status':'pending_human_approval','x-nico-delivery-status':'blocked_pending_human_approval',
  'x-nico-client-delivery-allowed':'false','x-nico-pdf-sha256':hash,'x-nico-artifact-sha256':hash,
  'x-nico-canonical-truth-sha256':truth,
}});
for(const change of ['run','commit','truth','language','not-ready','detached','accepted']){
  test('actual Workspace delayed body rejects stale '+change+' before handoff',async()=>{
    let release;const r=validResponse();r.arrayBuffer=()=>new Promise(resolve=>{release=resolve;});
    const s=setup({fetchImpl:async()=>r});const operation=s.handler();
    while(!release)await new Promise(resolve=>setImmediate(resolve));
    if(change==='run')s.container.attrs['data-run-id']='comprun_other';
    if(change==='commit')s.container.attrs['data-commit-sha']='c'.repeat(40);
    if(change==='truth')s.container.attrs['data-canonical-truth-sha256']='c'.repeat(64);
    if(change==='language')s.button.attrs['data-report-language']='es-MX';
    if(change==='not-ready')s.container.attrs['data-assessment-report-ready']='false';
    if(change==='detached')s.button.isConnected=false;
    if(change==='accepted')s.button.attrs['data-assessment-pdf-kind']='accepted-edition';
    release(pdf.buffer.slice(pdf.byteOffset,pdf.byteOffset+pdf.byteLength));await operation;
    assert.equal(s.downloads.length,0);assert.equal(s.errors.length,0);
    assert.doesNotMatch(s.statuses.at(-1)?.textContent||'',/verified and sent/);
  });
}
test('actual Workspace repeated active clicks dispatch once, timeout and explicit retry remain bounded',async()=>{
  let attempt=0;
  const s=setup({fetchImpl:async(url,init)=>{
    if(++attempt===1)return new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true}));
    return validResponse();
  }});
  const first=s.handler();await s.handler();assert.equal(s.calls.length,1);
  s.timers.find(timer=>timer.ms===255000).fn();await first;
  assert.equal(s.downloads.length,0);assert.equal(s.errors.length,1);
  await s.handler();assert.equal(s.calls.length,2);assert.equal(s.downloads.length,1);
});
test('actual Workspace interrupted body does not hand off and explicit retry uses retained GET only',async()=>{
  let attempt=0;const s=setup({fetchImpl:async()=>{
    const r=validResponse();if(++attempt===1)r.arrayBuffer=async()=>{throw Error('Owned interrupted body');};return r;
  }});
  await s.handler();assert.equal(s.downloads.length,0);assert.equal(s.errors.length,1);
  await s.handler();assert.equal(s.downloads.length,1);assert.equal(s.calls.length,2);
  assert.ok(s.calls.every(call=>call.init.method==='GET'));
});
