'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const web = createRequire(path.join(root, 'apps/web/package.json'));
const ts = web('typescript'), React = web('react');
const dir = path.join(root,'apps/web/app/operations/backup-restore');
function fixture() {return JSON.parse(fs.readFileSync(path.join(root,'docs/examples/backup-restore-import.synthetic.json'),'utf8'));}
function harness(entry='page.tsx', props={scope:'customer_id=synthetic&project_id=synthetic'}, respond=async()=>({ok:true,json:async()=>({})})) {
 const states=[];let cursor=0;const cache=new Map(),calls=[];
 function load(file) {
  if(cache.has(file)) return cache.get(file);
  const module={exports:{}};
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{module,exports:module.exports,Date,Intl,TextEncoder,URLSearchParams,
   process:{env:{NEXT_PUBLIC_NICO_API_URL:'https://synthetic.invalid'}},
   fetch:async(url,init)=>{calls.push({url,init});return respond(url,init);},
   require(name){
    if(name==='react')return {...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return [states[i],value=>{states[i]=typeof value==='function'?value(states[i]):value;}];},useRef(initial){const i=cursor++;if(!(i in states))states[i]={current:initial};return states[i];}};
    if(!name.startsWith('.'))return web(name);
    const base=path.resolve(path.dirname(file),name);return load(['.ts','.tsx'].map(ext=>base+ext).find(fs.existsSync));
   }},{filename:file});
  cache.set(file,module.exports);return module.exports;
 }
 const Component=load(path.join(dir,entry)).default;
 function expand(node){if(!node||typeof node!=='object')return node;if(Array.isArray(node))return node.map(expand);if(typeof node.type==='function')return expand(node.type(node.props));return React.cloneElement(node,{},...React.Children.toArray(node.props.children).map(expand));}
 function render(){cursor=0;return expand(Component(props));}
 function all(node,predicate){if(!node||typeof node!=='object')return [];return [...(predicate(node)?[node]:[]),...React.Children.toArray(node.props.children).flatMap(child=>all(child,predicate))];}
 const find=p=>all(render(),p);
 const text=node=>typeof node==='string'?node:typeof node==='number'?String(node):node&&node.props?React.Children.toArray(node.props.children).map(text).join(''):'';
 const button=prefix=>find(n=>n.type==='button'&&text(n).startsWith(prefix))[0];
 const input=prefix=>{const label=find(n=>n.type==='label'&&text(n).startsWith(prefix))[0];assert.ok(label,prefix);return all(label,n=>['input','textarea'].includes(n.type))[0];};
 const set=(label,value)=>input(label).props.onChange({target:{value,checked:value}});
 async function choose(value){const file=value===null?undefined:typeof value.text==='function'?value:{size:JSON.stringify(value).length,text:async()=>JSON.stringify(value)};find(n=>n.type==='input'&&n.props.type==='file')[0].props.onChange({currentTarget:{files:file?[file]:[],value:'fake'}});await new Promise(resolve=>setImmediate(resolve));}
 return {find,button,input,set,choose,calls,text:()=>text(render()),click:prefix=>{const b=button(prefix);assert.ok(b,prefix);assert.ok(!b.props.disabled,prefix+' enabled');return b.props.onClick();},load};
}
const parser=harness('EvidenceFileImport.tsx',{disabled:false,onConfirm(){}}).load(path.join(dir,'evidenceImport.ts'));
test('strict format parses without mutating flags or fixture',()=>{const raw=JSON.stringify(fixture());assert.equal(JSON.stringify(parser.parseEvidenceImport(raw)),raw);});
for(const [name,change] of [
 ['unknown root',x=>x.token='never transmit'],['unknown nested',x=>x.backup.password='secret'],
 ['unsupported version',x=>x.format='other'],['unsupported provider',x=>x.provider='postgres://private'],
 ['mismatched backup',x=>x.restore.source_backup_reference_sha256='d'.repeat(64)],
 ['uppercase hash',x=>x.schema_contract_sha256='A'.repeat(64)],['number instead of boolean',x=>x.backup.successful=1],
 ['null object',x=>x.backup=null],['array object',x=>x.restore=[]],['unknown method',x=>x.verification.method='full'],
 ['full bootstrap overclaim',x=>x.verification.full_bootstrap_or_http_verified=true],['too many samples',x=>x.verification.sample_count=4],
 ['fractional count',x=>x.backup.retention_days=1.2],['invalid leap day',x=>x.backup.completed_at='2025-02-29T07:00:00Z'],
 ['invalid month',x=>x.backup.completed_at='2026-13-01T07:00:00Z'],['ambiguous local time',x=>x.backup.completed_at='2026-01-01T07:00:00'],
 ['offset timestamp',x=>x.backup.completed_at='2026-01-01T07:00:00+01:00'],['future date',x=>x.restore.completed_at='2099-01-01T07:00:00Z'],
 ['restore before backup',x=>x.restore.completed_at='2025-01-01T07:00:00Z'],['PITR contradiction',x=>x.backup.pitr_window_hours=24],
 ['secret note',x=>x.restore.note='credential'],['prototype key',x=>Object.defineProperty(x,'__proto__',{value:{},enumerable:true})]
])test('reject '+name,()=>{const x=fixture();change(x);assert.throws(()=>parser.parseEvidenceImport(JSON.stringify(x)));});
test('reject duplicate escaped keys, malformed JSON, oversized data',()=>{for(const raw of ['{"format":1,"for\\u006dat":2}','not json','{"a":}', ' '.repeat(16385),'[[[[[[]]]]]]'])assert.throws(()=>parser.parseEvidenceImport(raw));});
test('schema match required without normalization/fallback',()=>{const x=fixture();assert.throws(()=>parser.requireMatchingSchema(x));assert.throws(()=>parser.requireMatchingSchema(x,'d'.repeat(64)));parser.requireMatchingSchema(x,x.schema_contract_sha256);});
test('UTC instant and milliseconds survive local conversion, including DST fold',()=>{const old=process.env.TZ;try {for(const tz of ['UTC','America/New_York','Asia/Kolkata']){process.env.TZ=tz;for(const utc of ['2026-01-01T07:51:16.234Z','2026-11-01T06:30:00.000Z']){const local=parser.localDateTime(utc);assert.equal(parser.evidenceInstant(local,utc),utc);}}}finally{if(old===undefined)delete process.env.TZ;else process.env.TZ=old;}});
test('cancel preview and repeated import never submit or populate before confirmation',async()=>{const applied=[];const h=harness('EvidenceFileImport.tsx',{schema:fixture().schema_contract_sha256,disabled:false,onConfirm:x=>applied.push(x)});await h.choose(fixture());assert.equal(applied.length,0);assert.match(h.text(),/UTC:.*2026-01-01/);assert.match(h.text(),/Full bootstrap\/HTTP/);h.click('Cancel import');assert.equal(applied.length,0);await h.choose(fixture());h.click('Confirm and fill');assert.equal(applied.length,1);assert.equal(h.calls.length,0);});
test('cancel reading and out-of-order file completion cannot apply stale content',async()=>{let resolve;const h=harness('EvidenceFileImport.tsx',{schema:fixture().schema_contract_sha256,disabled:false,onConfirm(){throw Error('unexpected');}});await h.choose({size:10,text:()=>new Promise(r=>resolve=r)});h.click('Cancel import');resolve(JSON.stringify(fixture()));await new Promise(r=>setImmediate(r));assert.ok(!h.button('Confirm and fill'));});
test('wrong files and schema mismatches cannot be applied',async()=>{const h=harness('EvidenceFileImport.tsx',{schema:'d'.repeat(64),disabled:false,onConfirm(){throw Error('unexpected');}});await h.choose(fixture());assert.equal(h.button('Confirm and fill').props.disabled,true);await h.choose({password:'secret'});assert.ok(!h.button('Confirm and fill'));assert.ok(!h.text().includes('secret'));});
function summary(){return {schema_contract_sha256:fixture().schema_contract_sha256,latest_backup:{present:false},latest_restore_drill:{present:false}};}
function setup(respond){const h=harness('page.tsx',{},respond);h.set('NICO admin token','synthetic-token');h.set('Operator or reviewer','Test Operator');return h;}
test('real page imports locally, then backup and restore submit separately with preserved fields and auth',async()=>{
 let current=summary();const h=setup(async(url,init)=>{if(init.method!=='POST')return {ok:true,json:async()=>current};const b=JSON.parse(init.body);if(url.includes('backup-evidence'))current={...current,latest_backup:{present:true,...b}};else current={...current,latest_restore_drill:{present:true,...b}};return {ok:true,json:async()=>({status:'recorded',backup_restore:current})};});
 await h.click('Refresh backup');await h.choose(fixture());h.click('Confirm and fill');assert.equal(h.calls.length,1);assert.equal(h.input('NICO admin token').props.value,'synthetic-token');assert.equal(h.input('Operator or reviewer').props.value,'Test Operator');
 await h.click('Record isolated');assert.equal(h.calls.length,1);assert.match(h.text(),/matching backup/);
 await h.click('Record backup evidence');assert.equal(h.calls.length,2);assert.equal(h.input('Restored record-set').props.value,fixture().restore.restored_record_set_sha256);
 await h.click('Record isolated');assert.equal(h.calls.length,3);const body=JSON.parse(h.calls[2].init.body);assert.equal(body.completed_at,fixture().restore.completed_at);assert.equal(body.schema_contract_sha256,fixture().schema_contract_sha256);assert.equal(body.application_read_verified,false);assert.match(body.note,/3 unreviewed records/);assert.equal(h.calls[2].init.headers['X-NICO-Admin-Token'],'synthetic-token');
 await h.choose(fixture());h.click('Confirm and fill');await h.click('Record backup evidence');await h.click('Record isolated');assert.equal(h.calls.length,3);
});
test('double click and uncertain write cannot be retried by reimport',async()=>{let resolve;const h=setup(async(url,init)=>init.method==='POST'?new Promise(r=>resolve=r):({ok:true,json:async()=>summary()}));await h.click('Refresh backup');await h.choose(fixture());h.click('Confirm and fill');const button=h.button('Record backup evidence');const pending=button.props.onClick();await button.props.onClick();assert.equal(h.calls.length,2);resolve({ok:false,status:503,json:async()=>({})});await pending;await h.choose(fixture());h.click('Confirm and fill');await h.click('Record backup evidence');assert.equal(h.calls.length,2);assert.match(h.text(),/unresolved/);});
test('scope/schema drift cannot submit imported claims',async()=>{const h=setup(async()=>({ok:true,json:async()=>summary()}));await h.click('Refresh backup');await h.choose(fixture());h.click('Confirm and fill');h.set('Project ID','different');await h.click('Record backup evidence');assert.equal(h.calls.length,1);assert.match(h.text(),/Refresh status for this scope/);});
test('manual entry remains usable without a file',async()=>{const h=setup(async()=>({ok:true,json:async()=>({status:'recorded',backup_restore:summary()})}));h.set('Backup reference SHA','b'.repeat(64));await h.click('Record backup evidence');assert.equal(h.calls.length,1);assert.equal(JSON.parse(h.calls[0].init.body).successful,false);});

