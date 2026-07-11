from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any

SOURCE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx")
TEST_PATH_MARKERS = ("/test/", "/tests/", "test_", "_test.", ".test.", ".spec.")
MIN_DUPLICATE_WINDOW = 6
MAX_DUPLICATE_SAMPLES = 20
MAX_HOTSPOTS = 25


def _is_source_path(path: str) -> bool:
    lowered = f"/{path.lower()}"
    if not path.lower().endswith(SOURCE_SUFFIXES):
        return False
    if any(marker in lowered for marker in TEST_PATH_MARKERS):
        return False
    if any(part in lowered for part in ("/node_modules/", "/dist/", "/build/", "/.next/", "/vendor/")):
        return False
    if lowered.endswith((".min.js", ".min.css")):
        return False
    return True


def _grade(complexity: int) -> str:
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    if complexity <= 30:
        return "D"
    if complexity <= 40:
        return "E"
    return "F"


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


class _FunctionComplexityVisitor(ast.NodeVisitor):
    def __init__(self, root: ast.AST) -> None:
        self.root = root
        self.complexity = 1
        self.current_nesting = 0
        self.max_nesting = 0

    def _nested_visit(self, node: ast.AST, increment: int = 1) -> None:
        self.complexity += increment
        self.current_nesting += 1
        self.max_nesting = max(self.max_nesting, self.current_nesting)
        self.generic_visit(node)
        self.current_nesting -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self._nested_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._nested_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._nested_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._nested_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._nested_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        increment = max(1, len(node.handlers))
        self._nested_visit(node, increment=increment)

    def visit_Match(self, node: ast.Match) -> None:
        increment = max(1, len(node.cases))
        self._nested_visit(node, increment=increment)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.complexity += 1 + len(node.ifs)
        self.current_nesting += 1
        self.max_nesting = max(self.max_nesting, self.current_nesting)
        self.generic_visit(node)
        self.current_nesting -= 1


def _python_imports(tree: ast.AST) -> tuple[set[str], set[str]]:
    imports: set[str] = set()
    internal: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = str(alias.name or "")
                if name:
                    imports.add(name)
                    if name.startswith(("nico", "apps")):
                        internal.add(name)
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            name = "." * int(node.level or 0) + module
            if name:
                imports.add(name)
            if int(node.level or 0) > 0 or module.startswith(("nico", "apps")):
                internal.add(name or ".")
    return imports, internal


def _analyze_python(path: str, text: str) -> dict[str, Any]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return {
            "status": "parse_failed",
            "path": path,
            "note": f"Python AST parsing failed at line {exc.lineno or 'unknown'}; no complexity score was inferred for this file.",
        }

    functions: list[dict[str, Any]] = []
    classes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes += 1
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visitor = _FunctionComplexityVisitor(node)
        visitor.visit(node)
        end_line = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
        loc = max(1, end_line - int(node.lineno) + 1)
        functions.append(
            {
                "path": path,
                "name": str(node.name),
                "line": int(node.lineno),
                "end_line": end_line,
                "loc": loc,
                "cyclomatic_complexity": visitor.complexity,
                "grade": _grade(visitor.complexity),
                "max_nesting": visitor.max_nesting,
                "language": "python",
                "method": "python_ast",
            }
        )

    imports, internal_imports = _python_imports(tree)
    source_loc = sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    return {
        "status": "analyzed",
        "path": path,
        "language": "python",
        "source_loc": source_loc,
        "functions": functions,
        "classes": classes,
        "imports": sorted(imports),
        "internal_imports": sorted(internal_imports),
        "fan_out": len(imports),
        "internal_fan_out": len(internal_imports),
        "method": "python_ast",
    }


def _strip_js_comments_and_strings(text: str) -> str:
    pattern = re.compile(
        r"(?P<block>/\*.*?\*/)|(?P<line>//[^\n]*)|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)",
        re.DOTALL,
    )
    return pattern.sub(lambda match: "\n" * match.group(0).count("\n") if match.group("block") else "", text)


def _js_imports(text: str) -> tuple[set[str], set[str]]:
    imports: set[str] = set()
    patterns = (
        re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]"),
        re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    )
    for pattern in patterns:
        imports.update(match.group(1) for match in pattern.finditer(text))
    internal = {name for name in imports if name.startswith((".", "@/", "nico/", "apps/"))}
    return imports, internal


def _brace_nesting(text: str) -> int:
    depth = 0
    maximum = 0
    for char in text:
        if char == "{":
            depth += 1
            maximum = max(maximum, depth)
        elif char == "}":
            depth = max(0, depth - 1)
    return maximum


