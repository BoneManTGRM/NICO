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
function setup(fetchImpl, language='en', digestImpl) {
  const calls=[], anchors=[], timers=[], effects=[], listeners=new Map(), statuses=[];
  let cleanUp, operationState;
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
    Uint8Array,crypto:digestImpl?{subtle:{digest:digestImpl}}:webcrypto,Element,HTMLButtonElement,
    fetch:async(url,init)=>{calls.push({url,init});return fetchImpl(url,init);},
    require(name){
      if(name==='react')return{useEffect:fn=>effects.push(fn),useRef:value=>{operationState=value;return{current:value};}};
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
  const settled=async()=>{
    const deadline=Date.now()+5000;
    while(operationState.size && Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,5));
    assert.equal(operationState.size,0,'Download operation did not settle within the regression deadline');
  };
  return{api:module.exports,calls,anchors,timers,button,actions,statuses,blobs,click,cleanUp,settled};
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
  await s.settled();
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
  await s.settled();
  assert.equal(s.anchors.length,1);
});
for(const language of ['en','es-MX']) {
  test(language+' draft download preserves bytes, identity and language',async()=>{
    const s=setup(async()=>response(language),language);
    s.click();await s.settled();
    assert.equal(s.anchors.length,1);
    assert.ok(s.anchors[0].filename.includes('-'+language+'-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf'));
    assert.ok(s.calls[0].url.endsWith('/localized-report/'+language+'/pdf'));
    if(language==='es-MX')assert.match(s.statuses.at(-1).textContent,/PDF verificado/);
  });
  test(language+' timeout is persistent, actionable and permits an explicit retry',async()=>{
    let attempt=0;
    const s=setup(async()=>++attempt===1?Response.json({detail:{code:'assessment_artifact_timeout'}},{status:504}):response(language),language);
    s.click();await s.settled();
    assert.equal(s.anchors.length,0);
    assert.equal(s.button.disabled,false);
    assert.equal(s.statuses.at(-1).attrs.role,'alert');
    assert.match(s.statuses.at(-1).textContent,language==='en'?/Retry this download/:/Vuelve a intentarlo/);
    assert.equal(s.calls.length,1);
    s.click();await s.settled();
    assert.equal(s.calls.length,2);
    assert.equal(s.anchors.length,1);
  });
}
for(const status of [401,403])test('HTTP '+status+' requires authentication without presenting a PDF',async()=>{
  const s=setup(async()=>new Response('{}',{status}));
  s.click();await s.settled();
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
  s.click();await s.settled();
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
  s.click();await s.settled();assert.equal(s.anchors.length,0);
  assert.match(s.statuses.at(-1).textContent,/The download was interrupted\. Retry this download\./);
  assert.equal(s.button.disabled,false);
  s.click();await s.settled();assert.equal(s.anchors.length,1);
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

test('Spanish UI progress keeps an independently selected English report language',async()=>{
  const s=setup(async()=>response('en'),'es-MX');
  s.button.attrs['data-report-language']='en';
  s.click();await s.settled();
  assert.equal(s.calls.length,1);
  assert.ok(s.calls[0].url.endsWith('/localized-report/en/pdf'));
  assert.match(s.statuses.at(-1).textContent,/PDF verificado/);
  assert.ok(s.anchors[0].filename.includes('-en-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf'));
});

for(const language of ['en','es-MX'])test(language+' network interruption gives safe retry guidance',async()=>{
  let attempt=0;
  const s=setup(async()=>{
    if(++attempt===1)throw new TypeError('Failed to fetch');
    return response(language);
  },language);
  s.click();await s.settled();
  assert.equal(s.anchors.length,0);
  assert.equal(s.statuses.at(-1).attrs.role,'alert');
  assert.match(s.statuses.at(-1).textContent,language==='en'?/Retry this download/:/Vuelve a intentarlo/);
  assert.equal(s.button.disabled,false);
  s.click();await s.settled();
  assert.equal(s.calls.length,2);
  assert.equal(s.anchors.length,1);
});
test('the response deadline aborts the request and leaves explicit retry available',async()=>{
  const s=setup((url,init)=>new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true})));
  s.click();
  s.timers.find(t=>t.ms===255000).fn();
  await s.settled();
  assert.equal(s.calls.length,1);
  assert.equal(s.calls[0].init.signal.aborted,true);
  assert.equal(s.anchors.length,0);
  assert.equal(s.button.disabled,false);
  assert.match(s.statuses.at(-1).textContent,/timed out\. Retry this download/);
});