test('confirmed scope stays bound after another scope refresh with identical schema',async()=>{
 const h=setup(async()=>({ok:true,json:async()=>summary()}));await h.click('Refresh backup');await h.choose(fixture());h.click('Confirm and fill');h.set('Project ID','other');await h.click('Refresh backup');await h.click('Record backup evidence');assert.equal(h.calls.length,2);assert.match(h.text(),/Re-import and confirm/);
});
test('pending preview cannot be confirmed after a scope change and refresh',async()=>{
 const h=setup(async()=>({ok:true,json:async()=>summary()}));await h.click('Refresh backup');await h.choose(fixture());h.set('Customer ID','other');await h.click('Refresh backup');assert.equal(h.button('Confirm and fill').props.disabled,true);assert.match(h.text(),/scope changed/);await h.choose(fixture());assert.equal(h.button('Confirm and fill').props.disabled,false);
});
test('a newer file selection wins over an older late file read',async()=>{
 let resolve;const applied=[];const h=harness('EvidenceFileImport.tsx',{scope:'same',schema:fixture().schema_contract_sha256,disabled:false,onConfirm:x=>applied.push(x)});
 await h.choose({size:10,text:()=>new Promise(r=>resolve=r)});const second=fixture();second.verification.sample_count=1;await h.choose(second);resolve(JSON.stringify(fixture()));await new Promise(r=>setImmediate(r));h.click('Confirm and fill');assert.equal(applied[0].verification.sample_count,1);
});
test('server schema change after confirmation blocks both imported submissions',async()=>{
 let current=summary();const h=setup(async()=>({ok:true,json:async()=>current}));await h.click('Refresh backup');await h.choose(fixture());h.click('Confirm and fill');current={...current,schema_contract_sha256:'d'.repeat(64)};await h.click('Refresh backup');await h.click('Record backup evidence');await h.click('Record isolated');assert.equal(h.calls.length,2);assert.match(h.text(),/current schema contract/);
});
test('oversized file is rejected before reading content',async()=>{
 const h=harness('EvidenceFileImport.tsx',{scope:'same',disabled:false,onConfirm(){throw Error('unexpected');}});let reads=0;await h.choose({size:16385,text(){reads++;return Promise.resolve('{}');}});assert.equal(reads,0);assert.match(h.text(),/16 KiB/);
});
