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
    'x-nico-review-pdf-artifact-mode':'pending-source-frozen',
    'x-nico-frozen-source-artifact':'true',
    'x-nico-localized-artifact-requires-new-approval':'false',
    'x-nico-localized-artifact-approval-invalidated':'false',
    ...overrides,
  }});
}
function setup(fetchImpl, language='en', digestImpl, options={}) {
  const calls=[], anchors=[], timers=[], effects=[], listeners=new Map(), statuses=[];
  let cleanUp, operationState;
  class Element {
    constructor(tag='span') {this.tagName=tag;this.attrs={};this.style={};this.isConnected=true;this.textContent='';}
    getAttribute(key) {return this.attrs[key]??null;}
    setAttribute(key,value) {this.attrs[key]=String(value);}
    removeAttribute(key) {delete this.attrs[key];}
    appendChild(node) {statuses.push(node);}
    querySelector() {return statuses.filter(node=>node.isConnected).at(-1)||null;}
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
    body:{appendChild(){}},createElement:tag=>new Element(tag),querySelectorAll:()=>options.recover?[button]:[],
    addEventListener:(type,fn)=>listeners.set(type,fn),
    removeEventListener:(type,fn)=>{if(listeners.get(type)===fn)listeners.delete(type);},
  };
  const storage=options.storage||new Map();
  const window={sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},location:new URL(language==='es-MX'?'https://unit.invalid/es/assessment':'https://unit.invalid/assessment'),
    setTimeout(fn,ms){const id=timers.length+1;timers.push({id,fn,ms,cleared:false});return id;},
    clearTimeout(id){const timer=timers.find(t=>t.id===id);if(timer)timer.cleared=true;}};
  const module={exports:{}};
  vm.runInNewContext(compiled,{module,exports:module.exports,document,window,
    URL:FixtureURL,URLSearchParams,Blob,Headers,Response,AbortController,DOMException,Error,
    Date: options.clock ? class extends Date {static now(){return options.clock.now;}} : Date,
    AbortSignal: options.clock ? {any:AbortSignal.any.bind(AbortSignal), timeout(ms){
      options.clock.timeouts.push(ms);return new AbortController().signal;}} : AbortSignal,
    process:{env:{NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION:options.async?"true":"false"}},
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
  return{api:module.exports,calls,anchors,timers,button,actions,statuses,blobs,click,cleanUp,settled,storage};
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
  assert.equal(s.calls[0].url,`/api/nico/assessment/comprehensive-run/${runId}/localized-report/en/pdf`);
  assert.equal(s.calls[0].init.method,'GET');
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

test('stale completion clears its old progress from a reused assessment container',async()=>{
  let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));
  s.click();s.actions.attrs['data-run-id']='comprun_current_after_reload';
  release(response());await s.settled();
  assert.equal(s.anchors.length,0);assert.equal(s.actions.querySelector(),null);
});
test('old stale completion cannot remove progress owned by a new control and truth',async()=>{
  const releases=[];const s=setup(()=>new Promise(resolve=>releases.push(resolve)));
  s.click();s.button.isConnected=false;s.actions.attrs['data-canonical-truth-sha256']='c'.repeat(64);
  const replacement=new s.button.constructor();replacement.attrs={...s.button.attrs,'data-assessment-action-disabled':'false'};
  replacement.textContent=s.button.textContent;
  const current=s.api.downloadPendingReviewPdf(replacement);
  releases[0](response());await flush();
  assert.ok(s.actions.querySelector()?.isConnected);assert.match(s.actions.querySelector().textContent,/Downloading and verifying/);
  releases[1](response('en',{'x-nico-canonical-truth-sha256':'c'.repeat(64)}));await current;await s.settled();
  assert.equal(s.anchors.length,1);assert.match(s.actions.querySelector().textContent,/verified and sent/);
});


