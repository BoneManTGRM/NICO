'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createRequire}=require('node:module');
const {test}=require('node:test');
const root=path.resolve(__dirname,'../..');
const ts=createRequire(path.join(root,'apps/web/package.json'))('typescript');
function load(relative){
  const module={exports:{}};const calls=[];
  const compiled=ts.transpileModule(fs.readFileSync(path.join(root,relative),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(compiled,{module,exports:module.exports,URL,Headers,Response,DOMException,AbortSignal,
    process:{env:{NODE_ENV:'production',NICO_API_URL:'https://backend.invalid'}},
    crypto:require('node:crypto').webcrypto,
    fetch:async(url,init)=>{calls.push({url,init});throw new DOMException('Synthetic upstream deadline','TimeoutError');},
  });
  return{api:module.exports,calls};
}
for(const [relative,segments]of[
  ['apps/web/app/api/nico/[...path]/route.ts',['assessment','comprehensive-run','comprun_synthetic','localized-report','en','pdf']],
  ['apps/web/app/api/nico/assessment/[...path]/route.ts',['comprehensive-run','comprun_synthetic','localized-report','en','pdf']],
])test(relative+' names its single-attempt artifact timeout truthfully',async()=>{
  const {api,calls}=load(relative);
  const response=await api.GET({method:'GET',nextUrl:new URL('https://unit.invalid/api/nico/assessment'),
    headers:new Headers({'x-nico-operator-session':'SYNTHETIC-SESSION','x-request-id':'synthetic-request'}),
    cookies:{get:()=>undefined}}, {params:Promise.resolve({path:segments})});
  assert.equal(response.status,504);assert.equal(calls.length,1);
  const body=await response.json();
  assert.equal(body.detail.code,'assessment_artifact_timeout');
  assert.equal(body.detail.attempts,1);
  assert.equal(body.detail.request_class,'exact-run-artifact');
  assert.equal(body.detail.timeout_ms,240000);
  assert.equal(body.detail.retryable,true);
  assert.doesNotMatch(body.detail.message,/cold-start|retries/);
  assert.match(body.detail.message,/Retry this download/);
});
test('authenticated artifact proxy still refuses an unauthenticated read before fetching',async()=>{
  const {api,calls}=load('apps/web/app/api/nico/assessment/[...path]/route.ts');
  const response=await api.GET({method:'GET',nextUrl:new URL('https://unit.invalid/api/nico/assessment'),
    headers:new Headers(),cookies:{get:()=>undefined}},{params:Promise.resolve({path:['comprehensive-run','comprun_synthetic','localized-report','es-MX','pdf']})});
  assert.equal(response.status,401);assert.equal(calls.length,0);
});
