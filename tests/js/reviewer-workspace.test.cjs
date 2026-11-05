'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test'),{createRequire}=require('node:module');
const ROOT=path.resolve(__dirname,'../..'),web=createRequire(path.join(ROOT,'apps/web/package.json'));
const ts=web('typescript'),React=web('react');
const RUN='comprun_saved';
const payload=(run=RUN)=>({run_id:run,repository:'owner/repo',commit_sha:'a'.repeat(40),evidence_ledger_id:'ledger',candidate_count:1,
 dispositioned_candidate_count:0,remaining_candidate_count:1,quality_control_required_count:0,quality_control_completed_count:0,open_evidence_request_count:0,
 candidates:[{candidate_id:'candidate_a',human_disposition_state:'pending'}],clusters:[],queue_counts:{},workload_metrics:{human_dispositions_pending:1},quality_control_sampling:{},
 ledger:{},empirical_measurement:{},unresolved_high_impact_candidate_ids:[],ready_for_final_approval:false,human_review_required:true,client_delivery_allowed:false});
const completed=()=>({...payload(),remaining_candidate_count:0,dispositioned_candidate_count:1,workload_metrics:{human_dispositions_pending:0,human_dispositions_completed:1},candidates:[{candidate_id:'candidate_a',human_disposition_state:'completed'}]});
function harness(respond){
 const frames=new Map(),cache=new Map(),calls=[];let frame,cursor,dirty=true,tree;
 const location=new URL('https://nico.test/operations/reviewer-queue?run_id='+RUN);
 const window={location,history:{state:null,replaceState(_s,_t,url){window.location=new URL(url,window.location);}}};
 const hooks={...React,useState(initial){const i=cursor++;if(!(i in frame.slots))frame.slots[i]=typeof initial==='function'?initial():initial;const f=frame;
 return [f.slots[i],v=>{f.slots[i]=typeof v==='function'?v(f.slots[i]):v;dirty=true;}];},
 useRef(initial){const i=cursor++;if(!(i in frame.slots))frame.slots[i]={current:initial};return frame.slots[i];},
 useMemo(fn){return fn();},useEffect(fn,deps){const i=cursor++,old=frame.slots[i];if(!old||!deps||deps.some((x,j)=>!Object.is(x,old.deps[j]))) {frame.effects.push(()=>{old?.cleanup?.();frame.slots[i]={deps,cleanup:fn()};});}}};
 function load(file){if(cache.has(file))return cache.get(file);const module={exports:{}};cache.set(file,module.exports);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,{module,exports:module.exports,window,document:{documentElement:{}},URL,URLSearchParams,Headers,Response,console,
 fetch:async(url,init={})=>{const call={url:String(url),init};calls.push(call);return respond(call);},
 require(name){if(name==='react')return hooks;if(name.endsWith('.css'))return {default:{}};if(!name.startsWith('.'))return web(name);
 const base=path.resolve(path.dirname(file),name);return load(['.tsx','.ts'].map(x=>base+x).find(fs.existsSync));}}, {filename:file});cache.set(file,module.exports);return module.exports;}
 const Page=load(path.join(ROOT,'apps/web/app/operations/reviewer-queue/page.tsx')).default;
 function walk(n,id,seen){if(n==null||typeof n!=='object')return n;if(Array.isArray(n))return n.map((x,i)=>walk(x,id+'/'+i,seen));
 if(typeof n.type==='function'){id+='/'+n.type.name+':'+(n.key||'');seen.add(id);if(!frames.has(id))frames.set(id,{slots:[],effects:[]});frame=frames.get(id);cursor=0;return walk(n.type(n.props),id,seen);}
 return {...n,props:{...n.props,children:React.Children.toArray(n.props?.children).map((x,i)=>walk(x,id+'/'+i,seen))}};}
 function render(){for(let loops=0;dirty&&loops<20;loops++){dirty=false;const seen=new Set();tree=walk(React.createElement(Page), 'root',seen);
 for(const [id,f]of frames)if(!seen.has(id)){for(const slot of f.slots)slot?.cleanup?.();frames.delete(id);}
 for(const f of frames.values()){const effects=f.effects.splice(0);for(const effect of effects){frame=f;effect();}}}return tree;}
 function all(n,p){if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...(n.props?.children||[]).flatMap(x=>all(x,p))];}
 const find=p=>all(render(),p),section=attr=>find(n=>n.props[attr])[0];
 const within=(attr,p)=>all(section(attr),p),button=(attr,label)=>within(attr,n=>n.type==='button'&&String(n.props.children).includes(label))[0];
 render();return {calls,render,find,within,button,select(run){find(n=>n.type==='input')[0].props.onChange({target:{value:run}});render();},
 async load(attr){const b=button(attr,'Load review');if(b?.props.onClick)await b.props.onClick();else await within(attr,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});render();},
 input(attr,label,value){const n=within(attr,n=>n.type==='label'&&n.props.children.includes(label))[0];all(n,x=>x.type==='input')[0].props.onChange({target:{value}});render();},
 async submit(){await within('data-phase2-review-work',n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});render();},
 async settle(){for(let i=0;i<8;i++){await new Promise(r=>setImmediate(r));render();}}};
}
const WORK='data-phase2-review-work',BROWSER='data-review-browser';
test('all panels share the selected exact run and discard old target selection',async()=>{
 const h=harness(()=>Response.json(payload()));h.input(WORK,'Candidate, cluster, or request ID','old_candidate');h.select('comprun_other');
 for(const attr of [WORK,BROWSER])assert.equal(h.within(attr,n=>n.type==='input')[0].props.value,'comprun_other');
 const label=h.within(WORK,n=>n.type==='label'&&n.props.children.includes('Candidate, cluster, or request ID'))[0];
 assert.equal(label.props.children.find(n=>n?.type==='input').props.value,'');assert.equal(h.calls.length,0);
});
for(const attr of [WORK,BROWSER])for(const bad of ['invalid-json','wrong-run','non-array','empty'])test(`${attr} rejects ${bad} without empty success or crash`,async()=>{
 const h=harness(()=>bad==='invalid-json'?new Response('{'):Response.json(bad==='empty'?{}:bad==='wrong-run'?payload('comprun_other'):{...payload(),candidates:{}}));
 await h.load(attr);assert.equal(h.within(attr,n=>n.props.role==='alert').length,1);
 assert.equal(h.within(attr,n=>n.type==='button'&&String(n.props.children).startsWith('Refresh')).length,0);
});
test('late old-run read cannot populate newly selected run',async()=>{let resolve;const h=harness(()=>new Promise(r=>{resolve=r;}));const pending=h.load(WORK);h.select('comprun_other');resolve(Response.json(payload()));await pending;
 assert.equal(h.within(WORK,n=>n.type==='button'&&String(n.props.children).startsWith('Refresh')).length,0);
});
for(const ambiguous of [false,true])test(`write refreshes siblings by GET; ambiguous=${ambiguous} never repeats POST`,async()=>{
 let written=false;const h=harness(call=>{if(call.init.method==='POST'){written=true;return ambiguous?new Response('{'):Response.json(completed());}
 return Response.json(written?completed():payload());});
 await h.load(WORK);await h.load(BROWSER);h.input(WORK,'Authorized reviewer','Reviewer');h.input(WORK,'Reviewer / specialist role','Specialist');h.input(WORK,'Candidate, cluster, or request ID','candidate_a');
 const before=h.calls.length;await h.submit();await h.settle();const calls=h.calls.slice(before);assert.equal(calls.filter(c=>c.init.method==='POST').length,1);
 assert.ok(calls.filter(c=>(c.init.method||'GET')==='GET'&&c.url.endsWith('/review-work')).length>=2);
 assert.ok(calls.some(c=>c.url.endsWith('/review-queue')));assert.ok(calls.every(c=>c.url.includes(RUN)));
 const pending=h.within(BROWSER,n=>n.type==='article'&&n.props.children.some(c=>c?.type==='span'&&c.props.children.includes('human dispositions pending')))[0];
 assert.equal(pending.props.children.find(c=>c?.type==='strong').props.children[0],'0');
 const body=JSON.parse(calls[0].init.body);assert.equal(body.review_authorized,true);assert.equal(body.authorization_confirmed,true);
});

