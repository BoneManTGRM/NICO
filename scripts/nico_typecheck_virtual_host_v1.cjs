'use strict';
/**
 * No sources, config, or dependencies are executed by this module.
 * Trusted strategy must supply an already-loaded pinned TS compiler and exact
 * expected digests from independent, immutable source/build authorities.
 * The caller owns process limits, secure artifact retention, and run semantics.
 */
const crypto = require('node:crypto');
const path = require('node:path').posix;
const { TextDecoder } = require('node:util');

const ROOT = '/project/apps/web';
const COMPILER = '/compiler/lib';
const GENERATED = [
  'cache-life.d.ts', 'root-params.d.ts', 'routes.d.ts', 'validator.ts'
];
const OWNED = 'BoneManTGRM/NICO';
const HISTORICAL_COMMIT = '5eb768b5776f88bae86e972c76267915cc874c85';
const HISTORICAL_TREE = 'fd4170b422a9f623c286e9e1f3c08e01b0ec821c';
const HISTORICAL_PACKAGE = '091a04fa67c7907b98e106fcff8b964e13129754fce72d24f3025b97c4887fa3';
const MAX_BYTES = 128 * 1024 * 1024;
const MAX_FILE = 8 * 1024 * 1024;
const MAX_FILES = 12000;
const SHA = /^[a-f0-9]{64}$/;
const GIT_SHA = /^[a-f0-9]{40}$/;
const Text = new TextDecoder('utf-8', { fatal: true });
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');

function requireThat(value, code) {
  if (!value) throw new Error(code);
}

function safeRelative(relative) {
  return typeof relative === 'string' && relative.length < 1024 &&
      !/[\u0000-\u001f\\]/u.test(relative) &&
      relative.split('/').every(part => part !== '' && part !== '.' && part !== '..');
}

