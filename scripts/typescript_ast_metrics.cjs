#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function loadTypeScript() {
  const candidates = [
    process.env.NICO_TYPESCRIPT_MODULE,
    path.resolve(process.cwd(), "apps/web/node_modules/typescript/lib/typescript.js"),
    path.resolve(process.cwd(), "node_modules/typescript/lib/typescript.js"),
    "typescript",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // Continue to the next bounded local module location.
    }
  }
  return null;
}

function readInput() {
  const raw = fs.readFileSync(0, "utf8");
  const payload = JSON.parse(raw || "{}");
  return payload && typeof payload === "object" ? payload : {};
}

function scriptKind(ts, filename) {
  if (filename.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (filename.endsWith(".jsx")) return ts.ScriptKind.JSX;
  if (filename.endsWith(".js")) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

function grade(value) {
  if (value <= 5) return "A";
  if (value <= 10) return "B";
  if (value <= 20) return "C";
  if (value <= 30) return "D";
  if (value <= 40) return "E";
  return "F";
}

function nodeName(ts, node, sourceFile) {
  if (node.name && typeof node.name.getText === "function") return node.name.getText(sourceFile);
  if (ts.isConstructorDeclaration(node)) return "constructor";
  if (ts.isArrowFunction(node)) return "<arrow>";
  if (ts.isFunctionExpression(node)) return "<function-expression>";
  return "<anonymous>";
}

function isFunctionLike(ts, node) {
  return ts.isFunctionDeclaration(node)
    || ts.isMethodDeclaration(node)
    || ts.isConstructorDeclaration(node)
    || ts.isArrowFunction(node)
    || ts.isFunctionExpression(node)
    || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node);
}

function isDecision(ts, node) {
  return ts.isIfStatement(node)
    || ts.isForStatement(node)
    || ts.isForInStatement(node)
    || ts.isForOfStatement(node)
    || ts.isWhileStatement(node)
    || ts.isDoStatement(node)
    || ts.isCaseClause(node)
    || ts.isCatchClause(node)
    || ts.isConditionalExpression(node);
}

function isLogicalDecision(ts, node) {
  return ts.isBinaryExpression(node)
    && [
      ts.SyntaxKind.AmpersandAmpersandToken,
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
    ].includes(node.operatorToken.kind);
}

function functionMetrics(ts, node, sourceFile) {
  let cyclomatic = 1;
  let cognitive = 0;
  let nesting = 0;
  let maxNesting = 0;

  function visit(current, depth) {
    if (current !== node && isFunctionLike(ts, current)) return;
    const decision = isDecision(ts, current);
    const logical = isLogicalDecision(ts, current);
    if (decision || logical) {
      cyclomatic += 1;
      cognitive += 1 + (decision ? depth : 0);
    }
    const nextDepth = decision ? depth + 1 : depth;
    if (decision) {
      nesting = nextDepth;
      maxNesting = Math.max(maxNesting, nesting);
    }
    ts.forEachChild(current, (child) => visit(child, nextDepth));
  }

  visit(node, 0);
  const start = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  const end = sourceFile.getLineAndCharacterOfPosition(node.getEnd());
  const line = start.line + 1;
  const endLine = end.line + 1;
  const nestedRanges = [];
  function collectNestedRanges(current) {
    if (current !== node && isFunctionLike(ts, current)) {
      const nestedStart = sourceFile.getLineAndCharacterOfPosition(current.getStart(sourceFile)).line + 1;
      const nestedEnd = sourceFile.getLineAndCharacterOfPosition(current.getEnd()).line + 1;
      nestedRanges.push([nestedStart, nestedEnd]);
      return;
    }
    ts.forEachChild(current, collectNestedRanges);
  }
  collectNestedRanges(node);
  const excludedLines = new Set();
  for (const [nestedStart, nestedEnd] of nestedRanges) {
    for (let currentLine = nestedStart; currentLine <= nestedEnd; currentLine += 1) excludedLines.add(currentLine);
  }
  const spanLoc = Math.max(1, endLine - line + 1);
  const residualLoc = Math.max(1, spanLoc - [...excludedLines].filter((value) => value >= line && value <= endLine).length);
  return {
    path: sourceFile.fileName,
    name: nodeName(ts, node, sourceFile),
    line,
    end_line: endLine,
    loc: residualLoc,
    span_loc: spanLoc,
    loc_method: "function_residual_physical_lines_excluding_nested_functions_v2",
    cyclomatic_complexity: cyclomatic,
    cognitive_complexity: cognitive,
    grade: grade(cyclomatic),
    max_nesting: maxNesting,
    language: "javascript-typescript",
    method: "typescript_compiler_ast",
  };
}

function importsFor(ts, sourceFile) {
  const imports = [];
  for (const statement of sourceFile.statements) {
    if ((ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement))
      && statement.moduleSpecifier
      && ts.isStringLiteral(statement.moduleSpecifier)) {
      imports.push(statement.moduleSpecifier.text);
    }
    if (ts.isImportEqualsDeclaration(statement)
      && statement.moduleReference
      && ts.isExternalModuleReference(statement.moduleReference)
      && statement.moduleReference.expression
      && ts.isStringLiteral(statement.moduleReference.expression)) {
      imports.push(statement.moduleReference.expression.text);
    }
  }
  return [...new Set(imports)];
}

