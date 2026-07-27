from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico import phase5_report_truth_v1 as base

VERSION = "nico.phase5_report_truth.v2"
_ORIGINAL_NORMALIZED_SCANNER_RECORD = base._normalized_scanner_record
_ORIGINAL_RECONCILE = base.reconcile_phase5_report_truth
_ORIGINAL_CONTEXT_FROM_MAPPING = base._context_from_mapping
_STATUS_ALIASES = {
    "complete": "completed",
    "completed": "completed",
    "success": "completed",
    "passed": "completed",
    "failure": "failed",
    "error": "failed",
    "timed-out": "timeout",
    "timed_out": "timeout",
    "incomplete": "partial",
}
_STALE_STATUS_MARKERS = (
    "failed",
    "partial",
    "unavailable",
    "incomplete",
    "did not produce",
    "not complete",
    "execution coverage",
)


def _find_commit(value: Any) -> str:
    if isinstance(value, dict):
        checkout = value.get("checkout") if isinstance(value.get("checkout"), dict) else {}
        provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
        for candidate in (
            value.get("target_commit_sha"),
            value.get("snapshot_commit_sha"),
            value.get("commit_sha"),
            checkout.get("commit_sha"),
            provenance.get("target_commit_sha"),
        ):
            commit = base._sha(candidate)
            if commit:
                return commit
        for child in value.values():
            commit = _find_commit(child)
            if commit:
                return commit
    elif isinstance(value, list):
        for child in value:
            commit = _find_commit(child)
            if commit:
                return commit
    return ""