function authorize(h){h.input(WORK,'Authorized reviewer','Reviewer');h.input(WORK,'Reviewer / specialist role','Specialist');h.input(WORK,'Candidate, cluster, or request ID','candidate_a');}
for(const status of [401,403])test(`denied write ${status} remains blocked without reconciliation or repeat`,async()=>{
 const h=harness(c=>c.init.method==='POST'?Response.json({detail:'private backend text'},{status}):Response.json(payload()));await h.load(WORK);authorize(h);
 const before=h.calls.length;await h.submit();await h.settle();assert.equal(h.calls.length,before+1);
 assert.equal(h.within(WORK,n=>n.type==='button'&&n.props.type==='submit')[0].props.disabled,true);
});
test('ambiguous write plus failed GET leaves actions blocked and explicit uncertainty',async()=>{
 let writes=0;const h=harness(c=>c.init.method==='POST'?(writes++,new Response('{')):writes?Response.json(payload('comprun_wrong')):Response.json(payload()));
 await h.load(WORK);authorize(h);await h.submit();await h.settle();assert.equal(writes,1);
 assert.equal(h.within(WORK,n=>n.type==='button'&&n.props.type==='submit')[0].props.disabled,true);
 assert.ok(h.within(WORK,n=>n.props.role==='alert').length);assert.equal(h.calls.length,3);
});
test('in-flight write cannot be duplicated or refresh a subsequently selected run',async()=>{
 let resolve;const h=harness(c=>c.init.method==='POST'?new Promise(r=>{resolve=r;}):Response.json(payload()));await h.load(WORK);authorize(h);
 const before=h.calls.length;const first=h.submit();await h.submit();assert.equal(h.calls.length,before+1);
 h.select('comprun_other');resolve(Response.json(payload()));await first;await h.settle();assert.equal(h.calls.length,before+1);
 assert.equal(h.within(WORK,n=>n.type==='input')[0].props.value,'comprun_other');
});
test('newer same-run read wins over a late older projection',async()=>{
 const pending=[];const h=harness(()=>new Promise(r=>pending.push(r)));const old=h.load(WORK);const latest=h.load(WORK);
 pending[1](Response.json({...payload(),candidate_count:0,candidates:[],remaining_candidate_count:0}));await latest;
 pending[0](Response.json(payload('comprun_wrong')));await old;assert.equal(h.within(WORK,n=>n.props.role==='alert').length,0);
 assert.ok(h.within(WORK,n=>n.type==='button'&&String(n.props.children).startsWith('Refresh')).length);
});
for(const change of [{clusters:{}},{human_review_required:false},{client_delivery_allowed:true},{candidate_count:99}])test(`review projection rejects gate or shape mismatch ${JSON.stringify(change)}`,async()=>{
 const h=harness(()=>Response.json({...payload(),...change}));await h.load(WORK);assert.equal(h.within(WORK,n=>n.props.role==='alert').length,1);
});