const preparationJob='reviewpdfprep_'+'e'.repeat(64);
function preparation(state, language='en', changes={}) {
  return new Response(JSON.stringify({job_id:preparationJob,state,run_id:runId,report_language:language,
    commit_sha:commit,canonical_truth_sha256:truth,human_review_required:true,client_delivery_allowed:false,artifact_mode:'pending-source-frozen',...changes}),
    {headers:{'content-type':'application/json'}});
}
async function poll(s) {
  await flush();
  const timer=s.timers.filter(t=>t.ms===2500&&!t.cleared).at(-1);
  assert.ok(timer,'pending preparation poll');timer.cleared=true;timer.fn();await flush();
}
for(const language of ['en','es-MX'])test(`${language} async preparation is explicit, deduplicated and downloads only verified ready bytes`,async()=>{
  let step=0;
  const s=setup(async(url,init)=>{
    if(url.includes('/pdf?'))return response(language);
    return preparation(['queued','preparing','ready'][step++],language);
  },language,undefined,{async:true});
  assert.equal(s.calls.length,0);
  s.click();await flush();
  assert.equal(s.calls[0].init.method,'POST');
  assert.equal(JSON.parse(s.calls[0].init.body).prepare,true);
  s.button.disabled=false;s.click();await flush();assert.equal(s.calls.length,1);
  assert.match(s.statuses[0].textContent,language==='en'?/queued/:/cola/);
  assert.equal(s.timers.some(t=>t.ms===255000),false,'download clock starts after preparation');
  await poll(s);assert.match(s.statuses[0].textContent,language==='en'?/Preparing/:/Preparando/);
  await poll(s);await s.settled();
  assert.equal(s.calls.filter(c=>c.init.method==='POST').length,1);
  const download=s.calls.find(c=>c.url.includes('/pdf?'));
  const target=new URL(download.url,'https://synthetic.invalid');
  assert.ok(download.url.startsWith('/api/nico/assessment/'));
  assert.equal(target.pathname,`/api/nico/assessment/comprehensive-run/${runId}/review-pdf/${language}/pdf`);
  assert.deepEqual(Object.fromEntries(target.searchParams),{
    job_id:preparationJob,commit_sha:commit,canonical_truth_sha256:truth,
  });
  assert.equal(download.init.method,'GET');
  assert.equal(download.init.credentials,'same-origin');
  assert.equal(download.init.cache,'no-store');
  assert.equal(s.anchors.length,1);
  assert.ok(s.timers.some(t=>t.ms===255000));
  assert.equal(s.storage.size,0);
});
test('reload resumes saved preparation with GET and never starts another render',async()=>{
  const storage=new Map();
  const first=setup(async()=>preparation('preparing'),'en',undefined,{async:true,storage});
  first.click();await flush();assert.equal(storage.size,1);
  first.cleanUp();await flush();
  const restored=setup(async(url)=>url.includes('/pdf?')?response():preparation('ready'),
    'en',undefined,{async:true,storage,recover:true});
  await restored.settled();
  assert.ok(restored.calls.length>=2);
  assert.equal(restored.calls.every(c=>c.init.method==='GET'),true);
  assert.equal(restored.anchors.length,1);
});
for(const language of ['en','es-MX'])test(`${language} failed preparation has no PDF or approval`,async()=>{
  const s=setup(async()=>preparation('failed',language),language,undefined,{async:true});
  s.click();await s.settled();
  assert.equal(s.anchors.length,0);assert.equal(s.calls.length,1);
  assert.match(s.statuses[0].textContent,language==='en'?/failed or was cancelled/:/falló o se canceló/);
});
for(const change of ['locale','source','checksum','approval'])test(`async ${change} mismatch fails closed`,async()=>{
  const s=setup(async(url)=>{
    if(url.includes('/pdf?'))return change==='checksum'?response('en',{'x-nico-pdf-sha256':'0'.repeat(64)}):response();
    return preparation('ready','en',change==='locale'?{report_language:'es-MX'}:
      change==='source'?{canonical_truth_sha256:'0'.repeat(64)}:
      change==='approval'?{client_delivery_allowed:true}:{});
  },'en',undefined,{async:true});
  s.click();await s.settled();assert.equal(s.anchors.length,0);
});
test('navigation cancels observation while retaining resumable server preparation',async()=>{
  const s=setup(async()=>preparation('preparing'),'en',undefined,{async:true});
  s.click();await flush();assert.equal(s.storage.size,1);s.cleanUp();await flush();
  assert.equal(s.calls.length,1);assert.equal(s.anchors.length,0);assert.equal(s.storage.size,1);
});
test('late preparation response cannot download into a changed assessment',async()=>{
  let finish;
  const s=setup(()=>new Promise(resolve=>{finish=resolve;}),'en',undefined,{async:true});
  s.click();s.actions.attrs['data-commit-sha']='c'.repeat(40);finish(preparation('ready'));
  await s.settled();assert.equal(s.anchors.length,0);assert.equal(s.calls.length,1);
});


