'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const root=process.env.NICO_SOURCE_ROOT||path.resolve(__dirname,'../..');
const web=createRequire(path.join(__dirname,'../../apps/web/package.json'));
const ts=web('typescript'),React=web('react');
const cache=new Map();
function load(file){
 if(cache.has(file))return cache.get(file);
 const module={exports:{}};cache.set(file,module.exports);
 let code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 if(file.endsWith('/ReviewerQueue.tsx'))code+='\nmodule.exports.auditViews={CandidateDisclosure,FindingDisclosure};';
 vm.runInNewContext(code,{module,exports:module.exports,require(name){
  if(name==='react')return {...React,useState:()=>[true,()=>{}]};
  if(name.endsWith('.css'))return {default:{}};
  if(!name.startsWith('.'))return web(name);
  const base=path.resolve(path.dirname(file),name);return load(['.tsx','.ts'].map(s=>base+s).find(fs.existsSync));
 }},{filename:file});return module.exports;
}
const views=load(path.join(root,'apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx')).auditViews;
function pres(node){
 if(node==null||typeof node!=='object')return [];
 if(Array.isArray(node))return node.flatMap(pres);
 if(typeof node.type==='function')return pres(node.type(node.props));
 return [...(node.type==='pre'?[node]:[]),...React.Children.toArray(node.props?.children).flatMap(pres)];
}
for(const locale of ['en','es-MX'])test(`${locale}: disclosed evidence is named, focusable and preserves retained content`,()=>{
 const candidate={candidate_id:'candidate_a',evidence_used:['literal evidence'],counterevidence:['literal counterevidence']};
 const nodes=pres(React.createElement(views.CandidateDisclosure,{candidate,locale}));
 nodes.push(...pres(React.createElement(views.FindingDisclosure,{finding:{finding_id:'finding_a',evidence:'literal finding'},locale})));
 assert.equal(nodes.length,4);
 for(const node of nodes){assert.equal(node.props.tabIndex,0);assert.equal(node.props.role,'region');assert.match(node.props['aria-label'],/candidate_a|finding_a/);}
 assert.equal(new Set(nodes.map(n=>n.props['aria-label'])).size,4);
 assert.match(nodes[0].props['aria-label'],locale==='en'?/^Evidence used/:/^Evidencia utilizada/);
 assert.deepEqual(JSON.parse(nodes[0].props.children),candidate.evidence_used);
 assert.deepEqual(JSON.parse(nodes[1].props.children),candidate.counterevidence);
 assert.deepEqual(JSON.parse(nodes[2].props.children),candidate);
 assert.equal(JSON.parse(nodes[3].props.children).evidence,'literal finding');
});
