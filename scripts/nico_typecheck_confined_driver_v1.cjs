'use strict';
// This trusted wrapper is started only by the private parent bridge.
// The path to the trusted compiler is an argv value set by the bridge;
// repository material is data on stdin, never a path to execute.
const { typecheckWithTrustedCompiler } = require('./nico_typecheck_virtual_host_v1.cjs');
const [compilerEntry] = process.argv.slice(2);
const MAX_WIRE = 48 * 1024 * 1024;
const MAX_DIAGNOSTICS_WIRE = 4 * 1024 * 1024;
const MOUNTS = ['source','generated','dependencies','compilerLibs'];

function must(condition) {
  if (!condition) throw new Error('invalid typecheck request');
}

async function run() {
  must(process.argv.length === 3 && compilerEntry.startsWith('/'));
  let total=0;
  const buffers=[];
  for await (const part of process.stdin) {
    total+=part.byteLength;
    must(total <= MAX_WIRE);
    buffers.push(part);
  }
  let message=JSON.parse(Buffer.concat(buffers,total).toString('utf8'));
  must(message?.protocol === 'nico.typescript.bridge.v1' && /^v24\./u.test(process.version));
  must(message.node_version === process.version);
  must(/^[a-f0-9]{64}$/u.test(message.nonce));
  const ts=require(compilerEntry);
  const mounts = {};
  for (const k of MOUNTS) {
    const rows=message.mounts[k], material=new Map();
    must(Array.isArray(rows) && rows.length<=12000);
    for (const row of rows) {
      must(Array.isArray(row) && row.length === 2 && typeof row[0] === 'string' &&
           typeof row[1] === 'string' && !material.has(row[0]));
      const payload=Buffer.from(row[1],'base64');
      must(payload.toString('base64') === row[1]);
      material.set(row[0],payload);
    }
    mounts[k]=material;
  }
  const {nonce,pin,assessed}=message;
  message=null;
  const result=typecheckWithTrustedCompiler(ts,pin,mounts,assessed);
  const response=JSON.stringify({protocol:'nico.typescript.bridge.v1',nonce,node_version:process.version,
    repository:assessed.repository,commit:assessed.commit,tree:assessed.tree,result});
  must(Buffer.byteLength(response)<=MAX_DIAGNOSTICS_WIRE);
  process.stdout.write(response);
}

run().catch(()=>{ process.exitCode=4; });