test('preparation sleep stops at the absolute deadline without another request',async()=>{
  const clock={now:1000,timeouts:[]};
  const s=setup(async()=>{clock.now=900000;return preparation('preparing');},'en',undefined,{async:true,clock});
  s.click();await flush();
  const timer=s.timers.find(t=>t.ms===1000&&!t.cleared);assert.ok(timer);
  clock.now=901000;timer.fn();await s.settled();
  assert.equal(s.calls.length,1);assert.equal(s.anchors.length,0);
  assert.match(s.statuses.at(-1).textContent,/still pending/);assert.equal(s.storage.size,1);
});
test('final bounded poll consumes ready even when its response reaches the deadline',async()=>{
  const clock={now:1000,timeouts:[]};let reads=0;
  const s=setup(async(url)=>{
    if(url.includes('/pdf?'))return response();
    if(++reads===1){clock.now=897000;return preparation('verifying');}
    clock.now=901000;return preparation('ready');
  },'en',undefined,{async:true,clock});
  s.click();await flush();clock.now=899500;await poll(s);await s.settled();
  assert.deepEqual(clock.timeouts,[30000,1500]);assert.equal(s.anchors.length,1);
});
test('different retained preparation identities never share low-level download work',async()=>{
  const releases=[];const s=setup(()=>new Promise(resolve=>releases.push(resolve)));
  const first=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth,preparationJobId:preparationJob,artifactMode:'pending-source-frozen'});
  const next=s.api.startExactRunDownload(runId,'en',{commitSha:commit,canonicalTruthSha256:truth,preparationJobId:'reviewpdfprep_'+'f'.repeat(64),artifactMode:'pending-source-frozen'});
  assert.equal(s.calls.length,2);releases[0](response());releases[1](response());await first;await next;
});

test('unqualified alternate-language source cannot enqueue or fall back to synchronous rendering',async()=>{
  const s=setup(async()=>new Response('',{status:409}),'es-MX',undefined,{async:true});
  s.actions.attrs['data-assessment-locale-reapproval-required']='true';
  s.click();await s.settled();
  assert.equal(s.calls.length,1);assert.equal(s.calls[0].init.method,'GET');
  assert.match(s.calls[0].url,/review-pdf\/es-MX\?.*qualify=true/);
  assert.equal(s.anchors.length,0);assert.equal(s.storage.size,0);
});
test('lost admission response resumes by bound GET lookup without creating another job',async()=>{
  const storage=new Map();
  const first=setup(async()=>{throw new DOMException('synthetic timeout','TimeoutError');},'en',undefined,{async:true,storage});
  first.click();await first.settled();
  assert.match([...storage.values()][0],/^requested:v1:\d+$/);
  first.cleanUp();
  const recovered=setup(async(url)=>url.includes('/pdf?')?response():preparation('ready'),
    'en',undefined,{async:true,storage,recover:true});
  await recovered.settled();
  assert.equal(recovered.calls[0].init.method,'GET');
  assert.equal(new URL(recovered.calls[0].url,'https://unit.invalid').searchParams.has('job_id'),false);
  assert.equal(recovered.calls.every(call=>call.init.method==='GET'),true);
  assert.equal(recovered.anchors.length,1);
});

for(const status of [409,422,503])test(`preparation HTTP ${status} preserves only recoverable request markers`,async()=>{
  const storage=new Map();
  const first=setup(async()=>{throw new DOMException('synthetic timeout','TimeoutError');},'en',undefined,{async:true,storage});
  first.click();await first.settled();first.cleanUp();
  assert.match([...storage.values()][0],/^requested:v1:\d+$/);
  const restored=setup(async()=>new Response('{}',{status}), 'en',undefined,{async:true,storage,recover:true});
  await restored.settled();
  assert.equal(restored.calls.length,1);assert.equal(restored.calls[0].init.method,'GET');
  assert.equal(restored.anchors.length,0);
  assert.equal(storage.size,status===503?1:0);
  if(status!==503){
    restored.click();await restored.settled();
    assert.equal(restored.calls[1].init.method,'POST','definitive stale identity allows explicit retry');
  }
});