function candidateTargets(currentPath, specifier) {
  if (!specifier.startsWith(".")) return [];
  const base = path.posix.normalize(path.posix.join(path.posix.dirname(currentPath), specifier));
  return [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    `${base}.js`,
    `${base}.jsx`,
    `${base}/index.ts`,
    `${base}/index.tsx`,
    `${base}/index.js`,
    `${base}/index.jsx`,
  ];
}

function stronglyConnectedComponents(graph) {
  let index = 0;
  const stack = [];
  const onStack = new Set();
  const indexes = new Map();
  const lowlinks = new Map();
  const components = [];

  function connect(node) {
    indexes.set(node, index);
    lowlinks.set(node, index);
    index += 1;
    stack.push(node);
    onStack.add(node);

    for (const next of graph.get(node) || []) {
      if (!indexes.has(next)) {
        connect(next);
        lowlinks.set(node, Math.min(lowlinks.get(node), lowlinks.get(next)));
      } else if (onStack.has(next)) {
        lowlinks.set(node, Math.min(lowlinks.get(node), indexes.get(next)));
      }
    }

    if (lowlinks.get(node) === indexes.get(node)) {
      const component = [];
      while (stack.length) {
        const item = stack.pop();
        onStack.delete(item);
        component.push(item);
        if (item === node) break;
      }
      components.push(component.sort());
    }
  }

  for (const node of graph.keys()) {
    if (!indexes.has(node)) connect(node);
  }
  return components;
}

function main() {
  const ts = loadTypeScript();
  if (!ts) {
    process.stdout.write(JSON.stringify({
      status: "unavailable",
      reason: "typescript_compiler_module_not_available",
      analyses: [],
    }));
    return;
  }

  const payload = readInput();
  const files = payload.files && typeof payload.files === "object" ? payload.files : {};
  const fileNames = new Set(Object.keys(files));
  const analyses = [];
  const graph = new Map();
  const parseFailures = [];

  for (const [filename, textValue] of Object.entries(files)) {
    const text = String(textValue || "");
    const sourceFile = ts.createSourceFile(
      filename,
      text,
      ts.ScriptTarget.Latest,
      true,
      scriptKind(ts, filename),
    );
    const diagnostics = sourceFile.parseDiagnostics || [];
    if (diagnostics.length) {
      parseFailures.push({path: filename, count: diagnostics.length});
    }

    const functions = [];
    let classes = 0;
    function walk(node) {
      if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) classes += 1;
      if (isFunctionLike(ts, node)) functions.push(functionMetrics(ts, node, sourceFile));
      ts.forEachChild(node, walk);
    }
    walk(sourceFile);

    const imports = importsFor(ts, sourceFile);
    const internal = new Set();
    for (const specifier of imports) {
      for (const candidate of candidateTargets(filename, specifier)) {
        if (fileNames.has(candidate)) {
          internal.add(candidate);
          break;
        }
      }
    }
    graph.set(filename, internal);
    analyses.push({
      status: diagnostics.length ? "analyzed_with_diagnostics" : "analyzed",
      path: filename,
      language: "javascript-typescript",
      source_loc: text.split(/\r?\n/).filter((line) => line.trim()).length,
      functions,
      declared_function_count: functions.length,
      classes,
      imports,
      internal_imports: [...internal].sort(),
      fan_out: imports.length,
      internal_fan_out: internal.size,
      method: "typescript_compiler_ast",
      parser_diagnostic_count: diagnostics.length,
    });
  }

  const fanIn = new Map([...graph.keys()].map((name) => [name, 0]));
  for (const targets of graph.values()) {
    for (const target of targets) fanIn.set(target, (fanIn.get(target) || 0) + 1);
  }
  for (const analysis of analyses) analysis.fan_in = fanIn.get(analysis.path) || 0;

  const components = stronglyConnectedComponents(graph);
  const cycles = components.filter((component) => component.length > 1);
  process.stdout.write(JSON.stringify({
    status: "complete",
    parser: "typescript_compiler_api",
    parser_version: String(ts.version || "unknown"),
    analyses,
    parse_failures: parseFailures,
    import_graph: {
      nodes: graph.size,
      edges: [...graph.values()].reduce((total, targets) => total + targets.size, 0),
      strongly_connected_components: components.length,
      cyclic_components: cycles,
      files_in_cycles: [...new Set(cycles.flat())].sort(),
    },
  }));
}

try {
  main();
} catch (error) {
  process.stdout.write(JSON.stringify({
    status: "failed",
    reason: error && error.name ? error.name : "typescript_ast_failure",
    message: error && error.message ? String(error.message).slice(0, 1000) : "",
    analyses: [],
  }));
  process.exitCode = 1;
}