function digestEntries(entries) {
  return hash(JSON.stringify([...entries].sort((a,b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)));
}

function isPlainMapping(value) {
  return value instanceof Map;
}

function admitMounts(pin, mounts) {
  const files = new Map(), dirs = new Map();
  let total = 0;
  function enterDirectory(dir) {
    if (!dirs.has(dir)) {
      dirs.set(dir,{files:new Set(),directories:new Set()});
      if (dir !== '/') {
        const parent=path.dirname(dir);
        enterDirectory(parent);
        dirs.get(parent).directories.add(path.basename(dir));
      }
    }
    return dirs.get(dir);
  }
  const historical = pin.commit === HISTORICAL_COMMIT;
  const expectedGenerated = historical ? [...GENERATED, 'package.json'] : GENERATED;
  if (historical) requireThat(pin.tree === HISTORICAL_TREE, 'typecheck_assessment_identity');
  const rows = [
    ['source', ROOT, n => !n.startsWith('.next/') && !n.startsWith('node_modules/')],
    ['generated', ROOT+'/.next/types', n => expectedGenerated.includes(n)],
    ['dependencies', ROOT+'/node_modules', n => !n.split('/').includes('.bin')],
    ['compilerLibs', COMPILER, n => /^lib(?:\.[\w.-]+)?\.d\.ts$/u.test(n)],
  ];
  for (const [key, prefix, approved] of rows) {
    const mount = mounts[key];
    requireThat(isPlainMapping(mount) && SHA.test(pin.mountDigests[key] || ''), 'typecheck_mount_invalid');
    if (key === 'generated') {
      requireThat(mount.size === expectedGenerated.length && expectedGenerated.every(n => mount.has(n)),
          'typecheck_generated_inputs_missing');
    }
    requireThat(mount.size <= MAX_FILES - files.size, 'typecheck_file_count');
    const manifest = [];
    for (const [relative, bytes] of mount.entries()) {
      requireThat(safeRelative(relative) && approved(relative) && Buffer.isBuffer(bytes),
          'typecheck_mount_path');
      requireThat(bytes.byteLength <= MAX_FILE && bytes.byteLength <= MAX_BYTES-total,
          'typecheck_byte_budget');
      // Copy the bytes into our own immutable text view before hashing or parsing.
      const own = Buffer.from(bytes);
      total += own.byteLength;
      const digest = hash(own);
      const buildPackage = key === 'generated' && relative === 'package.json';
      if (buildPackage) requireThat(digest === HISTORICAL_PACKAGE, 'typecheck_build_metadata_digest');
      const absolute = (buildPackage ? ROOT+'/.next' : prefix) + '/' + relative;
      requireThat(!files.has(absolute), 'typecheck_duplicate_input');
      files.set(absolute,{ text:Text.decode(own), digest });
      enterDirectory(path.dirname(absolute)).files.add(path.basename(absolute));
      manifest.push([relative,digest]);
    }
    requireThat(pin.mountDigests[key] === digestEntries(manifest),'typecheck_mount_digest');
  }
  requireThat([...files.keys()].every(name => !dirs.has(name)), 'typecheck_duplicate_file_and_directory');
  return {files,dirs};
}

function normalize(proposed) {
  if (typeof proposed !== 'string' || !proposed || proposed.length > 4096 ||
      /[\u0000-\u001f\\]/u.test(proposed) || /(^|\/)\.\.($|\/)/u.test(proposed) && !proposed.startsWith('/')) {
    // Only the canonical virtual namespace is exposed. The compiler itself
    // resolves relative modules to absolute virtual candidate paths first.
    return '';
  }
  return path.resolve(ROOT,proposed);
}

function eligibleConfig(config) {
  if (typeof config !== 'object' || config === null || Array.isArray(config)) return false;
  const root_keys = new Set(['compilerOptions','files','include','exclude','compileOnSave']);
  if (!Object.keys(config).every(k => root_keys.has(k))) return false;
  // The exact owned build records false here. Never enable save-time compilation.
  if (Object.hasOwn(config,'compileOnSave') && config.compileOnSave !== false) return false;
  const expected = new Set(['target','lib','allowJs','skipLibCheck','strict','noEmit','esModuleInterop',
    'module','moduleResolution','resolveJsonModule','isolatedModules','jsx','incremental','plugins']);
  if (!config.compilerOptions || !Object.keys(config.compilerOptions).every(k => expected.has(k))) return false;
  const plugins = config.compilerOptions.plugins;
  return plugins === undefined || (Array.isArray(plugins) && plugins.length === 1 &&
      plugins[0] && Object.keys(plugins[0]).length === 1 && plugins[0].name === 'next');
}

function typecheckWithTrustedCompiler(ts, pin, mounts, assessed) {
  requireThat(pin.repository === OWNED && assessed.repository === pin.repository
      && GIT_SHA.test(pin.commit || '') && GIT_SHA.test(pin.tree || '')
      && pin.commit === assessed.commit && pin.tree === assessed.tree,
      'typecheck_assessment_identity');
  requireThat(typeof pin.compilerVersion === 'string' && ts.version === pin.compilerVersion,
      'typecheck_compiler_pin');
  const {files,dirs} = admitMounts(pin,mounts);
  const reads = new Map();
  const sortedNames = seq => [...seq].sort();
  const readFile = name => {
    const normalized=normalize(name), file = files.get(normalized);
    if (file) {
      reads.set(normalized,file.digest);
      return file.text;
    }
    return undefined;
  };
  const directoryExists = name => dirs.has(normalize(name));
  const fileExists = name => files.has(normalize(name));
  const entries = name => {
    const listing=dirs.get(normalize(name));
    return listing ? {files:sortedNames(listing.files),directories:sortedNames(listing.directories)}
      : {files:[],directories:[]};
  };
  const readDirectory = (directory, extensions, exclude, include, depth) =>
    ts.matchFiles(normalize(directory),extensions,exclude,include,true,ROOT,depth,entries,normalize);
  const hostBase = {
    readFile, fileExists, directoryExists, readDirectory,
    getDirectories: name => entries(name).directories,
    realpath: normalize,
    getCurrentDirectory: () => ROOT,
    getNewLine: () => '\n',
    getEnvironmentVariable: () => '',
  };
  const parsedConfig = ts.readConfigFile(ROOT+'/tsconfig.json', readFile);
  requireThat(!parsedConfig.error && eligibleConfig(parsedConfig.config), 'typecheck_config_unsupported');
  const config = {...parsedConfig.config, compilerOptions:{...parsedConfig.config.compilerOptions}};
  // use the reviewed semantic settings; never load a language service plugin
  delete config.compilerOptions.plugins;
  const parsed = ts.parseJsonConfigFileContent(config,{...hostBase,useCaseSensitiveFileNames:true},
     ROOT,undefined,ROOT+'/tsconfig.json');
  requireThat(parsed.errors.length === 0 && parsed.fileNames.length > 0,
      'typecheck_config_or_roots_incomplete');
  requireThat(parsed.fileNames.every(n => normalize(n).startsWith(ROOT+'/') && files.has(normalize(n))),
      'typecheck_root_outside_inventory');
  const options = {...parsed.options,noEmit:true,incremental:false};
  const host = {
    ...hostBase, useCaseSensitiveFileNames: () => true, getCanonicalFileName:normalize,
    getDefaultLibFileName: opts => COMPILER+'/'+ts.getDefaultLibFileName(opts),
    getDefaultLibLocation: () => COMPILER,
    getSourceFile: (name, language) => {
      const text=readFile(name);
      return text === undefined ? undefined : ts.createSourceFile(normalize(name),text,language,true);
    },
    writeFile: () => {throw new Error('typecheck_emission_forbidden');},
  };
  const program = ts.createProgram(parsed.fileNames,options,host);
  const programInputs = program.getSourceFiles().map(f => normalize(f.fileName)).sort();
  requireThat(programInputs.length > 0 && programInputs.every(n => reads.has(n)),
      'typecheck_actual_program_input_not_captured');
  requireThat(GENERATED.every(n => programInputs.includes(ROOT+'/.next/types/'+n)),
      'typecheck_generated_inputs_not_in_program');
  const raw = ts.getPreEmitDiagnostics(program);
  requireThat(raw.length <= 20000,'typecheck_diagnostic_budget');
  const diagnostics = [];
  let outputBytes=0;
  for (const d of raw) {
    const message=ts.flattenDiagnosticMessageText(d.messageText,'\n');
    outputBytes += Buffer.byteLength(message);
    requireThat(outputBytes <= 2*1024*1024,'typecheck_diagnostic_budget');
    diagnostics.push({code:d.code, category:ts.DiagnosticCategory[d.category],
      file:d.file ? normalize(d.file.fileName) : null, start:d.start ?? null,
      length:d.length ?? null, message});
  }
  return {compiler_version:ts.version, diagnostics, roots:parsed.fileNames,
    program_inputs:programInputs, read_inputs:Object.fromEntries(reads)};
}

module.exports={typecheckWithTrustedCompiler,digestEntries};
