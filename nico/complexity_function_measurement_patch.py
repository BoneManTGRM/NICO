from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

PATCH_VERSION = "nico.complexity_function_measurement.v1"
_MARKER = "_nico_complexity_function_measurement_v1"
CHURN_WINDOW_DAYS = 180
_COMPLETED_METHODS = {"python_ast_function_level_v2", "javascript_typescript_function_level_v2"}


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _python_function_measurements(text: str) -> list[dict[str, Any]]:
    from nico.full_assessment_complexity_evidence import _FunctionComplexityVisitor

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visitor = _FunctionComplexityVisitor(node)
        visitor.visit(node)
        functions.append(
            {
                "name": str(node.name),
                "line": int(node.lineno),
                "end_line": int(getattr(node, "end_lineno", node.lineno) or node.lineno),
                "cyclomatic_complexity": int(visitor.complexity),
                "max_nesting": int(visitor.max_nesting),
                "method": "python_ast_function_level_v2",
            }
        )
    return functions


def analyze_python_with_function_risk(
    path: Path,
    text: str,
    *,
    original: Callable[[Path, str], dict[str, Any]],
) -> dict[str, Any]:
    result = dict(original(path, text))
    functions = _python_function_measurements(text)
    if not functions and result.get("parse_error"):
        return result
    result["function_count"] = len(functions)
    result["max_function_complexity"] = max(
        (_int(item.get("cyclomatic_complexity")) for item in functions),
        default=0,
    )
    result["function_complexity_method"] = "python_ast_function_level_v2"
    result["highest_risk_functions"] = sorted(
        functions,
        key=lambda item: _int(item.get("cyclomatic_complexity")),
        reverse=True,
    )[:8]
    return result


def analyze_script_with_function_risk(
    path: Path,
    text: str,
    *,
    original: Callable[[Path, str], dict[str, Any]],
) -> dict[str, Any]:
    from nico.assessment_score_integrity import analyze_javascript_functions

    result = dict(original(path, text))
    measured = analyze_javascript_functions(str(path), text)
    functions = [
        item
        for item in measured.get("functions", []) or []
        if isinstance(item, dict)
    ]
    declared = [item for item in functions if item.get("name") != "<module-logic>"]
    result["function_count"] = len(declared)
    result["max_function_complexity"] = max(
        (_int(item.get("cyclomatic_complexity")) for item in functions),
        default=0,
    )
    result["function_complexity_method"] = "javascript_typescript_function_level_v2"
    result["highest_risk_functions"] = sorted(
        [
            {
                "name": item.get("name"),
                "line": item.get("line"),
                "end_line": item.get("end_line"),
                "cyclomatic_complexity": item.get("cyclomatic_complexity"),
                "max_nesting": item.get("max_nesting"),
                "method": item.get("method"),
            }
            for item in functions
        ],
        key=lambda item: _int(item.get("cyclomatic_complexity")),
        reverse=True,
    )[:8]
    return result


def recent_git_churn(repo_dir: Path) -> dict[str, int]:
    from collections import defaultdict
    from nico import complexity_engine as engine
    from nico.worker_execution import WorkerLimits

    result = engine.run_command(
        (
            "git",
            "log",
            f"--since={CHURN_WINDOW_DAYS} days ago",
            "--numstat",
            "--pretty=format:",
        ),
        cwd=repo_dir,
        limits=WorkerLimits(timeout_seconds=45, max_output_chars=120_000),
    )
    if not result.ok:
        previous = getattr(recent_git_churn, "_nico_previous", None)
        return previous(repo_dir) if callable(previous) else {}
    churn: dict[str, int] = defaultdict(int)
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        churn[path] += _int(added if added.isdigit() else 0) + _int(deleted if deleted.isdigit() else 0)
    return dict(churn)


