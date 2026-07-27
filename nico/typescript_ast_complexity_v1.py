from __future__ import annotations

import json
import subprocess
from collections import Counter
from functools import wraps
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

VERSION = "nico.typescript_ast_complexity.v1"
_PATCH_MARKER = "_nico_typescript_ast_complexity_v1"
AST_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "typescript_ast_metrics.cjs"
AST_TIMEOUT_SECONDS = 180


def _run_typescript_ast(files: dict[str, str]) -> dict[str, Any]:
    payload = {
        "files": {
            path: text
            for path, text in files.items()
            if path.casefold().endswith((".ts", ".tsx", ".js", ".jsx"))
        }
    }
    if not payload["files"]:
        return {"status": "complete", "analyses": [], "import_graph": {}}
    try:
        completed = subprocess.run(
            ("node", str(AST_SCRIPT)),
            input=json.dumps(payload, separators=(",", ":")),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=AST_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__, "analyses": []}
    try:
        result = json.loads(completed.stdout or "{}")
    except ValueError:
        return {
            "status": "failed",
            "reason": "invalid_typescript_ast_json",
            "stderr": (completed.stderr or "")[:1000],
            "analyses": [],
        }
    if not isinstance(result, dict):
        return {"status": "failed", "reason": "invalid_typescript_ast_payload", "analyses": []}
    if completed.returncode and result.get("status") == "complete":
        result["status"] = "failed"
        result["reason"] = "typescript_ast_nonzero_exit"
    return result


