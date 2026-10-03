// Synthetic exact-run fixtures; no production assessment, approval or device claim.
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
const filename = path.join(root, 'apps/web/app/AssessmentReviewPdfDownload.tsx');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const runId = 'comprun_synthetic_download';
const commit = 'a'.repeat(40);
const truth = 'b'.repeat(64);
const pdf = Buffer.from('%PDF-1.7\nSYNTHETIC unchanged retained bytes\n');
const digest = createHash('sha256').update(pdf).digest('hex');
const flush = async () => {for (let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));};
function response(language='en', overrides={}) {
  return new Response(pdf, {headers: {
    'content-type':'application/pdf', 'x-nico-run-id':runId,
    'x-nico-commit-sha':commit, 'x-nico-report-language':language,
    'x-nico-assessment-rerun':'false', 'x-nico-approval-status':'pending_human_approval',
    'x-nico-delivery-status':'blocked_pending_human_approval',
    'x-nico-client-delivery-allowed':'false', 'x-nico-pdf-sha256':digest,
    'x-nico-artifact-sha256':digest, 'x-nico-canonical-truth-sha256':truth,
    ...overrides,
  }});
}
function setup(fetchImpl, language='en') {
  const calls=[], anchors=[], timers=[], effects=[], listeners=new Map(), statuses=[];
  let cleanUp;
  class Element {
    constructor(tag='span') {this.tagName=tag;this.attrs={};this.style={};this.isConnected=true;this.textContent='';}
    getAttribute(key) {return this.attrs[key]??null;}
    setAttribute(key,value) {this.attrs[key]=String(value);}
    removeAttribute(key) {delete this.attrs[key];}
    appendChild(node) {statuses.push(node);}
    querySelector() {return statuses[statuses.length-1]||null;}
    closest(selector) {return selector==='button'?button:actions;}
    remove() {this.isConnected=false;}
    click() {anchors.push({href:this.href,target:this.target,filename:this.download});}
  }
  class HTMLButtonElement extends Element {constructor(){super('button');this.disabled=false;}}
  const actions=new Element('div');
  actions.attrs={'data-run-id':runId,'data-commit-sha':commit,'data-canonical-truth-sha256':truth,'data-assessment-report-ready':'true'};
  const button=new HTMLButtonElement();
  button.attrs={'data-assessment-pdf-kind':'localized-draft-pending-approval','data-report-language':language};
  button.textContent=language==='es-MX'?'Descargar PDF para revisión':'Download review PDF';
  const blobs=new Map();
  class FixtureURL extends URL {
    static createObjectURL(blob) {const id='blob:synthetic-'+blobs.size;blobs.set(id,blob);return id;}
    static revokeObjectURL(id) {blobs.delete(id);}
  }
  const document={
    documentElement:{lang:language==='es-MX'?'es':'en'},
    body:{appendChild(){}},createElement:tag=>new Element(tag),querySelectorAll:()=>[],
    addEventListener:(type,fn)=>listeners.set(type,fn),
    removeEventListener:(type,fn)=>{if(listeners.get(type)===fn)listeners.delete(type);},
  };
  const window={location:new URL(language==='es-MX'?'https://unit.invalid/es/assessment':'https://unit.invalid/assessment'),
    setTimeout(fn,ms){const id=timers.length+1;timers.push({id,fn,ms,cleared:false});return id;},
    clearTimeout(id){const timer=timers.find(t=>t.id===id);if(timer)timer.cleared=true;}};
  const module={exports:{}};
  vm.runInNewContext(compiled,{module,exports:module.exports,document,window,
    URL:FixtureURL,Blob,Headers,Response,AbortSignal,AbortController,DOMException,Error,
    Uint8Array,crypto:webcrypto,Element,HTMLButtonElement,
    fetch:async(url,init)=>{calls.push({url,init});return fetchImpl(url,init);},
    require(name){
      if(name==='react')return{useEffect:fn=>effects.push(fn),useRef:value=>({current:value})};
      if(name==='./assessment/assessmentLocale')return{reportLanguageForRequest:value=>value};
      throw Error('Unexpected import '+name);
    },
  },{filename});
  module.exports.default();
  for(const effect of effects)cleanUp=effect();
  const click=()=>{
    let intercepted=false;
    listeners.get('click')({target:button,preventDefault(){intercepted=true;},stopPropagation(){},stopImmediatePropagation(){}});
    return intercepted;
  };
  return{api:module.exports,calls,anchors,timers,button,actions,statuses,blobs,click,cleanUp};
}
test('slow retained PDF stays tracked and repeat clicks cannot launch another request',async()=>{
  let release;
  const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  assert.equal(s.click(),true);
  assert.equal(s.calls.length,1);
  assert.equal(s.button.disabled,true);
  for(const timer of s.timers.filter(t=>t.ms<=8000&&!t.cleared))timer.fn();
  assert.match(s.statuses[0].textContent,/Downloading and verifying/);
  s.button.disabled=false; // Simulate a React replacement/rerender during the operation.
  s.click();
  assert.equal(s.calls.length,1);
  assert.equal(s.anchors.length,0);
  release(response());
  await flush();
  assert.equal(s.anchors.length,1);
  assert.match(s.anchors[0].href,/^blob:/);
  assert.notEqual(s.anchors[0].target,'_blank');
  assert.deepEqual(Buffer.from(await s.blobs.get(s.anchors[0].href).arrayBuffer()),pdf);
  assert.match(s.statuses.at(-1).textContent,/verified and sent/);
  assert.equal(s.button.disabled,false);
  assert.equal(s.calls[0].init.credentials,'same-origin');
  assert.equal(s.calls[0].init.cache,'no-store');
});
test('the guard includes a slow response body, not only response headers',async()=>{
  let release;
  const r=response();
  r.arrayBuffer=()=>new Promise(resolve=>{release=resolve;});
  const s=setup(async()=>r);
  s.click();await flush();
  s.button.disabled=false;s.click();
  assert.equal(s.calls.length,1);
  assert.equal(s.anchors.length,0);
  release(pdf.buffer.slice(pdf.byteOffset,pdf.byteOffset+pdf.byteLength));
  await flush();
  assert.equal(s.anchors.length,1);
});
for(const language of ['en','es-MX']) {
  test(language+' draft download preserves bytes, identity and language',async()=>{
    const s=setup(async()=>response(language),language);
    s.click();await flush();
    assert.equal(s.anchors.length,1);
    assert.ok(s.anchors[0].filename.includes('-'+language+'-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf'));
    assert.ok(s.calls[0].url.endsWith('/localized-report/'+language+'/pdf'));
    if(language==='es-MX')assert.match(s.statuses.at(-1).textContent,/PDF verificado/);
  });
  test(language+' timeout is persistent, actionable and permits an explicit retry',async()=>{
    let attempt=0;
    const s=setup(async()=>++attempt===1?Response.json({detail:{code:'assessment_artifact_timeout'}},{status:504}):response(language),language);
    s.click();await flush();
    assert.equal(s.anchors.length,0);
    assert.equal(s.button.disabled,false);
    assert.equal(s.statuses.at(-1).attrs.role,'alert');
    assert.match(s.statuses.at(-1).textContent,language==='en'?/Retry this download/:/Vuelve a intentarlo/);
    assert.equal(s.calls.length,1);
    s.click();await flush();
    assert.equal(s.calls.length,2);
    assert.equal(s.anchors.length,1);
  });
}
for(const status of [401,403])test('HTTP '+status+' requires authentication without presenting a PDF',async()=>{
  const s=setup(async()=>new Response('{}',{status}));
  s.click();await flush();
  assert.equal(s.anchors.length,0);
  assert.match(s.statuses.at(-1).textContent,/Sign in to NICO/);
  assert.equal(s.calls.length,1);
});
for(const [description,headers]of[
  ['wrong run',{'x-nico-run-id':'comprun_other'}],
  ['wrong source',{'x-nico-commit-sha':'c'.repeat(40)}],
  ['wrong language',{'x-nico-report-language':'es-MX'}],
  ['stale canonical truth',{'x-nico-canonical-truth-sha256':'c'.repeat(64)}],
  ['tampered retained bytes',{'x-nico-pdf-sha256':'0'.repeat(64),'x-nico-artifact-sha256':'0'.repeat(64)}],
  ['unbound artifact hash',{'x-nico-artifact-sha256':'c'.repeat(64)}],
  ['approved edition',{'x-nico-approval-status':'approved_final','x-nico-accepted-pdf-sha256':digest}],
  ['delivery authorization',{'x-nico-client-delivery-allowed':'true'}],
  ['assessment replay',{'x-nico-assessment-rerun':'true'}],
])test(description+' fails closed',async()=>{
  const s=setup(async()=>response('en',headers));
  s.click();await flush();
  assert.equal(s.anchors.length,0);
  assert.equal(s.statuses.at(-1).attrs.role,'alert');
  assert.equal(s.button.disabled,false);
});
test('interrupted body clears the operation and leaves safe retry available',async()=>{
  let attempt=0;
  const s=setup(async()=>{
    const r=response();
    if(++attempt===1)r.arrayBuffer=async()=>{throw Error('Synthetic interrupted download');};
    return r;
  });
  s.click();await flush();assert.equal(s.anchors.length,0);
  assert.equal(s.button.disabled,false);
  s.click();await flush();assert.equal(s.anchors.length,1);
});
test('overlapping identical helper requests share one operation only while it is active',async()=>{
  let release;
  const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  const binding={commitSha:commit,canonicalTruthSha256:truth};
  const a=s.api.startExactRunDownload(runId,'en',binding);
  const b=s.api.startExactRunDownload(runId,'en',binding);
  assert.equal(a,b);assert.equal(s.calls.length,1);
  release(response());await a;
  assert.equal(s.anchors.length,1);
  const c=s.api.startExactRunDownload(runId,'en',binding);
  assert.equal(s.calls.length,2);
  release(response());await c;
  assert.equal(s.anchors.length,2);
});
test('English and es-MX operations do not substitute one artifact for the other',async()=>{
  const s=setup(async url=>response(url.includes('/es-MX/')?'es-MX':'en'));
  const binding={commitSha:commit,canonicalTruthSha256:truth};
  await Promise.all([s.api.startExactRunDownload(runId,'en',binding),s.api.startExactRunDownload(runId,'es-MX',binding)]);
  assert.equal(s.calls.length,2);assert.equal(s.anchors.length,2);
});
test('unmount aborts an interrupted request without downloading partial bytes',async()=>{
  const s=setup((url,init)=>new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true})));
  s.click();s.cleanUp();await flush();
  assert.equal(s.calls[0].init.signal.aborted,true);
  assert.equal(s.anchors.length,0);
});
for(const boundary of ['accepted','not-ready','missing-source'])test(boundary+' action stays with its existing workspace owner',()=>{
  const s=setup(async()=>response());
  if(boundary==='accepted')s.button.attrs['data-assessment-pdf-kind']='exact-approved-accepted-edition';
  if(boundary==='not-ready')s.actions.attrs['data-assessment-report-ready']='false';
  if(boundary==='missing-source')delete s.actions.attrs['data-commit-sha'];
  assert.equal(s.click(),false);
  assert.equal(s.calls.length,0);
});