def _patch_profile_presentation() -> None:
    from nico import hosted_complexity_engine_attachment_patch as attachment

    current = attachment.build_complexity_attachment_summary
    if getattr(current, _MARKER, False):
        return
    original = current

    def summary_with_function_measurements(profile: dict[str, Any] | None) -> dict[str, Any]:
        summary = dict(original(profile))
        raw = profile if isinstance(profile, dict) else {}
        summary["scoring_model"] = raw.get("scoring_model") or "function_risk_density_v3"
        summary["max_function_cyclomatic_complexity"] = _int(
            raw.get("max_function_cyclomatic_complexity")
        )
        summary["high_function_risk_file_count"] = _int(
            raw.get("high_function_risk_file_count")
        )
        summary["churn_complexity_overlap_count"] = _int(
            raw.get("churn_complexity_overlap_count")
        )
        summary["churn_window_days"] = _int(raw.get("churn_window_days")) or CHURN_WINDOW_DAYS
        summary["function_measurement_methods"] = list(
            raw.get("function_measurement_methods") or []
        )
        raw_hotspots = raw.get("hotspots") if isinstance(raw.get("hotspots"), list) else []
        for target, source in zip(summary.get("top_hotspots") or [], raw_hotspots):
            if isinstance(target, dict) and isinstance(source, dict):
                target["max_function_cyclomatic_complexity"] = source.get(
                    "max_function_cyclomatic_complexity"
                )
                target["complexity_density_per_100_loc"] = source.get(
                    "complexity_density_per_100_loc"
                )
                target["function_complexity_method"] = source.get(
                    "function_complexity_method"
                )
        return summary

    setattr(summary_with_function_measurements, _MARKER, True)
    setattr(summary_with_function_measurements, "_nico_previous", original)
    attachment.build_complexity_attachment_summary = summary_with_function_measurements


def _patch_profile_builder() -> None:
    from nico import complexity_engine as engine

    current = engine.build_complexity_profile
    if getattr(current, _MARKER, False):
        return
    original = current

    def build_profile_with_measurement_metadata(repo_dir: Path) -> dict[str, Any]:
        profile = dict(original(repo_dir))
        profile["scoring_model"] = "function_risk_density_v3"
        profile["churn_window_days"] = CHURN_WINDOW_DAYS
        profile["function_measurement_methods"] = sorted(_COMPLETED_METHODS)
        profile["measurement_guardrail"] = (
            "Maximum function complexity is measured per function. Whole-module aggregate branch count is retained as scope evidence but is not substituted for function risk. Delivery-hotspot churn is bounded to the report-aligned 180-day window."
        )
        evidence = []
        for item in profile.get("evidence", []) or []:
            text = str(item)
            if text.startswith("Git churn data available for"):
                text = text.replace(
                    "Git churn data available for",
                    f"{CHURN_WINDOW_DAYS}-day Git churn data available for",
                    1,
                )
            evidence.append(text)
        evidence.append(
            "Function-level complexity measurement completed with Python AST and bounded JavaScript/TypeScript function extraction; module aggregate complexity remains separately disclosed."
        )
        profile["evidence"] = list(dict.fromkeys(evidence))
        return profile

    setattr(build_profile_with_measurement_metadata, _MARKER, True)
    setattr(build_profile_with_measurement_metadata, "_nico_previous", original)
    engine.build_complexity_profile = build_profile_with_measurement_metadata


def install_complexity_function_measurement_patch() -> dict[str, Any]:
    from nico import complexity_engine as engine

    current_python = engine._analyze_python
    current_script = engine._analyze_script
    already_installed = bool(
        getattr(current_python, _MARKER, False)
        and getattr(current_script, _MARKER, False)
    )
    if not getattr(current_python, _MARKER, False):
        original_python = current_python

        def analyze_python(path: Path, text: str) -> dict[str, Any]:
            return analyze_python_with_function_risk(path, text, original=original_python)

        setattr(analyze_python, _MARKER, True)
        setattr(analyze_python, "_nico_previous", original_python)
        engine._analyze_python = analyze_python

    if not getattr(current_script, _MARKER, False):
        original_script = current_script

        def analyze_script(path: Path, text: str) -> dict[str, Any]:
            return analyze_script_with_function_risk(path, text, original=original_script)

        setattr(analyze_script, _MARKER, True)
        setattr(analyze_script, "_nico_previous", original_script)
        engine._analyze_script = analyze_script

    current_churn = engine._git_numstat
    if not getattr(current_churn, _MARKER, False):
        setattr(recent_git_churn, _MARKER, True)
        setattr(recent_git_churn, "_nico_previous", current_churn)
        engine._git_numstat = recent_git_churn

    _patch_profile_builder()
    _patch_profile_presentation()
    return {
        "status": "already_installed" if already_installed else "installed",
        "version": PATCH_VERSION,
        "python_function_level": True,
        "javascript_typescript_function_level": True,
        "module_aggregate_used_as_function_risk": False,
        "churn_window_days": CHURN_WINDOW_DAYS,
        "score_inflation_allowed": False,
        "guardrail": (
            "Scores may change only from more precise function measurements and a disclosed recent-delivery churn window. Parse failures, large-file overlap, ownership risk, and measured hotspots remain visible."
        ),
    }


__all__ = [
    "CHURN_WINDOW_DAYS",
    "PATCH_VERSION",
    "analyze_python_with_function_risk",
    "analyze_script_with_function_risk",
    "install_complexity_function_measurement_patch",
    "recent_git_churn",
]