def _analyze_javascript(path: str, text: str) -> dict[str, Any]:
    cleaned = _strip_js_comments_and_strings(text)
    source_loc = sum(1 for line in cleaned.splitlines() if line.strip())
    branch_patterns = (
        r"\bif\s*\(",
        r"\bfor\s*\(",
        r"\bwhile\s*\(",
        r"\bcase\b",
        r"\bcatch\s*\(",
        r"\?\?",
        r"&&",
        r"\|\|",
        r"\?(?![?.])",
    )
    branch_count = sum(len(re.findall(pattern, cleaned)) for pattern in branch_patterns)
    function_patterns = (
        r"\bfunction\s+[A-Za-z_$][\w$]*\s*\(",
        r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
        r"\b[A-Za-z_$][\w$]*\s*\([^;{}]*\)\s*\{",
    )
    function_count = sum(len(re.findall(pattern, cleaned)) for pattern in function_patterns)
    imports, internal_imports = _js_imports(text)
    module_complexity = max(1, 1 + branch_count)
    synthetic_function = {
        "path": path,
        "name": "<module-heuristic>",
        "line": 1,
        "end_line": max(1, len(text.splitlines())),
        "loc": source_loc,
        "cyclomatic_complexity": module_complexity,
        "grade": _grade(module_complexity),
        "max_nesting": _brace_nesting(cleaned),
        "language": "javascript-typescript",
        "method": "bounded_lexical_heuristic",
        "declared_function_count": function_count,
    }
    return {
        "status": "analyzed",
        "path": path,
        "language": "javascript-typescript",
        "source_loc": source_loc,
        "functions": [synthetic_function],
        "declared_function_count": function_count,
        "imports": sorted(imports),
        "internal_imports": sorted(internal_imports),
        "fan_out": len(imports),
        "internal_fan_out": len(internal_imports),
        "method": "bounded_lexical_heuristic",
    }


def _normalized_duplicate_lines(text: str) -> list[tuple[int, str]]:
    normalized: list[tuple[int, str]] = []
    in_block_comment = False
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
                line = line.split("*/", 1)[1].strip()
            else:
                continue
        if line.startswith("/*"):
            if "*/" not in line:
                in_block_comment = True
                continue
            line = line.split("*/", 1)[1].strip()
        if not line or line.startswith(("#", "//", "*")):
            continue
        if line.startswith(("import ", "from ")) or line in {"{", "}", "};", ");"}:
            continue
        compact = re.sub(r"\s+", " ", line)
        compact = re.sub(r"['\"][^'\"]{16,}['\"]", "<string>", compact)
        if len(compact) < 12:
            continue
        normalized.append((line_no, compact))
    return normalized


def _duplicate_evidence(files: dict[str, str]) -> dict[str, Any]:
    occurrences: dict[str, list[tuple[str, int, tuple[int, ...]]]] = defaultdict(list)
    total_positions: set[tuple[str, int]] = set()
    source_loc = 0

    for path, text in files.items():
        if not _is_source_path(path):
            continue
        lines = _normalized_duplicate_lines(text)
        source_loc += len(lines)
        for index in range(0, max(0, len(lines) - MIN_DUPLICATE_WINDOW + 1)):
            window = lines[index : index + MIN_DUPLICATE_WINDOW]
            payload = "\n".join(value for _, value in window)
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            occurrences[digest].append((path, window[0][0], tuple(line_no for line_no, _ in window)))

    samples: list[dict[str, Any]] = []
    duplicate_groups = 0
    for digest, items in occurrences.items():
        distinct_paths = {path for path, _, _ in items}
        if len(distinct_paths) < 2:
            continue
        duplicate_groups += 1
        for path, _, line_numbers in items:
            total_positions.update((path, line_no) for line_no in line_numbers)
        if len(samples) < MAX_DUPLICATE_SAMPLES:
            samples.append(
                {
                    "fingerprint": digest[:12],
                    "block_lines": MIN_DUPLICATE_WINDOW,
                    "occurrences": [
                        {"path": path, "start_line": start_line}
                        for path, start_line, _ in items[:6]
                    ],
                }
            )

    ratio = len(total_positions) / source_loc if source_loc else 0.0
    return {
        "window_lines": MIN_DUPLICATE_WINDOW,
        "duplicate_block_groups": duplicate_groups,
        "duplicate_line_positions": len(total_positions),
        "normalized_source_lines": source_loc,
        "duplicate_line_ratio": round(ratio, 4),
        "samples": samples,
        "method": "normalized_cross_file_window_hashing",
    }