def _partition_source_files(
    files: dict[str, str],
    base: Any,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    source_files = {path: text for path, text in files.items() if base._is_source_path(path)}
    python_files = {path: text for path, text in source_files.items() if path.casefold().endswith(".py")}
    javascript_files = {path: text for path, text in source_files.items() if not path.casefold().endswith(".py")}
    return source_files, python_files, javascript_files


def _collect_python_analyses(
    python_files: dict[str, str],
    base: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    analyses: list[dict[str, Any]] = []
    parse_notes: list[str] = []
    for path, text in sorted(python_files.items()):
        analysis = base._analyze_python(path, text)
        if analysis.get("status") == "parse_failed":
            parse_notes.append(str(analysis.get("note") or f"Could not parse {path}."))
        else:
            analyses.append(analysis)
    return analyses, parse_notes


def _collect_javascript_analyses(
    javascript_files: dict[str, str],
    base: Any,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    ast_result = _run_typescript_ast(javascript_files)
    ast_analyses = [item for item in ast_result.get("analyses") or [] if isinstance(item, dict)]
    parse_notes: list[str] = []
    if ast_result.get("status") == "complete":
        ast_paths = {str(item.get("path") or "") for item in ast_analyses}
        for path in sorted(set(javascript_files) - ast_paths):
            parse_notes.append(f"TypeScript AST output omitted {path}; no lexical substitute was used for that file.")
        return ast_analyses, parse_notes, ast_result
    fallback = [base._analyze_javascript(path, text) for path, text in sorted(javascript_files.items())]
    parse_notes.append(
        "TypeScript compiler AST analysis was unavailable; JavaScript and TypeScript metrics fell back to bounded lexical extraction for this run."
    )
    return fallback, parse_notes, ast_result


def _function_metrics(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    functions = [
        item
        for analysis in analyses
        for item in analysis.get("functions") or []
        if isinstance(item, dict)
    ]
    return {
        "functions": functions,
        "complexities": [int(item.get("cyclomatic_complexity") or 0) for item in functions],
        "cognitive": [
            int(item.get("cognitive_complexity") or 0)
            for item in functions
            if item.get("cognitive_complexity") is not None
        ],
        "lengths": [int(item.get("loc") or 0) for item in functions],
        "nesting": [int(item.get("max_nesting") or 0) for item in functions],
        "grades": Counter(str(item.get("grade") or "unknown") for item in functions),
    }


def _hotspot_score(item: dict[str, Any]) -> float:
    complexity = int(item.get("cyclomatic_complexity") or 0)
    cognitive_value = int(item.get("cognitive_complexity") or 0)
    loc = int(item.get("loc") or 0)
    depth = int(item.get("max_nesting") or 0)
    return round(complexity * 3 + cognitive_value * 1.5 + min(loc, 200) / 5 + depth * 4, 1)


def _build_hotspots(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hotspots = [
        {**item, "hotspot_score": _hotspot_score(item)}
        for item in functions
        if int(item.get("cyclomatic_complexity") or 0) >= 11
        or int(item.get("cognitive_complexity") or 0) >= 15
        or int(item.get("loc") or 0) >= 80
        or int(item.get("max_nesting") or 0) >= 5
    ]
    return sorted(hotspots, key=lambda item: float(item.get("hotspot_score") or 0), reverse=True)


def _build_coupling(analyses: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int], list[int], list[int]]:
    fan_outs = [int(analysis.get("fan_out") or 0) for analysis in analyses]
    internal_fan_outs = [int(analysis.get("internal_fan_out") or 0) for analysis in analyses]
    fan_ins = [int(analysis.get("fan_in") or 0) for analysis in analyses]
    coupled = sorted(
        (
            {
                "path": analysis.get("path"),
                "fan_in": int(analysis.get("fan_in") or 0),
                "fan_out": int(analysis.get("fan_out") or 0),
                "internal_fan_out": int(analysis.get("internal_fan_out") or 0),
                "imports": list(analysis.get("imports") or [])[:20],
            }
            for analysis in analyses
        ),
        key=lambda item: (item["fan_in"] + item["internal_fan_out"], item["fan_out"]),
        reverse=True,
    )
    return coupled, fan_outs, internal_fan_outs, fan_ins


def _unavailable_notes(
    ast_result: dict[str, Any],
    javascript_files: dict[str, str],
    parse_notes: list[str],
    source_files: dict[str, str],
) -> list[str]:
    unavailable: list[str] = []
    if ast_result.get("status") != "complete" and javascript_files:
        unavailable.append(
            "TypeScript compiler AST evidence was unavailable for this run; JavaScript and TypeScript values use bounded lexical fallback and remain review-limited."
        )
    if parse_notes:
        unavailable.append(f"{len(parse_notes)} source parser limitation(s) were retained in the architecture evidence.")
    if not source_files:
        unavailable.append("No eligible first-party source files were present in the exact-SHA source profile.")
    return unavailable


def _safe_average(values: list[int], *, empty: float | None = None) -> float | None:
    return round(mean(values), 2) if values else empty


def _safe_median(values: list[int]) -> float | None:
    return round(median(values), 2) if values else None


def _safe_max(values: list[int], *, empty: int | None = None) -> int | None:
    return max(values) if values else empty


def _build_complexity(files: dict[str, str]) -> dict[str, Any]:
    from nico import full_assessment_complexity_evidence as base

    source_files, python_files, javascript_files = _partition_source_files(files, base)
    python_analyses, python_notes = _collect_python_analyses(python_files, base)
    javascript_analyses, javascript_notes, ast_result = _collect_javascript_analyses(javascript_files, base)
    analyses = [*python_analyses, *javascript_analyses]
    parse_notes = [*python_notes, *javascript_notes]

    metrics = _function_metrics(analyses)
    functions = metrics["functions"]
    complexities = metrics["complexities"]
    cognitive = metrics["cognitive"]
    lengths = metrics["lengths"]
    nesting = metrics["nesting"]
    grades = metrics["grades"]
    hotspots = _build_hotspots(functions)
    coupled, fan_outs, internal_fan_outs, fan_ins = _build_coupling(analyses)

    eligible_count = len(source_files)
    analyzed_count = len(analyses)
    high_complexity = sum(value >= 11 for value in complexities)
    import_graph = ast_result.get("import_graph") if isinstance(ast_result.get("import_graph"), dict) else {}

    return {
        "status": "attached" if analyses else "unavailable",
        "analyzer_version": VERSION,
        "scope": "Exact-SHA first-party source archive when available; tests, generated, distribution, dependency, vendor, and minified paths are excluded.",
        "files_considered": eligible_count,
        "eligible_source_files": eligible_count,
        "files_analyzed": analyzed_count,
        "source_coverage_percent": round(100 * analyzed_count / eligible_count, 1) if eligible_count else 0.0,
        "python_files_analyzed": sum(item.get("language") == "python" for item in analyses),
        "javascript_typescript_files_analyzed": sum(item.get("language") == "javascript-typescript" for item in analyses),
        "typescript_ast_files_analyzed": sum(item.get("method") == "typescript_compiler_ast" for item in analyses),
        "typescript_ast_status": ast_result.get("status") or "unavailable",
        "typescript_parser_version": ast_result.get("parser_version") or "unavailable",
        "source_parse_limitations": len(parse_notes),
        "total_source_loc": sum(int(item.get("source_loc") or 0) for item in analyses),
        "functions_measured": len(functions),
        "average_cyclomatic_complexity": _safe_average(complexities),
        "median_cyclomatic_complexity": _safe_median(complexities),
        "p90_cyclomatic_complexity": base._percentile(complexities, 0.90),
        "maximum_cyclomatic_complexity": _safe_max(complexities),
        "average_cognitive_complexity": _safe_average(cognitive),
        "maximum_cognitive_complexity": _safe_max(cognitive),
        "complexity_grades": dict(sorted(grades.items())),
        "high_complexity_functions": high_complexity,
        "very_high_complexity_functions": sum(value >= 21 for value in complexities),
        "high_complexity_ratio": round(high_complexity / len(functions), 4) if functions else None,
        "average_function_loc": _safe_average(lengths),
        "median_function_loc": _safe_median(lengths),
        "long_functions": sum(value >= 80 for value in lengths),
        "deep_nesting_functions": sum(value >= 5 for value in nesting),
        "maximum_nesting": _safe_max(nesting),
        "import_edges": sum(fan_outs),
        "internal_import_edges": sum(internal_fan_outs),
        "average_fan_out": _safe_average(fan_outs, empty=0.0),
        "maximum_fan_out": _safe_max(fan_outs, empty=0),
        "average_fan_in": _safe_average(fan_ins, empty=0.0),
        "maximum_fan_in": _safe_max(fan_ins, empty=0),
        "strongly_connected_components": int(import_graph.get("strongly_connected_components") or 0),
        "cyclic_components": list(import_graph.get("cyclic_components") or [])[:20],
        "files_in_import_cycles": list(import_graph.get("files_in_cycles") or [])[:100],
        "top_coupled_files": coupled[:25],
        "hotspots": hotspots[:50],
        "duplicate_evidence": base._duplicate_evidence(source_files),
        "parse_notes": parse_notes[:30],
        "unavailable_data_notes": _unavailable_notes(ast_result, javascript_files, parse_notes, source_files),
        "threshold_contract": {
            "per_function_cyclomatic_target": 20,
            "module_residual_complexity_target": 40,
            "maximum_nesting_target": 4,
            "thresholds_do_not_hide_or_rescore_existing_findings": True,
        },
        "retention_note": "Only numeric summaries, paths, line numbers, import names, graph edges, and bounded fingerprints are retained; source contents are not stored in this evidence object.",
        "guardrail": "Architecture metrics describe the exact-SHA first-party source profile. Parser limitations and coverage remain explicit and cannot be converted into clean evidence.",
        "human_review_required": True,
    }


def install_typescript_ast_complexity_v1() -> dict[str, Any]:
    from nico import full_assessment_complexity_evidence as complexity
    from nico import snapshot_repository_evidence as snapshot

    current: Callable[[dict[str, str]], dict[str, Any]] = complexity.collect_complexity_evidence
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def collect(files: dict[str, str]) -> dict[str, Any]:
        return _build_complexity(files)

    setattr(collect, _PATCH_MARKER, True)
    complexity.collect_complexity_evidence = collect
    snapshot.collect_complexity_evidence = collect
    return {
        "status": "installed",
        "version": VERSION,
        "typescript_compiler_ast": True,
        "cyclomatic_complexity": True,
        "cognitive_complexity": True,
        "nesting_depth": True,
        "fan_in_fan_out": True,
        "import_cycles_and_scc": True,
        "duplication": True,
        "explicit_source_coverage": True,
    }


__all__ = ["VERSION", "install_typescript_ast_complexity_v1"]
