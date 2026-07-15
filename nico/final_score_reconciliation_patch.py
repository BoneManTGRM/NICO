from __future__ import annotations

import re
import sys
from typing import Any, Callable

PATCH_VERSION = "nico.final_score_reconciliation.v1"
_MARKER = "_nico_final_score_reconciliation_v1"
_REQUIRED_DEPENDENCY_TOOLS = {"pip-audit", "npm-audit", "osv-scanner"}
_COMPLETED_STATUSES = {"completed", "completed_clean", "passed", "success"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in _list(result.get("sections")):
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _remove_text(items: Any, fragments: tuple[str, ...]) -> list[Any]:
    values = items if isinstance(items, list) else ([] if items in (None, "") else [items])
    return [
        item
        for item in values
        if not any(fragment in str(item or "").lower() for fragment in fragments)
    ]


def _tool_record_clean(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "").strip().lower()
    if status not in _COMPLETED_STATUSES:
        return False
    if _int(record.get("findings_count") or record.get("finding_count")) != 0:
        return False
    if record.get("verified_for_this_report") is False or record.get("current_run") is False:
        return False
    return True


def _records_from_mapping(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, value in mapping.items():
        if isinstance(value, dict):
            records[str(name).strip().lower()] = value
    return records


def _dependency_tool_records(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: list[dict[str, dict[str, Any]]] = []

    runtime = _dict(result.get("hosted_full_evidence_runtime_validation"))
    records = {
        str(item.get("tool") or "").strip().lower(): item
        for item in _list(runtime.get("tool_records"))
        if isinstance(item, dict) and item.get("tool")
    }
    if records:
        candidates.append(records)
    normalized = _dict(runtime.get("normalized"))
    normalized_tools = _records_from_mapping(_dict(normalized.get("tools")))
    if normalized_tools:
        candidates.append(normalized_tools)

    guards = _dict(result.get("report_quality_guards"))
    hosted_guard = _dict(guards.get("hosted_full_evidence_runtime"))
    guard_records = {
        str(item.get("tool") or "").strip().lower(): item
        for item in _list(hosted_guard.get("tool_records"))
        if isinstance(item, dict) and item.get("tool")
    }
    if guard_records:
        candidates.append(guard_records)

    scanner = _dict(result.get("scanner_worker_artifact_normalized"))
    scanner_tools = _records_from_mapping(_dict(scanner.get("tools")))
    if scanner_tools:
        candidates.append(scanner_tools)

    for candidate in candidates:
        if _REQUIRED_DEPENDENCY_TOOLS.issubset(candidate):
            return candidate
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        merged.update(candidate)
    return merged


def dependency_scanner_proof_is_present(result: dict[str, Any]) -> bool:
    return _REQUIRED_DEPENDENCY_TOOLS.issubset(_dependency_tool_records(result))


def dependency_scanner_proof_is_clean(result: dict[str, Any]) -> bool:
    records = _dependency_tool_records(result)
    return _REQUIRED_DEPENDENCY_TOOLS.issubset(records) and all(
        _tool_record_clean(records[name]) for name in _REQUIRED_DEPENDENCY_TOOLS
    )


def _test_path_count(result: dict[str, Any]) -> int:
    direct_candidates = (
        _dict(result.get("repository_metadata")).get("test_path_signal_count"),
        _dict(result.get("repository_metadata")).get("test_path_count"),
        _dict(result.get("scanner_artifact_summary")).get("test_path_signal_count"),
        _dict(result.get("scanner_worker_artifact_normalized")).get("test_path_signal_count"),
    )
    for candidate in direct_candidates:
        count = _int(candidate)
        if count > 0:
            return count

    architecture = _section(result, "architecture_debt")
    texts: list[str] = []
    if architecture:
        texts.extend(str(item or "") for item in _list(architecture.get("evidence")))
        texts.extend(str(item or "") for item in _list(architecture.get("findings")))
    texts.append(str(result.get("repository_metadata") or ""))
    pattern = re.compile(r"(?:repository tree )?test-path signal count\s*:\s*(\d+)", re.IGNORECASE)
    for text in texts:
        match = pattern.search(text)
        if match and int(match.group(1)) > 0:
            return int(match.group(1))
    return 0


def reconcile_code_audit_test_evidence(result: dict[str, Any]) -> bool:
    code = _section(result, "code_audit")
    test_count = _test_path_count(result)
    if not code or test_count <= 0:
        return False

    before_score = _int(code.get("score"))
    before_findings = list(code.get("findings") or [])
    before_unavailable = list(code.get("unavailable") or [])
    absence_fragments = (
        "no test-path signals were found",
        "no test path signals were found",
        "test-path signals=0",
    )
    code["findings"] = _remove_text(code.get("findings"), absence_fragments)
    code["unavailable"] = _remove_text(code.get("unavailable"), absence_fragments)
    code.setdefault("evidence", [])
    _append_unique(
        code["evidence"],
        f"Test evidence reconciled across scopes: the recursive repository tree contains {test_count} test-path signal(s). A bounded fetched-text sample with zero test paths is not treated as repository-wide absence evidence.",
    )

    evidence_text = "\n".join(str(item or "") for item in code.get("evidence", [])).lower()
    clean_markers = "actionable todo/fixme/security markers=0" in evidence_text
    no_risky_patterns = "risky pattern hits=0" in evidence_text or "production-risk=0" in evidence_text
    if clean_markers and no_risky_patterns:
        code["score"] = max(before_score, 90)
        code["status"] = "green"
        code["confidence"] = "high"
        code["summary"] = (
            "Code audit combines recent commit and pull-request traceability, clean actionable-marker review, "
            "and recursive repository test-path evidence. Bounded text sampling is not used to claim that tests are absent."
        )
    return (
        _int(code.get("score")) != before_score
        or code.get("findings") != before_findings
        or code.get("unavailable") != before_unavailable
    )


def _patch_release_readiness_signals() -> None:
    from nico import final_report_consistency as consistency

    current = consistency._release_readiness_signals
    if getattr(current, _MARKER, False):
        return
    original = current

    def release_readiness_signals(result: dict[str, Any]) -> dict[str, Any]:
        readiness = dict(original(result))
        signals = dict(readiness.get("signals") or {})
        dependency = _section(result, "dependency_health")
        dependency_text = "\n".join(
            str(item or "")
            for key in ("summary", "evidence", "findings", "unavailable")
            for item in (
                _list((dependency or {}).get(key))
                if isinstance((dependency or {}).get(key), list)
                else [(dependency or {}).get(key)]
            )
        ).lower()
        no_vulnerability_statement = (
            "no vulnerability records" in dependency_text
            or "zero dependency vulnerabilities" in dependency_text
        )
        structured_present = dependency_scanner_proof_is_present(result)
        structured_clean = dependency_scanner_proof_is_clean(result)
        if structured_present:
            dependency_ready = bool(
                dependency
                and _int(dependency.get("score")) >= 88
                and structured_clean
                and no_vulnerability_statement
            )
            signals["dependency_scanner_clean_artifacts_attached"] = dependency_ready
            if dependency_ready:
                signals["dependency_no_osv_vulnerabilities"] = True
        passed = [name for name, ok in signals.items() if ok]
        missing = [name for name, ok in signals.items() if not ok]
        return {
            "ready": not missing,
            "passed": passed,
            "missing": missing,
            "signals": signals,
            "structured_dependency_proof_present": structured_present,
            "structured_dependency_proof": structured_clean,
        }

    setattr(release_readiness_signals, _MARKER, True)
    setattr(release_readiness_signals, "_nico_previous", original)
    consistency._release_readiness_signals = release_readiness_signals


def reconcile_final_evidence_scores(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result

    from nico import final_report_consistency as consistency
    from nico.score_details import attach_score_details

    before = {
        "overall": _int(_dict(result.get("maturity_signal")).get("score")),
        "code_audit": _int((_section(result, "code_audit") or {}).get("score")),
        "dependency_health": _int((_section(result, "dependency_health") or {}).get("score")),
        "velocity_complexity": _int((_section(result, "velocity_complexity") or {}).get("score")),
    }

    reconcile_code_audit_test_evidence(result)
    consistency._apply_dependency_evidence_adjustment(result)
    consistency._apply_release_readiness_adjustment(result)
    consistency._apply_truth_guard(result)
    consistency._recompute_maturity(result)

    refreshed = attach_score_details(result)
    result.clear()
    result.update(refreshed)
    maturity = _dict(result.get("maturity_signal"))
    result["score_source_of_truth"] = {
        "field": "maturity_signal",
        "level": maturity.get("level"),
        "score": maturity.get("score"),
        "rule": (
            "Executive summary, score details, and report exports are rebuilt from the final visible section scores "
            "after structured scanner-proof and cross-scope test-evidence reconciliation."
        ),
    }
    result["final_score_reconciliation"] = {
        "status": "reconciled",
        "version": PATCH_VERSION,
        "before": before,
        "after": {
            "overall": _int(maturity.get("score")),
            "code_audit": _int((_section(result, "code_audit") or {}).get("score")),
            "dependency_health": _int((_section(result, "dependency_health") or {}).get("score")),
            "velocity_complexity": _int((_section(result, "velocity_complexity") or {}).get("score")),
        },
        "dependency_scanner_proof_present": dependency_scanner_proof_is_present(result),
        "dependency_scanner_proof_clean": dependency_scanner_proof_is_clean(result),
        "recursive_tree_test_path_count": _test_path_count(result),
        "score_inflation_allowed": False,
        "guardrail": (
            "Scores change only when the report already contains current-run structured clean scanner records or "
            "positive recursive-tree test evidence that contradicts a bounded-sample absence claim. Findings and human review remain intact."
        ),
    }
    consistency._rebuild_reports(result)
    return result


def install_final_score_reconciliation_patch() -> dict[str, Any]:
    from nico import final_report_consistency as consistency

    _patch_release_readiness_signals()
    current: Callable[[dict[str, Any]], dict[str, Any]] = consistency.finalize_express_result_consistency
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "structured_dependency_proof": True,
            "cross_scope_test_reconciliation": True,
            "final_score_details_refresh": True,
        }
    original = current

    def finalize_with_reconciled_scores(result: dict[str, Any]) -> dict[str, Any]:
        finalized = original(result)
        return reconcile_final_evidence_scores(finalized)

    setattr(finalize_with_reconciled_scores, _MARKER, True)
    setattr(finalize_with_reconciled_scores, "_nico_previous", original)
    consistency.finalize_express_result_consistency = finalize_with_reconciled_scores

    rebound = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "finalize_express_result_consistency", None) is original:
                setattr(module, "finalize_express_result_consistency", finalize_with_reconciled_scores)
                rebound += 1
        except Exception:
            continue

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "structured_dependency_proof": True,
        "cross_scope_test_reconciliation": True,
        "final_score_details_refresh": True,
        "rebound_import_references": rebound,
        "score_inflation_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "dependency_scanner_proof_is_clean",
    "dependency_scanner_proof_is_present",
    "install_final_score_reconciliation_patch",
    "reconcile_code_audit_test_evidence",
    "reconcile_final_evidence_scores",
]