def collect_complexity_evidence(files: dict[str, str]) -> dict[str, Any]:
    """Measure bounded source complexity from the authorized GitHub text-file sample."""

    source_files = {path: text for path, text in files.items() if _is_source_path(path)}
    analyses: list[dict[str, Any]] = []
    parse_notes: list[str] = []
    for path, text in sorted(source_files.items()):
        analysis = _analyze_python(path, text) if path.lower().endswith(".py") else _analyze_javascript(path, text)
        if analysis.get("status") == "parse_failed":
            parse_notes.append(str(analysis.get("note") or f"Could not parse {path}."))
            continue
        analyses.append(analysis)

    functions = [item for analysis in analyses for item in analysis.get("functions") or [] if isinstance(item, dict)]
    complexities = [int(item.get("cyclomatic_complexity") or 0) for item in functions]
    lengths = [int(item.get("loc") or 0) for item in functions]
    nesting = [int(item.get("max_nesting") or 0) for item in functions]
    fan_outs = [int(analysis.get("fan_out") or 0) for analysis in analyses]
    internal_fan_outs = [int(analysis.get("internal_fan_out") or 0) for analysis in analyses]
    grades = Counter(str(item.get("grade") or "unknown") for item in functions)

    hotspots: list[dict[str, Any]] = []
    for item in functions:
        complexity = int(item.get("cyclomatic_complexity") or 0)
        loc = int(item.get("loc") or 0)
        depth = int(item.get("max_nesting") or 0)
        risk = complexity * 3 + min(loc, 200) / 5 + depth * 4
        if complexity >= 11 or loc >= 80 or depth >= 5:
            hotspots.append({**item, "hotspot_score": round(risk, 1)})
    hotspots.sort(key=lambda item: float(item.get("hotspot_score") or 0), reverse=True)

    coupled = sorted(
        (
            {
                "path": analysis.get("path"),
                "fan_out": int(analysis.get("fan_out") or 0),
                "internal_fan_out": int(analysis.get("internal_fan_out") or 0),
                "imports": list(analysis.get("imports") or [])[:20],
            }
            for analysis in analyses
        ),
        key=lambda item: (item["internal_fan_out"], item["fan_out"]),
        reverse=True,
    )
    duplicate = _duplicate_evidence(source_files)
    python_files = sum(1 for item in analyses if item.get("language") == "python")
    js_files = sum(1 for item in analyses if item.get("language") == "javascript-typescript")
    total_loc = sum(int(item.get("source_loc") or 0) for item in analyses)
    high_complexity = sum(1 for value in complexities if value >= 11)
    very_high_complexity = sum(1 for value in complexities if value >= 21)
    long_functions = sum(1 for value in lengths if value >= 80)
    deep_nesting = sum(1 for value in nesting if value >= 5)

    status = "attached" if analyses else "unavailable"
    unavailable: list[str] = []
    if js_files:
        unavailable.append(
            "JavaScript and TypeScript complexity uses a bounded lexical heuristic because a full parser artifact was not attached; those module-level values are lower-confidence than Python AST metrics."
        )
    if parse_notes:
        unavailable.append(f"{len(parse_notes)} Python source file(s) could not be parsed and were excluded from complexity metrics.")
    if not source_files:
        unavailable.append("No eligible source files were present in the authorized GitHub text-file sample.")

    return {
        "status": status,
        "analyzer_version": "nico-bounded-complexity-v1",
        "scope": "Authorized GitHub text-file sample; test, build, distribution, dependency, and minified paths are excluded.",
        "files_considered": len(source_files),
        "files_analyzed": len(analyses),
        "python_files_analyzed": python_files,
        "javascript_typescript_files_analyzed": js_files,
        "python_parse_failures": len(parse_notes),
        "total_source_loc": total_loc,
        "functions_measured": len(functions),
        "average_cyclomatic_complexity": round(mean(complexities), 2) if complexities else None,
        "median_cyclomatic_complexity": round(median(complexities), 2) if complexities else None,
        "p90_cyclomatic_complexity": _percentile(complexities, 0.90),
        "maximum_cyclomatic_complexity": max(complexities) if complexities else None,
        "complexity_grades": dict(sorted(grades.items())),
        "high_complexity_functions": high_complexity,
        "very_high_complexity_functions": very_high_complexity,
        "high_complexity_ratio": round(high_complexity / len(functions), 4) if functions else None,
        "average_function_loc": round(mean(lengths), 2) if lengths else None,
        "median_function_loc": round(median(lengths), 2) if lengths else None,
        "long_functions": long_functions,
        "deep_nesting_functions": deep_nesting,
        "maximum_nesting": max(nesting) if nesting else None,
        "import_edges": sum(fan_outs),
        "internal_import_edges": sum(internal_fan_outs),
        "average_fan_out": round(mean(fan_outs), 2) if fan_outs else 0.0,
        "maximum_fan_out": max(fan_outs) if fan_outs else 0,
        "top_coupled_files": coupled[:15],
        "hotspots": hotspots[:MAX_HOTSPOTS],
        "duplicate_evidence": duplicate,
        "parse_notes": parse_notes[:20],
        "unavailable_data_notes": unavailable,
        "retention_note": "Only numeric summaries, paths, line numbers, import names, and bounded fingerprints are retained; source contents are not stored in this evidence object.",
        "guardrail": "Complexity evidence describes the authorized sampled files. It does not establish whole-repository absence of complexity, duplication, coupling, or maintainability risk.",
        "human_review_required": True,
    }
