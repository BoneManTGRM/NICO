from __future__ import annotations

import ast
from functools import wraps
from pathlib import PurePosixPath
from typing import Any, Callable

PATCH_VERSION = "nico.language_aware_pattern_reconciliation.v2"
_PATCH_MARKER = "_nico_language_aware_pattern_reconciliation_v2"
_SCAN_MARKER = "_nico_language_aware_scan_files_v2"
_SCRIPT_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
_PYTHON_EXTENSIONS = {".py"}
_PYTHON_RULES = {"python_eval_exec", "python_shell_true", "python_os_system", "unsafe_yaml_load", "pickle_loads"}
_SCRIPT_RULES = {"js_inner_html", "react_dangerous_html"}


def _finding_parts(note: str) -> tuple[str, int | None, str]:
    text = str(note or "").strip()
    if not text:
        return "", None, ""
    prefix, _, detail = text.partition(": ")
    path_part, separator, line_part = prefix.rpartition(":")
    if not separator:
        return "", None, detail
    try:
        line = int(line_part)
    except ValueError:
        line = None
    return path_part.strip().replace("\\", "/"), line, detail


def _finding_path(note: str) -> str:
    return _finding_parts(note)[0]


def _finding_rule(note: str) -> str:
    detail = _finding_parts(note)[2]
    for separator in (" — ", " - "):
        if separator in detail:
            detail = detail.split(separator, 1)[0]
            break
    return detail.strip().casefold()


def _is_cross_language_python_exec_hit(note: str) -> bool:
    path = _finding_path(note)
    return _finding_rule(note) == "python_eval_exec" and PurePosixPath(path).suffix.lower() in _SCRIPT_EXTENSIONS


def _python_call_lines(source: str) -> dict[str, set[int]]:
    matches: dict[str, set[int]] = {rule: set() for rule in _PYTHON_RULES}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return matches
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        line = int(getattr(node, "lineno", 0) or 0)
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
            matches["python_eval_exec"].add(line)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "os" and func.attr == "system":
                matches["python_os_system"].add(line)
            if func.value.id == "yaml" and func.attr == "load":
                matches["unsafe_yaml_load"].add(line)
            if func.value.id == "pickle" and func.attr in {"load", "loads"}:
                matches["pickle_loads"].add(line)
        if any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ):
            matches["python_shell_true"].add(line)
    return matches


def _risk_note_is_executable(note: str, files: dict[str, str], python_lines: dict[str, dict[str, set[int]]]) -> bool:
    path, line, _ = _finding_parts(note)
    rule = _finding_rule(note)
    suffix = PurePosixPath(path).suffix.lower()
    if rule in _SCRIPT_RULES:
        return suffix in _SCRIPT_EXTENSIONS
    if rule in _PYTHON_RULES:
        if suffix not in _PYTHON_EXTENSIONS or line is None:
            return False
        return line in python_lines.get(path, {}).get(rule, set())
    return True


def wrap_scan_files(delegate: Callable[[dict[str, str]], dict[str, Any]]) -> Callable[[dict[str, str]], dict[str, Any]]:
    if getattr(delegate, _SCAN_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(files: dict[str, str]) -> dict[str, Any]:
        result = delegate(files)
        if not isinstance(result, dict):
            return result
        python_lines = {
            path: _python_call_lines(source)
            for path, source in files.items()
            if PurePosixPath(path).suffix.lower() in _PYTHON_EXTENSIONS
        }
        output = dict(result)
        risks = [str(item) for item in result.get("risks") or []]
        output["risks"] = [item for item in risks if _risk_note_is_executable(item, files, python_lines)]
        previous = result.get("risk_pattern_filter") if isinstance(result.get("risk_pattern_filter"), dict) else {}
        previous_raw = int(previous.get("raw_count") or len(risks))
        previous_excluded = int(previous.get("excluded_language_or_literal_mismatches") or 0)
        newly_excluded = len(risks) - len(output["risks"])
        output["risk_pattern_filter"] = {
            "version": PATCH_VERSION,
            "raw_count": max(previous_raw, len(risks) + previous_excluded),
            "retained_count": len(output["risks"]),
            "excluded_language_or_literal_mismatches": previous_excluded + newly_excluded,
        }
        return output

    setattr(wrapped, _SCAN_MARKER, True)
    return wrapped


def install_language_aware_pattern_reconciliation() -> dict[str, Any]:
    from nico import assessment_quality, hosted_assessment, snapshot_repository_evidence

    current: Callable[[str], str] = assessment_quality._classify_static_hit
    if not getattr(current, _PATCH_MARKER, False):
        def classify_language_aware(note: str) -> str:
            path = _finding_path(note)
            suffix = PurePosixPath(path).suffix.lower()
            rule = _finding_rule(note)
            if rule in _PYTHON_RULES and suffix in _SCRIPT_EXTENSIONS:
                return "language_rule_mismatch"
            if rule in _SCRIPT_RULES and suffix not in _SCRIPT_EXTENSIONS:
                return "language_rule_mismatch"
            return current(note)

        setattr(classify_language_aware, _PATCH_MARKER, True)
        setattr(classify_language_aware, "_nico_previous", current)
        assessment_quality._classify_static_hit = classify_language_aware

    hosted_wrapper = wrap_scan_files(hosted_assessment.scan_files)
    hosted_assessment.scan_files = hosted_wrapper
    snapshot_repository_evidence.scan_files = hosted_wrapper
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "script_extensions": sorted(_SCRIPT_EXTENSIONS),
        "python_rules_require_python_ast_call": True,
        "script_rules_require_script_extension": True,
        "cross_language_rules_scored": False,
        "string_literal_rule_definitions_scored": False,
        "scan_wrapper_bound": hosted_assessment.scan_files is hosted_wrapper and snapshot_repository_evidence.scan_files is hosted_wrapper,
        "evidence_retained_for_review": True,
        "human_review_required": True,
    }


__all__ = [
    "PATCH_VERSION",
    "_finding_path",
    "_finding_rule",
    "_is_cross_language_python_exec_hit",
    "_python_call_lines",
    "_risk_note_is_executable",
    "wrap_scan_files",
    "install_language_aware_pattern_reconciliation",
]
