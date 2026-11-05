'use strict';
// NICO's own authorized CI build only. Never a generic customer-code worker.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const PIN = '6.0.3';
const REQUIRED = ['routes.d.ts', 'root-params.d.ts'];
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function collectProject(root, compilerRoot) {
  const output = {schema:'nico.ci-typescript.v1', status:'incomplete', clean:false, diagnostics:[], diagnostics_text:''};
  try {
    root=fs.realpathSync(root); const web=path.join(root,'apps/web');
    compilerRoot=fs.realpathSync(compilerRoot);
    const inputs=new Map(); let total=0;
    function read(file) {
      const absolute=path.resolve(file);
      if (!fs.existsSync(absolute)) return undefined;
      if (fs.realpathSync(absolute)!==absolute || !fs.statSync(absolute).isFile()) throw Error('input_symlink_or_nonregular');
      if (!(absolute.startsWith(root+path.sep)||absolute.startsWith(compilerRoot+path.sep))) throw Error('input_outside_build_boundary');
      const size=fs.statSync(absolute).size;
      if(size>128*1024*1024 || (!inputs.has(absolute) && (inputs.size>=10000 || total+size>128*1024*1024))) throw Error('input_capture_budget');
      const bytes=fs.readFileSync(absolute);
      if (!inputs.has(absolute)) total+=bytes.length;
      if (inputs.size>10000 || total>128*1024*1024) throw Error('input_capture_budget');
      const sha256=hash(bytes);
      if (inputs.has(absolute)&&inputs.get(absolute)!==sha256) throw Error('input_changed_during_check');
      inputs.set(absolute,sha256);
      return bytes.toString('utf8');
    }
    const label=file => file.startsWith(compilerRoot+path.sep) ? '@compiler/'+path.relative(compilerRoot,file).split(path.sep).join('/') : path.relative(root,file).split(path.sep).join('/');
    const lockPath=path.join(web,'package-lock.json'); const lock=JSON.parse(read(lockPath));
    const compilerPackage=path.join(compilerRoot,'package.json'); const compilerEntry=path.join(compilerRoot,'lib/typescript.js');
    const metadata=JSON.parse(read(compilerPackage)); read(compilerEntry);
    if (metadata.name!=='typescript'||metadata.version!==PIN||lock.packages?.['node_modules/typescript']?.version!==PIN) throw Error('compiler_pin_mismatch');
    const ts=require(compilerEntry);
    if(ts.version!==PIN) throw Error('compiler_runtime_version_mismatch');
    output.compiler={version:ts.version,package_sha256:inputs.get(compilerPackage),entry_sha256:inputs.get(compilerEntry),node_version:process.version,node_sha256:hash(fs.readFileSync(process.execPath))};
    output.lockfile_sha256=inputs.get(lockPath);
    const generatedRoot=path.join(web,'.next/types'); const generated=[];
    function walk(directory) {
      if(fs.realpathSync(directory)!==directory) throw Error('generated_directory_symlink');
      for(const name of fs.readdirSync(directory).sort()) {
        const file=path.join(directory,name); const stat=fs.lstatSync(file);
        if(stat.isSymbolicLink()) throw Error('generated_input_symlink');
        if(stat.isDirectory()) walk(file);
        else if(stat.isFile()) { read(file); generated.push({path:label(file),sha256:inputs.get(file)}); }
        else throw Error('generated_input_nonregular');
        if(generated.length>5000) throw Error('generated_population_budget');
      }
    }
    for(const name of REQUIRED) if(!fs.existsSync(path.join(generatedRoot,name))) throw Error('required_generated_input_missing:'+name);
    walk(generatedRoot); output.generated_inputs=generated;
    const configPath=path.join(web,'tsconfig.json'); const config=ts.readConfigFile(configPath,read);
    output.configuration_sha256=inputs.get(configPath);
    const diagnostic=d=>({code:d.code,category:ts.DiagnosticCategory[d.category],file:d.file?label(d.file.fileName):null,
      start:d.start??null,length:d.length??null,message:ts.flattenDiagnosticMessageText(d.messageText,'\n'),related:(d.relatedInformation||[]).map(diagnostic)});
    if(config.error) { output.diagnostics=[diagnostic(config.error)]; throw Error('configuration_parse_failed'); }
    output.raw_configuration=config.config;
    const parsed=ts.parseJsonConfigFileContent(config.config,{...ts.sys,readFile:read},web,undefined,configPath);
    if(parsed.errors.length) { output.diagnostics=parsed.errors.map(diagnostic); throw Error('configuration_incomplete'); }
    const options={...parsed.options,noEmit:true,incremental:false};
    output.effective_configuration=options;
    output.configuration_limitations={declaration_semantics_checked:!Boolean(options.skipLibCheck),
      javascript_semantics_checked:Boolean(options.checkJs),strict_mode:Boolean(options.strict),
      scope:'TypeScript diagnostics under the retained project configuration; not runtime or exhaustive semantic verification'};
    const host=ts.createCompilerHost(options); host.readFile=read;
    host.writeFile=()=>{throw Error('emission_forbidden');};
    const program=ts.createProgram(parsed.fileNames,options,host);
    const diagnostics=ts.getPreEmitDiagnostics(program);
    output.diagnostics=diagnostics.map(diagnostic);
    output.diagnostics_text=ts.formatDiagnostics(diagnostics,{getCanonicalFileName:f=>label(f),getCurrentDirectory:()=>web,getNewLine:()=> '\n'});
    output.program_inputs=program.getSourceFiles().map(file=>({path:label(file.fileName),sha256:inputs.get(file.fileName),declaration:file.isDeclarationFile}));
    if(!output.program_inputs.length||output.program_inputs.some(row=>!row.sha256)) throw Error('program_input_capture_incomplete');
    for(const file of inputs.keys()) read(file);
    output.read_inputs=[...inputs].map(([file,sha256])=>({path:label(file),sha256})).sort((a,b)=>a.path.localeCompare(b.path));
    output.root_inputs=parsed.fileNames.map(label).sort();
    output.status='completed'; output.clean=!diagnostics.some(d=>d.category===ts.DiagnosticCategory.Error);
    output.capture_complete=true; output.emitted_files=0;
  } catch(error) {output.reason=error.message; output.capture_complete=false;}
  return output;
}
module.exports={collectProject};
if(require.main===module) {
  const root=path.resolve(__dirname,'..');
  const output=collectProject(root,path.join(root,'apps/web/node_modules/typescript'));
  const text=JSON.stringify(output);
  if(Buffer.byteLength(text)>8*1024*1024) {process.stdout.write(text.slice(0,8*1024*1024)); process.exitCode=3;}
  else {process.stdout.write(text); process.exitCode=output.status!=='completed'?3:output.clean?0:1;}
}