test('uncertain admission 503 then lookup 404 retains GET recovery until late commit is visible',async()=>{
  const storage=new Map();
  const first=setup(async()=>new Response('{}',{status:503}),'en',undefined,{async:true,storage});
  first.click();await first.settled();first.cleanUp();
  assert.match([...storage.values()][0],/^requested:v1:\d+$/);
  let reads=0;
  const restored=setup(async(url)=>url.includes('/pdf?')?response():
    ++reads===1?new Response('{}',{status:404}):preparation('ready'),
    'en',undefined,{async:true,storage,recover:true});
  await flush();
  assert.match([...storage.values()][0],/^requested:v1:\d+$/,'not-found before COMMIT is not authoritative absence');
  await poll(restored);await restored.settled();
  assert.equal(restored.calls.every(call=>call.init.method==='GET'),true);
  assert.equal(restored.anchors.length,1);assert.equal(storage.size,0);
});

test('uncertain admission recovery retains original deadline across reload and permits one explicit GET',async()=>{
  const storage=new Map(), clock={now:1000,timeouts:[]};
  const first=setup(async()=>new Response('{}',{status:503}),'en',undefined,{async:true,storage,clock});
  first.click();await first.settled();first.cleanUp();
  assert.equal([...storage.values()][0],'requested:v1:901000');
  clock.now=900000;
  const restored=setup(async()=>new Response('{}',{status:404}),'en',undefined,{async:true,storage,clock,recover:true});
  await flush();
  const timer=restored.timers.find(t=>t.ms===1000&&!t.cleared);assert.ok(timer);
  clock.now=901000;timer.fn();await restored.settled();restored.cleanUp();
  assert.equal(restored.calls.length,1);assert.equal([...storage.values()][0],'requested:v1:901000');
  const again=setup(async()=>new Response('{}',{status:404}),'en',undefined,{async:true,storage,clock,recover:true});
  await again.settled();assert.equal(again.calls.length,0,'reload cannot restart polling deadline');
  again.click();await again.settled();
  assert.equal(again.calls.length,1);assert.equal(again.calls[0].init.method,'GET');
  assert.equal([...storage.values()][0],'requested:v1:901000');
});

