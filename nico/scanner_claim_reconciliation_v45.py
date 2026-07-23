from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.scanner_claim_reconciliation.v45"
_PATCH_MARKER = "_nico_scanner_claim_reconciliation_v45"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _ledger(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    block = payload.get("scanner_assurance_ledger")
    analyzers = block.get("analyzers") if isinstance(block, dict) else []
    return {
        _text(item.get("tool")).casefold(): item
        for item in analyzers or []
        if isinstance(item, dict) and _text(item.get("tool"))
    }


def _candidate_count(tool: dict[str, Any]) -> int:
    for key in ("deduplicated_candidate_count", "raw_candidate_count"):
        value = tool.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    return 0


def _dependency_scope(section: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    osv = tools.get("osv-scanner") or {}
    candidates = _candidate_count(osv)
    if candidates <= 0:
        return
    evidence: list[str] = []
    replaced = False
    query_count = 0
    for raw in section.get("evidence") or []:
        value = _text(raw)
        match = re.search(r"OSV returned no vulnerability records for (\d+) pinned dependency", value, re.I)
        if match:
            query_count = int(match.group(1))
            evidence.append(
                f"Direct pinned-package OSV queries returned no vulnerability records for {query_count} query/queries. "
                f"The separate repository-wide OSV scanner returned {candidates} review-only candidate(s); the scopes are not interchangeable."
            )
            replaced = True
        else:
            evidence.append(value)
    if not replaced:
        evidence.append(
            f"Repository-wide OSV scanner returned {candidates} review-only candidate(s). "
            "This result is distinct from direct pinned-package vulnerability queries."
        )
    findings = [
        _text(item)
        for item in section.get("findings") or []
        if "scanner-worker dependency tools reported" not in _text(item).casefold()
    ]
    findings.append(
        f"Repository-wide OSV scanner returned {candidates} candidate(s) requiring package, manifest, and exact-location triage; candidates are not confirmed vulnerabilities."
    )
    section["evidence"] = _unique(evidence)
    section["findings"] = _unique(findings)
    section["osv_scope_reconciled"] = True


def _secret_timeout(section: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    gitleaks = tools.get("gitleaks") or {}
    if _text(gitleaks.get("lifecycle_result")).casefold() != "timed_out":
        return
    candidates = _candidate_count(gitleaks)
    findings: list[str] = []
    for raw in section.get("findings") or []:
        value = _text(raw)
        lowered = value.casefold()
        parsed = re.search(r"parsed gitleaks artifact reported (\d+).+finding", value, re.I)
        if parsed:
            count = int(parsed.group(1))
            findings.append(
                f"Partial Gitleaks output contained {count} review-only candidate(s) before timeout; they are not verified secret findings or clean evidence."
            )
        elif "gitleaks" in lowered and "finding" in lowered:
            findings.append(
                f"Gitleaks timed out with {candidates} retained review-only candidate(s); no verified finding or clean conclusion is permitted."
            )
        else:
            findings.append(value)
    if not any("gitleaks timed out" in item.casefold() or "partial gitleaks" in item.casefold() for item in findings):
        findings.append(
            f"Gitleaks timed out with {candidates} retained review-only candidate(s); no verified finding or clean conclusion is permitted."
        )
    section["findings"] = _unique(findings)
    section["gitleaks_partial_artifact_disposition"] = "review_only_timeout"


def _static_execution(section: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    bandit = tools.get("bandit") or {}
    eslint = tools.get("eslint") or {}
    bandit_failed = _text(bandit.get("lifecycle_result")).casefold() == "failed"
    eslint_not_configured = _text(eslint.get("lifecycle_result")).casefold() == "not_configured"
    if not bandit_failed and not eslint_not_configured:
        return

    evidence: list[str] = []
    for raw in section.get("evidence") or []:
        value = _text(raw)
        lowered = value.casefold()
        if bandit_failed and (
            "current-run bandit, semgrep, eslint, and typescript artifacts are complete" in lowered
            or "clean bandit triage supersedes" in lowered
            or "canonical scanner disposition: bandit=unknown" in lowered
        ):
            continue
        if eslint_not_configured and "canonical scanner disposition: eslint=unknown" in lowered:
            continue
        evidence.append(value)
    if bandit_failed:
        evidence.append(
            "Live Bandit execution failed for this exact run. Attached Bandit triage records remain diagnostic and cannot establish a clean or completed Bandit result."
        )
    if eslint_not_configured:
        evidence.append(
            "ESLint is not configured for this repository snapshot and is classified as not configured, not as a failed analyzer. TypeScript remains independently evaluated."
        )

    unavailable: list[str] = []
    for raw in section.get("unavailable") or []:
        value = _text(raw)
        if eslint_not_configured and "eslint" in value.casefold():
            continue
        unavailable.append(value)
    section["evidence"] = _unique(evidence)
    section["unavailable"] = _unique(unavailable)
    section["bandit_execution_disposition"] = "failed_review_only" if bandit_failed else "not_requested"
    section["eslint_execution_disposition"] = "not_configured" if eslint_not_configured else "requested"


def _copy_defects(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("Authorized I human reviewer", "Authorized human reviewer")
    if isinstance(value, list):
        return [_copy_defects(item) for item in value]
    if isinstance(value, dict):
        return {key: _copy_defects(item) for key, item in value.items()}
    return value


def reconcile_scanner_claims_v45(payload: dict[str, Any]) -> dict[str, Any]:
    tools = _ledger(payload)
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id in {"dependency_health", "dependency_library_ecosystem"}:
            _dependency_scope(section, tools)
        elif section_id == "secrets_review":
            _secret_timeout(section, tools)
        elif section_id == "static_analysis":
            _static_execution(section, tools)
    payload["scanner_claim_reconciliation"] = {
        "status": "complete",
        "version": VERSION,
        "osv_scope_separated": True,
        "failed_bandit_never_described_as_complete": True,
        "gitleaks_timeout_candidates_are_review_only": True,
        "eslint_not_configured_is_not_failure": True,
        "confirmed_findings_not_inferred_from_candidate_counts": True,
    }
    return _copy_defects(payload)


def install_scanner_claim_reconciliation_v45() -> dict[str, Any]:
    from nico import express_truth_calibration_v36 as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target.calibrate_express_truth
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def calibrate(payload: dict[str, Any]) -> dict[str, Any]:
        return reconcile_scanner_claims_v45(current(payload))

    setattr(calibrate, _PATCH_MARKER, True)
    setattr(calibrate, "_nico_previous", current)
    target.calibrate_express_truth = calibrate
    return {
        "status": "installed",
        "version": VERSION,
        "cross_tool_claims_reconciled": True,
        "candidate_counts_are_not_confirmed_findings": True,
    }


__all__ = [
    "VERSION",
    "install_scanner_claim_reconciliation_v45",
    "reconcile_scanner_claims_v45",
]
