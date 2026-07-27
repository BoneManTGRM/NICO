from __future__ import annotations

from typing import Any

from nico import phase5_report_truth_v1 as base
from nico import phase5_report_truth_v2 as v2

VERSION = "nico.phase5_report_truth.v3"


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
    unobserved_scanners = sorted(
        tool for tool in base.BASELINE["scanner_statuses"] if tool not in current_scanners
    )

    current_complexity = base._complexity_snapshot(assessment)
    complexity_changes = {
        name: {
            "before": before,
            "after": current_complexity[name],
            "delta": current_complexity[name] - before,
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
        "unobserved_baseline_scanners": unobserved_scanners,
        "missing_scanner_records_count_as_changes": False,
        "ci_history_classification_visible": ci_summary is not None,
        "tls_verify_disabled_finding_open": tls_open,
        "complexity_changes": complexity_changes,
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


def install_phase5_report_truth_v3() -> dict[str, Any]:
    base._phase5_outcomes = _phase5_outcomes_evidence_only
    result = dict(v2.install_phase5_report_truth_v2())
    result.update(
        {
            "status": "installed",
            "version": VERSION,
            "missing_scanner_records_are_not_changes": True,
            "only_observed_exact_sha_scanner_deltas_rendered": True,
        }
    )
    return result


BASELINE = base.BASELINE
scan_files_executable_only = base.scan_files_executable_only
reconcile_phase5_report_truth = v2.reconcile_phase5_report_truth

__all__ = [
    "VERSION",
    "BASELINE",
    "scan_files_executable_only",
    "reconcile_phase5_report_truth",
    "install_phase5_report_truth_v3",
]