for (const ambiguous of [false, true]) test(`sibling refresh cannot supersede a pending disposition write (ambiguous=${ambiguous})`,async()=>{
 let resolveWork,committed=false;const h=harness(c=>{
   if(c.init.method==='POST'&&JSON.parse(c.init.body).action==='disposition_candidate')return new Promise(r=>{resolveWork=r;});
   return Response.json(committed?completed():payload());
 });
 await h.load(WORK);await h.load(BROWSER);authorize(h);
 h.input(BROWSER,'Authorized reviewer','QC reviewer');h.input(BROWSER,'Reviewer role','Specialist');
 const work=h.submit();await h.button(BROWSER,'Configure explicit QC sample').props.onClick();await h.settle();
 assert.equal(h.within(WORK,n=>n.type==='button'&&n.props.type==='submit')[0].props.disabled,true,'pending write remains locked through sibling refresh');
 const before=h.calls.length;committed=true;resolveWork(ambiguous ? new Response('{') : Response.json(completed()));
 await work;await h.settle();assert.ok(h.calls.slice(before).some(c=>(c.init.method||'GET')==='GET'));
 assert.equal(h.calls.filter(c=>c.init.method==='POST').length,2,'only two distinct authorized actions');
 if(ambiguous)assert.ok(h.within(WORK,n=>n.props.role==='alert').some(n=>String(n.props.children).includes('outcome was not confirmed')));
});

for(const panel of [WORK,BROWSER])for(const body of ['json','empty','html','truncated'])test(`${panel} HTTP408 ${body} reconciles only by GET and preserves uncertainty`,async()=>{
 const h=harness(call=>{
  if(call.init.method==='POST')return body==='json'?Response.json({detail:'timeout'},{status:408}):new Response(body==='empty'?'':body==='html'?'<html>Request timeout</html>':'{"detail":',{status:408});
  return Response.json(payload());
 });
 await h.load(panel);
 if(panel===WORK)authorize(h);else {h.input(BROWSER,'Authorized reviewer','Reviewer');h.input(BROWSER,'Reviewer role','Specialist');}
 const before=h.calls.length;
 if(panel===WORK)await h.submit();else await h.button(BROWSER,'Configure explicit QC sample').props.onClick();
 await h.settle();const calls=h.calls.slice(before);
 assert.equal(calls.filter(c=>c.init.method==='POST').length,1);
 assert.equal(calls[0].init.method,'POST');
 assert.ok(calls.slice(1).some(c=>c.init.method==='GET'&&c.url.endsWith('/review-work')),'timeout must reconcile the saved exact-run state');
 assert.ok(calls.slice(1).every(c=>(c.init.method||'GET')==='GET'));
 assert.ok(calls.every(c=>c.url.includes(RUN)&&c.init.credentials==='same-origin'));
 assert.ok(h.within(panel,n=>n.props.role==='alert').some(n=>String(n.props.children).includes('outcome was not confirmed')));
 const action=JSON.parse(calls[0].init.body);assert.equal(action.review_authorized,true);assert.equal(action.authorization_confirmed,true);
});