for (const changed of ['run', 'commit', 'truth', 'language', 'detached-button', 'detached-actions', 'not-ready', 'accepted']) {
  test('stale ' + changed + ' selection cannot receive an old completed download', async () => {
    let release;
    const s = setup(() => new Promise(resolve => { release = resolve; }));
    assert.equal(s.click(), true);
    if (changed === 'run') s.actions.attrs['data-run-id'] = 'comprun_other_selection';
    if (changed === 'commit') s.actions.attrs['data-commit-sha'] = 'c'.repeat(40);
    if (changed === 'truth') s.actions.attrs['data-canonical-truth-sha256'] = 'c'.repeat(64);
    if (changed === 'language') s.button.attrs['data-report-language'] = 'es-MX';
    if (changed === 'detached-button') s.button.isConnected = false;
    if (changed === 'detached-actions') s.actions.isConnected = false;
    if (changed === 'not-ready') s.actions.attrs['data-assessment-report-ready'] = 'false';
    if (changed === 'accepted') s.button.attrs['data-assessment-pdf-kind'] = 'accepted-edition';
    release(response());
    await s.settled();
    assert.equal(s.calls.length, 1);
    assert.equal(s.anchors.length, 0, 'A stale completion must not hand off bytes to the current selection');
    assert.doesNotMatch(s.statuses.at(-1)?.textContent || '', /verified and sent/);
  });
}

test('a retained PDF with the wrong response MIME fails closed', async () => {
  const s = setup(async () => response('en', {'content-type': 'text/html'}));
  s.click();
  await s.settled();
  assert.equal(s.calls.length, 1);
  assert.equal(s.anchors.length, 0);
  assert.match(s.statuses.at(-1)?.textContent || '', /does not match/);
});

for(const desired of ['true','false'])test('stale reused accepted control preserves current React disabled='+desired,async()=>{
  let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  s.click();s.button.attrs['data-assessment-pdf-kind']='accepted-edition';
  s.button.attrs['data-assessment-action-disabled']=desired;
  release(response());await s.settled();
  assert.equal(s.anchors.length,0);assert.equal(s.button.disabled,desired==='true');
  assert.equal(s.button.getAttribute('aria-busy'),null);
});
test('old completion cannot clear a newer download owner on the same button',async()=>{
  const releases=[];const s=setup(()=>new Promise(resolve=>releases.push(resolve)));
  s.click();s.actions.attrs['data-canonical-truth-sha256']='c'.repeat(64);s.button.disabled=false;
  s.button.attrs['data-assessment-action-disabled']='false';
  s.click();assert.equal(s.calls.length,2);
  releases[0](response());await flush();
  assert.equal(s.anchors.length,0);assert.equal(s.button.disabled,true);
  assert.equal(s.button.getAttribute('aria-busy'),'true');
  releases[1](response('en',{'x-nico-canonical-truth-sha256':'c'.repeat(64)}));await s.settled();
  assert.equal(s.anchors.length,1);assert.equal(s.button.disabled,false);
});
test('a context changed during hashing cannot receive verified old bytes',async()=>{
  let release;const s=setup(async()=>response(),'en',()=>new Promise(resolve=>{release=resolve;}));
  s.click();while(!release)await flush();
  s.actions.attrs['data-run-id']='comprun_changed_during_digest';
  release(Buffer.from(digest,'hex'));await s.settled();
  assert.equal(s.anchors.length,0);assert.doesNotMatch(s.statuses.at(-1).textContent,/verified and sent/);
});
test('application/pdf MIME parameters are valid without relaxing media-type rejection',async()=>{
  const s=setup(async()=>response('en',{'content-type':'Application/PDF; charset=binary'}));
  s.click();await s.settled();assert.equal(s.anchors.length,1);
});
test('missing canonical truth declines capture so the Workspace can reject before GET',()=>{
  const s=setup(async()=>response());delete s.actions.attrs['data-canonical-truth-sha256'];
  assert.equal(s.click(),false);assert.equal(s.calls.length,0);
});
test('unavailable PDF remains disabled after a stale pending completion',async()=>{
  let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  s.click();s.actions.attrs['data-assessment-pdf-available']='false';
  s.button.attrs['data-assessment-action-disabled']='true';
  release(response());await s.settled();assert.equal(s.anchors.length,0);assert.equal(s.button.disabled,true);
});