def _find_tracked_complexity(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        metrics = value.get("tracked_function_metrics")
        exact = value.get("tracked_function_metrics_are_exact_sha")
        if isinstance(metrics, dict) and exact is True:
            return {
                str(name): dict(item)
                for name, item in metrics.items()
                if isinstance(item, dict) and item.get("cyclomatic_complexity") is not None
            }
        for child in value.values():
            found = _find_tracked_complexity(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_tracked_complexity(child)
            if found:
                return found
    return {}


def _find_ci_summary(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("schema") == "nico.ci_history_summary.v1":
            return value
        for child in value.values():
            found = _find_ci_summary(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_ci_summary(child)
            if found is not None:
                return found
    return None


def _context_from_mapping_v2(value: dict[str, Any], inherited: dict[str, str]) -> dict[str, str]:
    context = _ORIGINAL_CONTEXT_FROM_MAPPING(value, inherited)
    commit = base._sha(value.get("commit_sha"))
    if commit:
        context["commit_sha"] = commit
    return context


def _normalized_scanner_record_v2(
    tool: str,
    payload: dict[str, Any],
    *,
    context: dict[str, str],
    path: str,
    target_commit: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload)
    original_status = str(payload.get("status") or "").strip().casefold()
    normalized_payload["status"] = _STATUS_ALIASES.get(original_status, original_status)

    # Status aliases are normalized, but proof fields are never inferred from status.
    record = _ORIGINAL_NORMALIZED_SCANNER_RECORD(
        tool,
        normalized_payload,
        context=context,
        path=path,
        target_commit=target_commit,
    )
    record["source_status"] = original_status or "unknown"
    return record


def _phase5_outcomes_evidence_only(
    assessment: dict[str, Any],
    scanners: dict[str, dict[str, Any]],
    ci_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    current_scanners = {
        tool: record["status"] if not record["execution_complete"] else "completed"
        for tool, record in sorted(scanners.items())
    }
    scanner_changes = {
        tool: {"before": before, "after": current_scanners[tool]}
        for tool, before in base.BASELINE["scanner_statuses"].items()
        if tool in current_scanners and current_scanners[tool] != before
    }
    unobserved = sorted(tool for tool in base.BASELINE["scanner_statuses"] if tool not in current_scanners)

    tracked = assessment.get("phase5_tracked_complexity_metrics")
    tracked = tracked if isinstance(tracked, dict) else {}
    current_complexity = base._complexity_snapshot(assessment)
    for name, item in tracked.items():
        if isinstance(item, dict) and item.get("cyclomatic_complexity") is not None:
            current_complexity[str(name)] = int(item["cyclomatic_complexity"])
    complexity_changes = {
        name: {
            "before": before,
            "after": current_complexity[name],
            "delta": current_complexity[name] - before,
            "evidence": tracked.get(name) if isinstance(tracked.get(name), dict) else None,
        }
        for name, before in base.BASELINE["complexity"].items()
        if name in current_complexity and current_complexity[name] != before
    }
    tls_open = any(
        "tls_verify_disabled" in base._text(item.get("title")).casefold()
        for item in assessment.get("findings_register") or []
        if isinstance(item, dict)
    )
    health = assessment.get("evidence_health_summary")
    current_commit = health.get("target_commit_sha") if isinstance(health, dict) else ""
    return {
        "schema": VERSION,
        "baseline_commit_sha": base.BASELINE["commit_sha"],
        "current_commit_sha": current_commit,
        "scanner_status_changes": scanner_changes,
        "current_scanner_statuses": current_scanners,
        "unobserved_baseline_scanners": unobserved,
        "missing_scanner_records_count_as_changes": False,
        "ci_history_classification_visible": ci_summary is not None,
        "tls_verify_disabled_finding_open": tls_open,
        "complexity_changes": complexity_changes,
        "tracked_complexity_metrics_retained": bool(tracked),
        "unchanged_complexity_hotspots": sorted(
            name
            for name, before in base.BASELINE["complexity"].items()
            if current_complexity.get(name) == before
        ),
        "truth_rule": (
            "Only exact-SHA retained evidence changes report outcomes; missing records are not improvements, "
            "and unchanged risks remain visible."
        ),
    }


def _remove_stale_scanner_status_text(assessment: dict[str, Any]) -> None:
    health = assessment.get("evidence_health_summary")
    if not isinstance(health, dict):
        return
    records = health.get("scanner_records")
    if not isinstance(records, dict):
        return
    completed = {
        tool
        for tool, record in records.items()
        if isinstance(record, dict) and record.get("execution_complete") is True
    }
    if not completed:
        return

    for section in assessment.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for field in ("evidence", "findings", "unavailable"):
            values = section.get(field)
            if not isinstance(values, list):
                continue
            retained: list[Any] = []
            for value in values:
                text = base._text(value).casefold()
                stale = any(tool in text for tool in completed) and any(
                    marker in text for marker in _STALE_STATUS_MARKERS
                )
                if not stale:
                    retained.append(value)
            section[field] = retained

        category = {
            "dependency_health": "dependency",
            "static_analysis": "static",
            "secrets_review": "secret",
        }.get(str(section.get("id") or ""))
        if not category:
            continue
        category_records = [
            record
            for record in records.values()
            if isinstance(record, dict) and record.get("category") == category
        ]
        if category_records and all(record.get("execution_complete") is True for record in category_records):
            section["scanner_execution_status"] = "complete_exact_sha"
            section.setdefault("evidence", []).append(
                "All observed required scanners in this control completed with retained exact-SHA artifacts."
            )


def _ensure_ci_classification_visible(assessment: dict[str, Any], stage_results: dict[str, Any]) -> None:
    summary = _find_ci_summary(stage_results)
    if not isinstance(summary, dict):
        return
    historical = summary.get("historical_reliability")
    historical = historical if isinstance(historical, dict) else {}
    counts = historical.get("classified_counts")
    counts = counts if isinstance(counts, dict) else {}
    classification_line = "Workflow outcome classes: " + "; ".join(
        f"{key}={value}" for key, value in sorted(counts.items())
    )
    if classification_line.endswith(": "):
        classification_line += "No classified workflow outcomes retained."

    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    ci_section = next((item for item in sections if item.get("id") == "ci_cd"), None)
    if ci_section is not None:
        evidence = [str(item) for item in ci_section.get("evidence") or []]
        if not any(item.startswith("Workflow outcome classes:") for item in evidence):
            evidence.append(classification_line)
        ci_section["evidence"] = evidence
        ci_section["historical_reliability_classified"] = True

    phase5_section = next((item for item in sections if item.get("id") == "phase5_verified_outcomes"), None)
    if phase5_section is not None:
        evidence = [str(item) for item in phase5_section.get("evidence") or []]
        if not any(item.startswith("Workflow outcome classes:") for item in evidence):
            evidence.append(classification_line)
        phase5_section["evidence"] = evidence

    assessment["ci_history_classification"] = deepcopy(summary)


def reconcile_phase5_report_truth(
    assessment: dict[str, Any],
    stage_results: dict[str, Any],
) -> dict[str, Any]:
    target_commit = _find_commit(stage_results)
    tracked = _find_tracked_complexity(stage_results)
    assessment_input = deepcopy(assessment)
    if tracked:
        assessment_input["phase5_tracked_complexity_metrics"] = tracked
    if not target_commit:
        result = _ORIGINAL_RECONCILE(assessment_input, stage_results)
    else:
        enriched = {"phase5_exact_identity": {"commit_sha": target_commit}, **deepcopy(stage_results)}
        result = _ORIGINAL_RECONCILE(assessment_input, enriched)
    _remove_stale_scanner_status_text(result)
    _ensure_ci_classification_visible(result, stage_results)
    return result


def install_phase5_report_truth_v2() -> dict[str, Any]:
    base._context_from_mapping = _context_from_mapping_v2
    base._normalized_scanner_record = _normalized_scanner_record_v2
    base._phase5_outcomes = _phase5_outcomes_evidence_only
    base.reconcile_phase5_report_truth = reconcile_phase5_report_truth
    result = dict(base.install_phase5_report_truth_v1())
    result.update(
        {
            "status": "installed",
            "version": VERSION,
            "scanner_status_aliases_normalized": True,
            "nested_exact_commit_discovery": True,
            "plain_stage_commit_propagation": True,
            "missing_scanner_records_are_not_changes": True,
            "only_observed_exact_sha_scanner_deltas_rendered": True,
            "stale_scanner_failure_text_removed_only_after_proof": True,
            "exact_tracked_complexity_metrics_rendered": True,
            "classified_ci_outcomes_always_visible": True,
        }
    )
    return result


BASELINE = base.BASELINE
scan_files_executable_only = base.scan_files_executable_only

__all__ = [
    "VERSION",
    "BASELINE",
    "scan_files_executable_only",
    "reconcile_phase5_report_truth",
    "install_phase5_report_truth_v2",
]
