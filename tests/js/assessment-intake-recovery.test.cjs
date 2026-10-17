'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {webcrypto} = require('node:crypto');
const {test} = require('node:test');
const ROOT = process.env.NICO_SOURCE_ROOT || path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(process.env.NICO_TEST_WEB_ROOT || path.join(ROOT, 'apps/web'), 'package.json'));
const ts = fromWeb('typescript');
const KEY = 'nico.comprehensive.active-run.v1';
const settle = async () => {for (let i=0;i<12;i++) await new Promise(resolve=>setImmediate(resolve));};
const missing = () => Response.json({detail:{code:'comprehensive_run_not_found'}},{status:404});
const denied = code => Response.json({detail:{code,request_id:'request-denied'}},{status:401});
const accepted = id => ({run_id:id, repository:'owner/repo', commit_sha:'a'.repeat(40), status:'review_required', terminal:true,
  human_review_required:true, client_delivery_allowed:false, progress_percent:100});
function harness(respond, locale='en') {
  let state=[], cursor=0, cache=new Map(), effects=[], mounted=false, timer=0;
  const storage=new Map(), calls=[], listeners=new Map();
  const on=(type,fn)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);};
  const window={location:new URL('https://nico.test/assessment?tier=comprehensive'),
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    history:{state:null,replaceState(_s,_t,url){window.location=new URL(url,window.location);}},
    setTimeout(fn,ms){if(ms<=5000)queueMicrotask(fn);return ++timer;},clearTimeout(){},setInterval(){return 1;},clearInterval(){},
    addEventListener:on,removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),requestAnimationFrame:fn=>fn(),scrollTo(){}};
  const document={documentElement:{lang:locale},visibilityState:'visible',addEventListener:on,removeEventListener:window.removeEventListener};
  function load(filename) {
    if(cache.has(filename))return cache.get(filename);
    const module={exports:{}};cache.set(filename,module.exports);
    const js=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
    vm.runInNewContext(js,{module,exports:module.exports,window,document,URL,URLSearchParams,Headers,Response,AbortController,crypto:webcrypto,
      setTimeout:window.setTimeout,clearTimeout(){},process:{env:{}},console,
      fetch:async(url,init)=>{const call={url,method:init.method,body:init.body?JSON.parse(init.body):null};calls.push(call);
        if(url.endsWith('/diagnostics/comprehensive-runtime'))return respond.readiness ? respond.readiness() : Response.json({status:'ready',survives_container_replacement_verified:true});
        return respond(call,{window,storage,calls});},
      require(name){if(name==='react')return {
        useState(initial){const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v;}];},
        useRef(initial){const i=cursor++;if(!(i in state))state[i]={current:initial};return state[i];},
        useEffect(fn){if(!mounted)effects.push(fn);}};
        if(!name.startsWith('.'))return fromWeb(name);return load(path.resolve(path.dirname(filename),name+'.ts'));}}, {filename});
    cache.set(filename,module.exports);return module.exports;
  }
  let hook=load(path.join(ROOT,'apps/web/app/assessment/useAssessmentRun.ts')).useAssessmentRun;
  function render(){cursor=0;const result=hook(locale);if(!mounted){mounted=true;for(const effect of effects)effect();}return result;}
  render();
  const configure=()=>{const c=render();c.setRepository('owner/repo');c.setClient('Client');c.setProject('Project');c.setAuthorized(true);return render();};
  return{render,configure,calls,storage,window,dispatch(type){for(const fn of listeners.get(type)||[])fn();},
    reload(){listeners.clear();state=[];cache=new Map();effects=[];mounted=false;hook=load(path.join(ROOT,'apps/web/app/assessment/useAssessmentRun.ts')).useAssessmentRun;return render();}};
}
for(const locale of ['en','es-MX']) for(const code of ['specialist_authentication_required','specialist_session_invalid_or_expired']) {
  test(`proven ${code} clears only pending intake and preserves form (${locale})`,async()=>{
    const h=harness(c=>c.method==='POST'?denied(code):missing(),locale);await h.configure().run();const c=h.render();
    assert.equal(c.protectedRunId,'');assert.equal(h.storage.has(KEY),false);assert.equal(h.window.location.searchParams.get('run_id'),null);
    assert.equal(c.issue.runCreated,false);assert.equal(c.issue.code,code);assert.equal(c.issue.requestId,'request-denied');
    assert.equal(c.repository,'owner/repo');assert.equal(c.client,'Client');assert.equal(c.authorized,true);
    assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
    h.reload();await settle();assert.equal(h.render().phase,'idle');
  });
}
test('repeated clicks and pageshow during intake dispatch exactly one POST',async()=>{
  let resolvePost,id;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;return new Promise(r=>{resolvePost=r;});}return Response.json(accepted(id));});
  const c=h.configure();const first=c.run();const second=c.run();await settle();h.dispatch('pageshow');h.dispatch('online');await settle();
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(JSON.parse(h.storage.get(KEY)).intakeState,'pending');
  resolvePost(Response.json(accepted(id)));await Promise.all([first,second]);assert.equal(h.render().result.run_id,id);assert.equal(h.render().phase,'review_required');
});
test('ambiguous POST and GET404 remain pending across refresh and explicit retry without duplicate POST',async()=>{
  const h=harness(c=>{if(c.method==='POST')throw Error('response lost');return missing();});await h.configure().run();
  const id=h.window.location.searchParams.get('run_id');assert.ok(id);assert.equal(h.render().issue.runCreated,false);
  assert.equal(JSON.parse(h.storage.get(KEY)).intakeState,'pending');h.reload();await settle();
  assert.equal(h.render().issue.runCreated,false);assert.equal(h.render().protectedRunId,id);
  await h.render().retry();await h.render().run();assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
  assert.equal(h.window.location.searchParams.get('run_id'),id);
});
test('lost POST response recovers actual accepted run through exact GET',async()=>{
  let id;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;throw Error('lost');}return Response.json(accepted(id));});
  await h.configure().run();assert.equal(h.render().phase,'review_required');assert.equal(h.render().result.run_id,id);
  const saved=JSON.parse(h.storage.get('nico.comprehensive.exact-run.v1.'+id));assert.equal(saved.intakeState,'accepted');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('accepted run survives expired-session status failure and refresh',async()=>{
  let id,expired=false;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;return Response.json(accepted(id));}return expired?denied('specialist_session_invalid_or_expired'):Response.json(accepted(id));});
  await h.configure().run();expired=true;h.reload();await settle();assert.equal(h.render().issue.runCreated,true);
  assert.equal(h.render().protectedRunId,id);assert.equal(h.window.location.searchParams.get('run_id'),id);
  await h.render().retry();assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('generic rejected POST is not proof of nonacceptance',async()=>{
  const h=harness(c=>c.method==='POST'?Response.json({detail:{code:'conflict'}},{status:409}):missing());
  await h.configure().run();assert.equal(h.render().issue.runCreated,false);assert.equal(JSON.parse(h.storage.get(KEY)).intakeState,'pending');
  await h.render().retry();assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('malformed successful intake cannot manufacture accepted identity',async()=>{
  const h=harness(c=>c.method==='POST'?Response.json({status:'ok'}):missing());await h.configure().run();
  assert.equal(h.render().result,null);assert.equal(JSON.parse(h.storage.get(KEY)).intakeState,'pending');assert.equal(h.render().issue.runCreated,false);
});
test('URL-only legacy run404 stays unconfirmed and never launches work on Back/Forward',async()=>{
  const h=harness(()=>missing());const id='comprun_legacy';h.window.location.searchParams.set('run_id',id);h.reload();await settle();
  assert.equal(h.render().issue.runCreated,false);h.dispatch('pageshow');await settle();await h.render().retry();
  assert.equal(h.calls.filter(c=>c.method==='POST').length,0);assert.equal(h.window.location.searchParams.get('run_id'),id);
});
test('rejected intake preserves another tab active run pointer',async()=>{
  const other='comprun_other_tab';const h=harness((c,{storage})=>{if(c.method==='POST'){
    storage.set(KEY,JSON.stringify({version:1,runId:other,intakeState:'accepted'}));return denied('specialist_session_invalid_or_expired');}return missing();});
  await h.configure().run();assert.equal(JSON.parse(h.storage.get(KEY)).runId,other);assert.equal(h.render().protectedRunId,'');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
for(const acceptedResponse of [true,false]) test(`Back/Forward while intake in flight cannot overwrite selected URL (accepted=${acceptedResponse})`,async()=>{
  let complete,id;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;return new Promise(r=>{complete=r;});}return missing();});
  const pending=h.configure().run();await settle();const original=h.window.location.href;
  h.window.location=new URL('https://nico.test/assessment?run_id=comprun_existing');h.dispatch('popstate');
  complete(acceptedResponse?Response.json(accepted(id)):denied('specialist_session_invalid_or_expired'));await pending;
  assert.equal(h.window.location.searchParams.get('run_id'),'comprun_existing');
  assert.equal(JSON.parse(h.storage.get('nico.comprehensive.exact-run.v1.'+id)).runId,id);
  h.window.location=new URL(original);h.dispatch('popstate');await settle();
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.window.location.searchParams.get('run_id'),id);
});
test('actual matching run recovered despite POST rejection takes precedence over cleanup',async()=>{
  let id;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;return denied('specialist_authentication_required');}return Response.json(accepted(id));});
  await h.configure().run();assert.equal(h.render().result.run_id,id);assert.equal(h.render().phase,'review_required');assert.equal(h.window.location.searchParams.get('run_id'),id);
});
test('no authorization means no readiness request or POST',async()=>{
  const h=harness(()=>{throw Error('unexpected network');});h.render().setRepository('owner/repo');await h.render().run();assert.equal(h.calls.length,0);assert.equal(h.storage.has(KEY),false);
});
test('late status GET after Back/Forward cannot replace a different selected run',async()=>{
  let finish;const h=harness(()=>new Promise(resolve=>{finish=resolve;}));
  h.window.location.searchParams.set('run_id','comprun_first');h.reload();await settle();
  h.window.location.searchParams.set('run_id','comprun_second');h.dispatch('popstate');finish(Response.json(accepted('comprun_first')));await settle();
  assert.equal(h.window.location.searchParams.get('run_id'),'comprun_second');assert.equal(h.render().result,null);assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('unavailable storage AND history prevent any intake POST or duplicate click',async()=>{
  const h=harness(()=>{throw Error('POST must not execute');});h.window.localStorage.setItem=()=>{throw Error('storage denied');};
  h.window.history.replaceState=()=>{throw Error('history denied');};h.window.location.replace=()=>{};
  await h.configure().run();assert.equal(h.render().issue.code,'assessment_intake_recovery_unavailable');assert.equal(h.render().issue.runCreated,false);
  await h.render().run();assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('URL-only pending reservation survives lost response with storage unavailable',async()=>{
  const h=harness(c=>{if(c.method==='POST')throw Error('lost');return missing();});h.window.localStorage.setItem=()=>{throw Error('storage denied');};
  await h.configure().run();const id=h.window.location.searchParams.get('run_id');assert.ok(id);h.reload();await settle();
  assert.equal(h.render().issue.runCreated,false);await h.render().retry();assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('proven rejection clears this URL-only reservation when storage is unavailable',async()=>{
  const h=harness(c=>c.method==='POST'?denied('specialist_authentication_required'):missing());h.window.localStorage.setItem=()=>{throw Error('storage denied');};
  await h.configure().run();assert.equal(h.window.location.searchParams.get('run_id'),null);assert.equal(h.render().protectedRunId,'');
});

for (const failure of [false,true]) test(`navigation while status GET pending offers enabled recovery after settlement (failure=${failure})`,async()=>{
  let finish, hold=true;const h=harness(c=>hold?new Promise(r=>{finish=r;}):Response.json(accepted(c.url.split('/').at(-1))));
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');
  finish(failure?missing():Response.json(accepted('comprun_A')));await settle();
  const recovery=h.render();assert.equal(recovery.phase,'unavailable');assert.equal(recovery.running,false);
  assert.equal(recovery.issue.retryable,true);assert.equal(recovery.issue.code,'assessment_selected_run_recovery_required');assert.equal(recovery.protectedRunId,'comprun_B');
  assert.equal(recovery.result,null);hold=false;const before=h.calls.length;
  await Promise.all([recovery.retry(),recovery.retry(),recovery.retry()]);
  assert.equal(h.calls.length,before+1);assert.equal(h.render().result.run_id,'comprun_B');assert.equal(h.render().phase,'review_required');
  h.reload();await settle();assert.equal(h.render().result.run_id,'comprun_B');
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();assert.equal(h.render().result.run_id,'comprun_A');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('selected-run recovery failure keeps visible retry and never POSTs',async()=>{
  let finish, hold=true;const h=harness(()=>hold?new Promise(r=>{finish=r;}):missing());
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');
  finish(Response.json(accepted('comprun_A')));await settle();hold=false;await h.render().retry();
  assert.equal(h.render().running,false);assert.equal(h.render().issue.retryable,true);assert.equal(h.render().protectedRunId,'comprun_B');
  await Promise.all([h.render().retry(),h.render().retry()]);assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('navigation while intake response pending offers recovery without another intake',async()=>{
  let finish,id;const h=harness(c=>{if(c.method==='POST'){id=c.body.run_id;return new Promise(r=>{finish=r;});}return Response.json(accepted(c.url.split('/').at(-1)));});
  const pending=h.configure().run();await settle();h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');
  finish(Response.json(accepted(id)));await pending;assert.equal(h.render().running,false);assert.equal(h.render().issue.retryable,true);
  await h.render().retry();assert.equal(h.render().result.run_id,'comprun_B');
  h.window.location.searchParams.set('run_id',id);h.reload();await settle();assert.equal(h.render().result.run_id,id);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('navigation during readiness preflight does not overwrite selection or POST',async()=>{
  let finish;const respond=c=>Response.json(accepted(c.url.split('/').at(-1)));respond.readiness=()=>new Promise(r=>{finish=r;});
  const h=harness(respond);const pending=h.configure().run();await settle();h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');
  finish(Response.json({status:'ready',survives_container_replacement_verified:true}));await pending;
  assert.equal(h.window.location.searchParams.get('run_id'),'comprun_B');assert.equal(h.render().running,false);assert.equal(h.render().issue.retryable,true);
  await h.render().retry();assert.equal(h.render().result.run_id,'comprun_B');assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('navigation away from an accepted continuation never replays old continuation',async()=>{
  let finish;const h=harness(c=>{if(c.method==='POST')return new Promise(r=>{finish=r;});const id=c.url.split('/').at(-1);
    return Response.json(id==='comprun_A'?{...accepted(id),status:'running',terminal:false,progress_percent:25}:accepted(id));});
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');
  finish(Response.json(accepted('comprun_A')));await settle();assert.equal(h.render().running,false);assert.equal(h.render().issue.retryable,true);
  await h.render().retry();assert.equal(h.render().result.run_id,'comprun_B');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.url.endsWith('/comprehensive-intake')).length,0);
});
test('Back and Forward between previously completed identities recover without intake',async()=>{
  const h=harness(c=>Response.json(accepted(c.url.split('/').at(-1))));h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  assert.equal(h.render().result.run_id,'comprun_A');
  for(const id of ['comprun_B','comprun_A','comprun_B']) {
    h.window.location.searchParams.set('run_id',id);h.dispatch('popstate');await settle();
    assert.equal(h.render().running,false);assert.equal(h.render().issue.retryable,true);
    await h.render().retry();assert.equal(h.render().result.run_id,id);assert.equal(h.render().phase,'review_required');
  }
  assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('explicit retry honors selected URL over stale visible result before history event',async()=>{
  const h=harness(c=>Response.json(accepted(c.url.split('/').at(-1))));h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  const stale=h.render();assert.equal(stale.result.run_id,'comprun_A');h.window.location.searchParams.set('run_id','comprun_B');
  const before=h.calls.length;await stale.retry();assert.equal(h.calls.length,before+1);assert.equal(h.calls.at(-1).method,'GET');
  assert.ok(h.calls.at(-1).url.endsWith('/comprun_B'));assert.equal(h.render().result.run_id,'comprun_B');assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('terminal pageshow online and foreground preserve completed view without requests',async()=>{
  const h=harness(c=>Response.json(accepted(c.url.split('/').at(-1))));h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  const before=h.calls.length;for(const event of ['pageshow','online','visibilitychange'])h.dispatch(event);await settle();
  assert.equal(h.calls.length,before);assert.equal(h.render().phase,'review_required');assert.equal(h.render().result.run_id,'comprun_A');
  assert.equal(h.storage.has(KEY),false);
});
test('ordinary page resume does not cancel or duplicate an accepted continuation',async()=>{
  let finish,posts=0;const active={...accepted('comprun_A'),status:'running',terminal:false,progress_percent:25};
  const h=harness(c=>{if(c.method==='POST'){posts++;return posts===1?new Promise(r=>{finish=r;}):Response.json(accepted('comprun_A'));}
    return Response.json(posts>=2?accepted('comprun_A'):active);});
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();const before=h.calls.length;
  for(const event of ['pageshow','online','visibilitychange'])h.dispatch(event);await settle();assert.equal(h.calls.length,before);
  finish(Response.json({...active,progress_percent:50}));await settle();assert.equal(posts,2);assert.equal(h.render().phase,'review_required');
  assert.equal(h.render().result.commit_sha,'a'.repeat(40));assert.equal(h.calls.filter(c=>c.url.endsWith('/comprehensive-intake')).length,0);
});
test('terminal URL stays protected without visible result until explicit Start new reset',async()=>{
  const h=harness(c=>Response.json(accepted(c.url.split('/').at(-1))));h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();
  h.window.location.searchParams.set('run_id','comprun_B');h.dispatch('popstate');await settle();assert.equal(h.render().result,null);
  // A is suppressed as terminal in same-document ordinary persistence reads.
  h.window.location.searchParams.set('run_id','comprun_A');const before=h.calls.length;await h.render().run();
  assert.equal(h.calls.length,before);assert.equal(h.window.location.searchParams.get('run_id'),'comprun_A');
  h.render().startNew();assert.equal(h.render().result,null);assert.equal(h.render().protectedRunId,'');assert.equal(h.render().authorized,false);
  assert.equal(h.window.location.searchParams.get('run_id'),null);assert.ok(h.window.location.searchParams.has('new_assessment'));
  for(const event of ['pageshow','online'])h.dispatch(event);await settle();assert.equal(h.calls.length,before);assert.equal(h.render().phase,'idle');
});
test('transient exact status failure retries GET and preserves canonical identity',async()=>{
  let gets=0;const h=harness(c=>{assert.equal(c.method,'GET');return ++gets===1?Response.json({detail:{code:'temporarily_unavailable'}},{status:503}):Response.json(accepted('comprun_A'));});
  h.window.location.searchParams.set('run_id','comprun_A');h.reload();await settle();assert.equal(gets,2);assert.equal(h.render().phase,'review_required');
  assert.equal(h.render().result.run_id,'comprun_A');assert.equal(h.render().result.commit_sha,'a'.repeat(40));assert.equal(h.render().result.client_delivery_allowed,false);
});
