'use strict';
// LOCAL PROTOTYPE ONLY. No production scanner imports this module.
// The caller must own synthetic inputs, or separately establish OS isolation.
// A CompilerHost is a data boundary, not an OS security boundary.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const VERSION = 'nico.trusted-typescript.prototype.v1';
const ROOT = '/__nico_source__';
const LIB = '/__nico_libraries__';
const LIMITS = Object.freeze({files: 256, sourceBytes: 2 * 1024 * 1024, librariesBytes: 16 * 1024 * 1024});
function stable(x) {
  if (Array.isArray(x)) return '[' + x.map(stable).join(',') + ']';
  if (x !== null && typeof x === 'object') return '{' + Object.keys(x).sort().map(k => JSON.stringify(k)+':'+stable(x[k])).join(',') + '}';
  return JSON.stringify(x);
}
function hash(x) { return crypto.createHash('sha256').update(x).digest('hex'); }
function digest(x) { return hash(stable(x)); }
function fail(message) { throw new Error(message); }
function regular(p) {
  // An absolute operator-selected installation, not a manifest-selected path.
  if (!path.isAbsolute(p) || fs.realpathSync(p) !== p || !fs.lstatSync(p).isFile()) fail('trusted_tool_symlink_or_nonregular');
  return fs.readFileSync(p);
}
function createTrustedRunner(compilerRoot, expected) {
  // Expected digests are controller trust anchors, not fields of target input.
  const packageBytes = regular(path.join(compilerRoot, 'package.json'));
  const compilerPath = path.join(compilerRoot, 'lib/typescript.js');
  const compilerBytes = regular(compilerPath);
  const metadata = JSON.parse(packageBytes);
  const libraries = new Map();
  const libraryHashes = {};
  let libraryBytes = 0;
  for (const name of fs.readdirSync(path.join(compilerRoot, 'lib')).filter(n => /^lib.*\.d\.ts$/.test(n)).sort()) {
    const raw = regular(path.join(compilerRoot, 'lib', name));
    libraryBytes += raw.length;
    if (libraryBytes > LIMITS.librariesBytes) fail('trusted_library_budget');
    libraries.set(LIB + '/' + name, new TextDecoder('utf-8', {fatal: true}).decode(raw));
    libraryHashes[name] = hash(raw);
  }
  const actual = {package_sha256: hash(packageBytes), compiler_sha256: hash(compilerBytes), libraries_sha256: digest(libraryHashes)};
  if (metadata.name !== 'typescript' || metadata.version !== '6.0.3' || stable(actual) !== stable(expected) || !libraries.size) fail('trusted_compiler_identity_mismatch');
  // Evaluate precisely the verified image-owned bytes, with no package resolution.
  // Never evaluate any manifest text. TypeScript's trusted internal Node requires
  // are allowed; the compiler's filesystem host below is entirely replaced.
  const Module = require('node:module');
  const loaded = new Module(compilerPath, module);
  loaded.filename = compilerPath;
  loaded.paths = [];
  loaded._compile(compilerBytes.toString('utf8'), compilerPath);
  const ts = loaded.exports;
  if (ts.version !== metadata.version) fail('trusted_compiler_runtime_mismatch');
  const compiler = Object.freeze({version: ts.version, ...actual});

  return function run(request) {
    let diagnostics = [];
    const closureFailures = new Set();
    const readPaths = new Set();
    let receipt = null;
    try {
      const manifest = request.manifest;
      if (!manifest || manifest.schema !== 'nico.typescript.frozen-input.v1' || request.manifest_sha256 !== digest(manifest)) fail('manifest_digest_or_schema');
      const id = manifest.identity;
      if (!id || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(id.repository) || !/^[a-f0-9]{40}$/.test(id.commit_sha)
          || !/^[A-Za-z0-9_-]{1,128}$/.test(id.run_id) || !/^[A-Za-z0-9_-]{1,128}$/.test(id.snapshot_id)) fail('source_identity_invalid');
      if (!Array.isArray(manifest.files) || manifest.files.length > LIMITS.files) fail('source_file_budget');
      const files = new Map(libraries);
      let bytes = 0;
      const sourceRows = new Map();
      for (const row of manifest.files) {
        const name = row.path;
        if (typeof name !== 'string' || name.length > 512 || !name.split('/').every(p => /^[A-Za-z0-9_.@-]+$/.test(p) && !['.', '..', '.git', '__proto__'].includes(p))) fail('source_path_boundary');
        if (!['source', 'config'].includes(row.kind)) fail('offline_bundle_verification_unimplemented');
        if (name.split('/').includes('node_modules') || name.split('/').includes('.next')) fail('offline_bundle_verification_unimplemented');
        if (Object.keys(row).some(k => !['path', 'text', 'sha256', 'kind'].includes(k))) fail('source_row_schema');
        if (typeof row.text !== 'string' || hash(Buffer.from(row.text, 'utf8')) !== row.sha256) fail('source_digest');
        if ((row.kind === 'source' && !/\.(?:[cm]?tsx?|jsx?)$/.test(name)) || (row.kind === 'config' && !name.endsWith('.json'))) fail('source_kind');
        bytes += Buffer.byteLength(row.text);
        if (bytes > LIMITS.sourceBytes) fail('source_byte_budget');
        const key = ROOT + '/' + name;
        if (files.has(key)) fail('duplicate_input');
        files.set(key, row.text);
        sourceRows.set(key, row);
      }
      const configPath = ROOT + '/' + manifest.config;
      if (sourceRows.get(configPath)?.kind !== 'config') fail('config_not_in_manifest');
      const display = p => p?.startsWith(ROOT + '/') ? p.slice(ROOT.length + 1) : p;
      const normalizeDiagnostic = d => ({code: d.code, category: ts.DiagnosticCategory[d.category],
        file: display(d.file?.fileName) || null, start: d.start ?? null, length: d.length ?? null,
        message: ts.flattenDiagnosticMessageText(d.messageText, '\n'),
        related: (d.relatedInformation || []).map(normalizeDiagnostic)});
      const config = ts.parseConfigFileTextToJson(configPath, files.get(configPath));
      if (config.error) {
        diagnostics = [normalizeDiagnostic(config.error)];
        fail('config_parse_failed');
      }
      const raw = config.config;
      if (!raw || typeof raw !== 'object' || Array.isArray(raw) || raw.extends || raw.references?.length) fail('unsupported_configuration_closure');
      const opts = raw.compilerOptions || {};
      if (opts.plugins?.length || opts.noCheck || opts.noResolve || opts.skipLibCheck || opts.skipDefaultLibCheck
          || opts.types?.length || opts.typeRoots?.length || opts.libReplacement) fail('unsupported_configuration_closure');
      if ([...sourceRows.keys()].some(p => /\.[cm]?jsx?$/.test(p)) && (!opts.allowJs || !opts.checkJs)) fail('unchecked_javascript_population');
      // All reads, including module/config/lib resolution, are immutable map lookups.
      // Directory entries are virtual; no fallback to ts.sys or the host filesystem.
      const directories = new Set([ROOT, LIB]);
      for (const key of files.keys()) {
        let p = path.posix.dirname(key);
        while (p !== '/' && p !== '.') { directories.add(p); p = path.posix.dirname(p); }
      }
      const canonical = p => path.posix.normalize(p);
      const read = p => {
        p = canonical(p);
        if (files.has(p)) readPaths.add(p);
        return files.get(p);
      };
      const exists = p => files.has(canonical(p));
      const entries = p => ({files: [...files.keys()].filter(k => path.posix.dirname(k) === p).map(k => path.posix.basename(k)),
        directories: [...directories].filter(k => path.posix.dirname(k) === p).map(k => path.posix.basename(k))});
      const configHost = {useCaseSensitiveFileNames: true, fileExists: exists, readFile: read,
        readDirectory: (p, ext, exclude, include, depth) => ts.matchFiles(p, ext, exclude, include, true, ROOT, depth, entries, canonical)};
      const parsed = ts.parseJsonConfigFileContent(raw, configHost, ROOT, undefined, configPath);
      diagnostics = parsed.errors.map(normalizeDiagnostic);
      if (diagnostics.length) fail('config_diagnostics');
      if (!parsed.fileNames.length) fail('empty_source_population');
      const options = {...parsed.options, noEmit: true, incremental: false, composite: false,
        noCheck: false, noResolve: false, types: [], noUncheckedSideEffectImports: true};
      // Reject options that could suppress missing-input checks or change resolution
      // to unsupported facilities, rather than manufacturing a complete result.
      if (parsed.options.noLib || parsed.options.noResolve || parsed.options.noCheck) fail('unsupported_configuration_closure');
      const host = {
        getSourceFile: (name, languageVersion, onError) => {
          const text = read(name);
          return text === undefined ? undefined : ts.createSourceFile(canonical(name), text, languageVersion, true);
        },
        getDefaultLibFileName: o => LIB + '/' + ts.getDefaultLibFileName(o),
        getDefaultLibLocation: () => LIB,
        writeFile: () => fail('emission_forbidden'),
        getCurrentDirectory: () => ROOT,
        getDirectories: p => entries(canonical(p)).directories,
        directoryExists: p => directories.has(canonical(p)),
        fileExists: exists, readFile: read,
        getCanonicalFileName: canonical, useCaseSensitiveFileNames: () => true,
        getNewLine: () => '\n', realpath: canonical,
      };
      // Preflight every imported module, including side-effect-only imports, so
      // missing generated/dependency input cannot disappear under loose options.
      for (const [name, row] of sourceRows) {
        if (row.kind !== 'source') continue;
        const syntax = ts.createSourceFile(name, row.text, ts.ScriptTarget.Latest, true);
        const visit = node => {
          if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword
              || (ts.isIdentifier(node.expression) && node.expression.text === 'require'))
              && (node.arguments.length !== 1 || !ts.isStringLiteralLike(node.arguments[0]))) {
            closureFailures.add('unsupported_dynamic_dependency:' + display(name));
          }
          ts.forEachChild(node, visit);
        };
        visit(syntax);
        const info = ts.preProcessFile(row.text, true, true);
        for (const imported of info.importedFiles) {
          if (!ts.resolveModuleName(imported.fileName, name, options, host).resolvedModule) closureFailures.add('unresolved_module:' + display(name) + ':' + imported.fileName);
        }
        for (const ref of info.referencedFiles) {
          const target = canonical(path.posix.join(path.posix.dirname(name), ref.fileName));
          if (!exists(target)) closureFailures.add('unresolved_reference:' + display(name) + ':' + ref.fileName);
        }
        for (const ref of info.typeReferenceDirectives) closureFailures.add('unverified_type_dependency:' + ref.fileName);
        for (const ref of info.libReferenceDirectives) {
          if (!libraries.has(LIB + '/lib.' + ref.fileName.toLowerCase() + '.d.ts')) {
            closureFailures.add('unverified_compiler_library:' + ref.fileName);
          }
        }
      }
      const program = ts.createProgram(parsed.fileNames, options, host);
      diagnostics = ts.getPreEmitDiagnostics(program).map(normalizeDiagnostic);
      for (const d of diagnostics) {
        if ([2307, 2688, 2726, 6053, 6305, 7016, 2318].includes(d.code)) closureFailures.add('missing_input_diagnostic:TS' + d.code);
      }
      const complete = closureFailures.size === 0;
      const result = {schema: VERSION, status: complete ? 'complete' : 'incomplete',
        clean: complete && diagnostics.length === 0, diagnostics, findings: diagnostics,
        closure_failures: [...closureFailures].sort()};
      receipt = {schema: VERSION, identity: {...id}, manifest_sha256: request.manifest_sha256,
        compiler, effective_options: options, configuration_sha256: sourceRows.get(configPath).sha256,
        root_files: parsed.fileNames.map(display).sort(), read_files: [...readPaths].sort().map(display),
        read_input_sha256: digest([...readPaths].sort().map(p => [p, hash(Buffer.from(files.get(p)))])),
        diagnostics_sha256: digest(diagnostics), result_sha256: digest(result), emitted_files: 0,
        os_isolation_verified: false, qualified_for_production: false};
      receipt.receipt_sha256 = digest(receipt);
      return {...result, receipt};
    } catch (error) {
      return {schema: VERSION, status: 'incomplete', clean: false, reason: error.message,
        diagnostics, findings: diagnostics, closure_failures: [...closureFailures].sort(), receipt};
    }
  };
}
module.exports = {createTrustedRunner, LIMITS};