test('overlap replacement button for the same artifact cannot inherit a stale owner',async()=>{
  const releases=[];const s=setup((url,init)=>new Promise(resolve=>releases.push({resolve,init})));
  s.click();s.button.isConnected=false;
  const replacement=new s.button.constructor();
  replacement.attrs={...s.button.attrs,'data-assessment-action-disabled':'false'};
  replacement.textContent=s.button.textContent;
  const operation=s.api.downloadPendingReviewPdf(replacement);
  assert.equal(s.calls.length,2,'A new explicit current owner must not silently join a stale owner');
  assert.equal(releases[0].init.signal.aborted,true);
  releases[0].resolve(response());await flush();assert.equal(s.anchors.length,0);
  releases[1].resolve(response());await operation;await s.settled();
  assert.equal(s.anchors.length,1);assert.match(s.statuses.at(-1).textContent,/verified and sent/);
});
test('overlap stricter locale reapproval never inherits a weaker pending promise',async()=>{
  const releases=[];const s=setup((url,init)=>new Promise(resolve=>releases.push({resolve,init})));
  s.click();s.actions.attrs['data-assessment-locale-reapproval-required']='true';
  s.button.disabled=false;s.click();
  assert.equal(s.calls.length,2);
  releases[0].resolve(response());await flush();assert.equal(s.anchors.length,0);
  releases[1].resolve(response());await s.settled();
  assert.equal(s.anchors.length,0);assert.equal(s.statuses.at(-1).attrs.role,'alert');
  assert.match(s.statuses.at(-1).textContent,/does not match/);
});
test('overlap low-level stricter caller validates its own reapproval requirement',async()=>{
  const releases=[];const s=setup(()=>new Promise(resolve=>releases.push(resolve)));
  const weak=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth});
  const strict=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth,requiresNewApproval:true});
  const rejected=assert.rejects(strict,/does not match/);
  assert.equal(s.calls.length,2);releases[0](response());releases[1](response());
  await weak;await rejected;assert.equal(s.anchors.length,1);
});
test('overlap low-level stale caller is rejected before sharing active work',async()=>{
  let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  const first=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth});
  const stale=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth,isCurrent:()=>false});
  const rejected=assert.rejects(stale,/does not match/);
  release(response());await first;await rejected;assert.equal(s.calls.length,1);
});

for(const rejected of ['stale-header-context','wrong-MIME'])test('rejected '+rejected+' disposes only its owned retained fetch',async()=>{
  let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  s.click();if(rejected==='stale-header-context')s.actions.attrs['data-run-id']='comprun_other';
  release(response('en',rejected==='wrong-MIME'?{'content-type':'text/html'}:{}));await s.settled();
  assert.equal(s.anchors.length,0);assert.equal(s.calls[0].init.signal.aborted,true);
});
