'use strict';
// CSS constraint checks, not a browser layout/visual qualification.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=process.env.NICO_SOURCE_ROOT||path.resolve(__dirname,'../..');
const web=createRequire(path.resolve(__dirname,'../../apps/web/package.json'));
const css=web('postcss').parse(fs.readFileSync(path.join(root,'apps/web/app/operations/reviewer-queue/review-browser.module.css'),'utf8'));
function declarations(selector,viewport){
 const result={};
 css.walkRules(rule=>{
  if(!rule.selectors.includes(selector))return;
  for(let p=rule.parent;p&&p.type!=='root';p=p.parent){
   if(p.type==='atrule'&&p.name==='media'){
    const limits=[...p.params.matchAll(/(min|max)-width\s*:\s*(\d+)px/g)];
    assert.ok(limits.length,`unsupported media query ${p.params}`);
    if(limits.some(([,kind,n])=>kind==='max'?viewport>+n:viewport<+n))return;
   }
  }
  rule.walkDecls(d=>{result[d.prop]=d.value;});
 });return result;
}
function sides(value){const parts=value.split(/\s+/).map(parseFloat);return parts.length===1?2*parts[0]:2*parts[1];}
function constraints(viewport){
 const panel=declarations('.panel',viewport),grid=declarations('.sampling',viewport);
 const panelBorder=2*parseFloat(panel.border),gridBorder=2*parseFloat(grid.border);
 const margin=panel.margin.includes('auto')?0:sides(panel.margin);
 const available=Math.min(viewport-margin,parseFloat(panel['max-width']))-sides(panel.padding)-panelBorder-sides(grid.padding)-gridBorder;
 const expanded=grid['grid-template-columns'].replace(/repeat\((\d+),\s*(minmax\([^)]*\))\)/g,(_,n,track)=>Array(+n).fill(track).join(' '));
 const tracks=expanded.match(/minmax\([^)]*\)|[\d.]+fr/g);
 assert.ok(tracks?.length,`unknown tracks ${expanded}`);
 const minimum=tracks.reduce((sum,track)=>sum+(track.startsWith('minmax')?parseFloat(track.slice(7)):0),0)+(+parseFloat(grid.gap))*(tracks.length-1);
 return {available,minimum,count:tracks.length};
}
for(const viewport of [320,390,759.5,760,760.01,760.5,761,800,837,838,899.5,900,900.5,901,1024,1280,1440,1920]){
 test(`${viewport}px: sampling tracks fit the panel content box`,()=>{
  const {available,minimum,count}=constraints(viewport);
  assert.ok(minimum<=available,`minimum tracks ${minimum}px exceed available ${available}px`);
  if(viewport<=760)assert.equal(count,1,'preserve mobile stack');
  if(viewport>900)assert.equal(count,4,'preserve wide desktop proportions');
  if(viewport>760&&viewport<=900)assert.equal(count,2,'intermediate widths have no breakpoint gap');
 });
}
test('long bilingual content and native controls can shrink inside their grid cells',()=>{
 for(const width of [390,800,1280]){
  const child=declarations('.sampling > *',width);
  assert.equal(child['min-width'],'0');
  assert.equal(child['overflow-wrap'],'anywhere');
  for(const selector of ['.sampling input','.sampling select']){
   const control=declarations(selector,width);
   assert.equal(control['min-width'],'0');
   assert.equal(control.width,'100%');
   assert.equal(control['max-width'],'100%');
  }
 }
});