function derivativeResponse(changes={}) {
  return response('es-MX', {
    'x-nico-review-pdf-artifact-mode':'pending-source-localized-draft',
    'x-nico-frozen-source-artifact':'false',
    'x-nico-localized-artifact-requires-new-approval':'true',
    'x-nico-localized-artifact-approval-invalidated':'true',
    'x-nico-artifact-finality':'automated_draft', ...changes,
  });
}
function derivativePreparation(state, changes={}) {
  return preparation(state,'es-MX',{artifact_mode:'pending-source-localized-draft',...changes});
}
test('pending-source derivative qualifies before deduplicated admission and verifies draft bytes',async()=>{
  const s=setup(async url=>url.includes('qualify=true')?derivativePreparation('eligible'):
    url.includes('/pdf?')?derivativeResponse():derivativePreparation('ready'),'es-MX',undefined,{async:true});
  s.actions.attrs['data-assessment-locale-reapproval-required']='true';
  s.click();s.button.disabled=false;s.click();await s.settled();
  assert.deepEqual(s.calls.map(c=>c.init.method),['GET','POST','GET']);
  assert.match(s.calls[0].url,/qualify=true/);assert.equal(s.anchors.length,1);
  assert.equal(s.calls.some(c=>c.url.includes('/localized-report/')),false);
});
for(const change of ['mode','source','locale','job','reapproval','invalidation','finality','frozen','accepted','human','mode_header'])
test(`pending derivative ${change} mismatch cannot download`,async()=>{
  const s=setup(async url=>{
    if(url.includes('qualify=true'))return derivativePreparation('eligible');
    if(url.includes('/pdf?'))return derivativeResponse(change==='reapproval'?{'x-nico-localized-artifact-requires-new-approval':''}:
      change==='invalidation'?{'x-nico-localized-artifact-approval-invalidated':'false'}:
      change==='finality'?{'x-nico-artifact-finality':'approved'}:
      change==='frozen'?{'x-nico-frozen-source-artifact':'true'}:
      change==='accepted'?{'x-nico-accepted-edition-language':'en'}:
      change==='human'?{'x-nico-human-review-completed':'true'}:
      change==='mode_header'?{'x-nico-review-pdf-artifact-mode':''}:{});
    return derivativePreparation('ready',change==='mode'?{artifact_mode:'pending-source-frozen'}:
      change==='source'?{canonical_truth_sha256:'0'.repeat(64)}:
      change==='locale'?{report_language:'en'}:
      change==='job'?{job_id:'reviewpdfprep_'+'f'.repeat(64)}:{});
  },'es-MX',undefined,{async:true});
  s.actions.attrs['data-assessment-locale-reapproval-required']='true';
  s.click();await s.settled();assert.equal(s.anchors.length,0);
});
test('lost derivative admission response resumes with GET only and retains stricter approval checks',async()=>{
  const storage=new Map();
  const first=setup(async(url,init)=>{
    if(url.includes('qualify=true'))return derivativePreparation('eligible');
    throw new DOMException('synthetic timeout','TimeoutError');
  },'es-MX',undefined,{async:true,storage});
  first.actions.attrs['data-assessment-locale-reapproval-required']='true';
  first.click();await first.settled();first.cleanUp();
  assert.equal(first.calls.filter(c=>c.init.method==='POST').length,1);
  const next=setup(async url=>url.includes('/pdf?')?derivativeResponse():derivativePreparation('ready'),
    'es-MX',undefined,{async:true,storage});
  next.actions.attrs['data-assessment-locale-reapproval-required']='true';
  next.click();await next.settled();
  assert.equal(next.calls.every(c=>c.init.method==='GET'),true);assert.equal(next.anchors.length,1);
});

for (const language of ['en','es-MX']) {
  test(language+' qualified busy PDF gives manual retry guidance without claiming this run', async()=>{
    let attempts=0;
    const s=setup(async()=>++attempts===1
      ? Response.json({detail:{reason:'retained_pdf_preparing'}},{status:503,headers:{'Retry-After':'5'}})
      : response(language),language);
    s.click();await s.settled();
    assert.equal(s.statuses.at(-1).textContent,language==='en'
      ? 'NICO is still preparing a PDF. Retry this download in at least 5 seconds; do not start another assessment.'
      : 'NICO todavía está preparando un PDF. Reintenta esta descarga dentro de al menos 5 segundos; no inicies otra evaluación.');
    assert.equal(s.calls.length,1);assert.equal(s.anchors.length,0);assert.equal(s.button.disabled,false);
    for(const timer of s.timers.filter(t=>!t.cleared))timer.fn();
    await flush();assert.equal(s.calls.length,1,'no automatic retry');
    s.click();await s.settled();
    assert.equal(s.calls.length,2);assert.equal(s.anchors.length,1);
  });
  for (const [label,status,body,delay] of [
    ['other status',502,'{"detail":{"reason":"retained_pdf_preparing"}}','5'],
    ['missing reason',503,'{}','5'],
    ['wrong reason',503,'{"detail":{"reason":"other"}}','5'],
    ['malformed JSON',503,'{','5'],
    ['null JSON',503,'null','5'],
    ...[null,'0','-1','1.5','61','9999999999999999999','05','5 seconds','Thu, 01 Jan 2026 00:00:00 GMT'].map(delay=>
      ['invalid delay '+delay,503,'{"detail":{"reason":"retained_pdf_preparing"}}',delay]),
  ]) test(language+' busy download keeps generic error for '+label,async()=>{
    const headers={'x-request-id':'owned-request'};
    if(delay!==null)headers['Retry-After']=delay;
    const s=setup(async()=>new Response(body,{status,headers}),language);
    s.click();await s.settled();
    assert.equal(s.statuses.at(-1).textContent,(language==='en'
      ? 'The PDF could not be downloaded. Retry this download.'
      : 'No se pudo descargar el PDF. Vuelve a intentarlo.')+' (owned-request)');
    assert.equal(s.calls.length,1);assert.equal(s.anchors.length,0);
  });
}
