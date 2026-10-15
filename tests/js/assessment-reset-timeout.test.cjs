'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '../..');
const fromWeb = createRequire(path.join(process.env.NICO_TEST_WEB_ROOT || path.join(ROOT,'apps/web'), 'package.json'));
const ts = fromWeb('typescript');
const React = fromWeb('react');
const RUN = 'comprun_owned_reset';
const KEY = 'nico.comprehensive.active-run.v1';
const finished = {run_id:RUN,repository:'owner/repo',commit_sha:'a'.repeat(40),status:'review_required',terminal:true,
  assessment_state:'review_required',progress_percent:100,human_review_required:true,client_delivery_allowed:false};
const settle = async () => {for(let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));};

function harness() {
  const frames = new Map(), cache = new Map(), listeners = new Map(), timers = new Map(), storage = new Map(), calls=[];
  let frame, cursor=0, timer=0, hang=false;
  const storageApi={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
  function on(type,fn) {if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);}
  const dispatch = e => {for(const fn of listeners.get(e.type)||[]) fn(e);};
  const window={location:new URL(`https://nico.test/assessment?tier=comprehensive&run_id=${RUN}`),localStorage:storageApi,sessionStorage:storageApi,
    history:{state:null,replaceState(_s,_t,url){window.location=new URL(url,window.location);}},
    addEventListener:on,removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),dispatchEvent:dispatch,
    setTimeout(fn,ms){timers.set(++timer,{fn,ms});return timer;},clearTimeout:id=>timers.delete(id),
    setInterval(){return 0;},clearInterval(){},requestAnimationFrame:fn=>fn(),scrollTo(){},
  };
  const document={visibilityState:'visible',documentElement:{lang:'en',removeAttribute(){},style:{removeProperty(){}}},body:{},
    querySelector(){return null;},addEventListener:on,removeEventListener:window.removeEventListener};
  window.fetch=(url,init={})=>{calls.push({url:String(url),method:init.method||'GET'});
    if(!hang)return Promise.resolve(Response.json(finished));
    return new Promise((_resolve,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true}));};
  const hooks={...React,useState(initial){const i=cursor++;if(!(i in frame.state))frame.state[i]=typeof initial==='function'?initial():initial;
    const f=frame;return [f.state[i],v=>{f.state[i]=typeof v==='function'?v(f.state[i]):v;}];},
    useRef(initial){const i=cursor++;if(!(i in frame.state))frame.state[i]={current:initial};return frame.state[i];},
    useEffect(effect){if(!frame.mounted)frame.effects.push(effect);}};
  function load(filename){if(cache.has(filename))return cache.get(filename);const module={exports:{}};
    const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
    vm.runInNewContext(code,{module,exports:module.exports,window,document,URL,URLSearchParams,Request,Response,Headers,AbortController,DOMException,
      CustomEvent:class {constructor(type,options){this.type=type;this.detail=options?.detail;}},
      MutationObserver:class {observe(){}disconnect(){}},process:{env:{}},console,
      fetch:(...args)=>window.fetch(...args),setTimeout:window.setTimeout,clearTimeout:window.clearTimeout,
      require(name){if(name==='react')return hooks;if(name.endsWith('.css'))return {};
        if(!name.startsWith('.'))return fromWeb(name);const base=path.resolve(path.dirname(filename),name);
        return load(['.ts','.tsx'].map(ext=>base+ext).find(fs.existsSync));}}, {filename});
    cache.set(filename,module.exports);return module.exports;}
  const Recovery=load(path.join(ROOT,'apps/web/app/ComprehensiveStuckRunRecovery.tsx')).default;
  const useRun=load(path.join(ROOT,'apps/web/app/assessment/useAssessmentRun.ts')).useAssessmentRun;
  function render(name,fn){if(!frames.has(name))frames.set(name,{state:[],effects:[],mounted:false});frame=frames.get(name);cursor=0;
    const value=fn();if(!frame.mounted){frame.mounted=true;frame.effects.forEach(effect=>effect());}return value;}
  render('recovery',()=>Recovery());
  const controller=()=>render('run',()=>useRun('en'));
  controller();
  return {controller,window,calls,storage,dispatch,async lateRequest(runId=RUN){hang=true;
    const promise=window.fetch(`/api/nico/assessment/comprehensive-run/${runId}`,{method:'GET'}).catch(()=>null);
    const timeout=[...timers.values()].filter(t=>t.ms===90000).at(-1);assert.ok(timeout);hang=false;
    return {fire:async()=>{timeout.fn();await promise;await settle();}};},
    recovery:()=>render('recovery',()=>Recovery())};
}

test('late old-run timeout after Start new cannot restore its URL or resume it',async()=>{
  const h=harness();await settle();assert.equal(h.controller().phase,'review_required');
  const pending=await h.lateRequest();h.controller().startNew();
  assert.equal(h.controller().result,null);assert.ok(h.window.location.searchParams.has('new_assessment'));
  const before=h.calls.length;await pending.fire();
  assert.equal(h.window.location.searchParams.get('run_id'),null);
  assert.ok(h.window.location.searchParams.has('new_assessment'));
  h.dispatch({type:'pageshow'});await settle();
  assert.equal(h.calls.length,before);assert.equal(h.controller().phase,'idle');assert.equal(h.controller().protectedRunId,'');
  assert.equal(h.recovery(),null);assert.equal(h.storage.has(KEY),false);
});

test('legitimate same-run timeout retains exact recovery and completed report',async()=>{
  const h=harness();await settle();const pending=await h.lateRequest();await pending.fire();
  assert.equal(h.window.location.searchParams.get('run_id'),RUN);
  assert.equal(JSON.parse(h.storage.get(KEY)).runId,RUN);assert.ok(h.recovery());
  assert.equal(h.controller().result.run_id,RUN);assert.equal(h.controller().result.client_delivery_allowed,false);
});

test('late old-run timeout cannot replace a newer explicitly selected run',async()=>{
  const h=harness();await settle();const pending=await h.lateRequest();h.controller().startNew();
  h.window.location.searchParams.set('run_id','comprun_owned_new');h.window.location.searchParams.delete('new_assessment');
  await pending.fire();assert.equal(h.window.location.searchParams.get('run_id'),'comprun_owned_new');assert.equal(h.recovery(),null);
});

for (const pathname of ['/assessment','//other.example/assessment']) test(`history failure stays on origin for ${pathname}`,async()=>{
  const h=harness();await settle();let target;
  h.window.location.pathname=pathname;
  h.window.location.replace=url=>{target=new URL(url,h.window.location);};
  h.window.history.replaceState=()=>{throw new DOMException('owned history failure','SecurityError');};
  assert.doesNotThrow(()=>h.controller().startNew());
  assert.equal(target.origin,'https://nico.test');assert.equal(target.searchParams.get('run_id'),null);
  assert.ok(target.searchParams.has('new_assessment'));assert.equal(h.controller().result,null);
});


test('ignoring an old timeout does not dismiss recovery for the newly selected run',async()=>{
  const h=harness();await settle();const old=await h.lateRequest();h.controller().startNew();
  const next='comprun_owned_new';h.window.location.searchParams.set('run_id',next);h.window.location.searchParams.delete('new_assessment');
  const current=await h.lateRequest(next);await current.fire();
  assert.ok(h.recovery());assert.equal(JSON.parse(h.storage.get(KEY)).runId,next);
  await old.fire();assert.ok(h.recovery());assert.equal(h.window.location.searchParams.get('run_id'),next);
  assert.equal(JSON.parse(h.storage.get(KEY)).runId,next);
});
