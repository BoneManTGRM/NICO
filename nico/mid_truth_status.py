from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

VERIFIED = "Verified"
VERIFIED_WITH_LIMITATIONS = "Verified with limitations"
UNAVAILABLE = "Unavailable"
FAILED = "Failed"
HUMAN_REVIEW_REQUIRED = "Human review required"
ALLOWED_SECTION_STATUSES = {
    VERIFIED,
    VERIFIED_WITH_LIMITATIONS,
    UNAVAILABLE,
    FAILED,
    HUMAN_REVIEW_REQUIRED,
}

DEPENDENCY_TOOLS = {"pip-audit", "npm-audit", "osv-scanner"}
SECRET_TOOLS = {"gitleaks", "trufflehog", "credential-scan"}
STATIC_TOOLS = {"bandit", "semgrep", "eslint", "typescript"}
TECHNICAL_SECTION_IDS = {
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
}
_SCOPE_DISCLOSURE_MARKERS = (
    "does not replace",
    "does not prove",
    "not proof that",
    "clean scanner result",
    "clean scanner execution",
    "human review is still required",
    "human triage",
    "story-point expectations",
    "developer seniority",
    "review quality",
    "business-value delivery",
    "outside the scanned repository history",
    "time-window operational evidence",
    "not exact-commit code evidence",
)
_ARCHITECTURE_SUPERSEDED_MARKERS = (
    "call-graph, coupling, duplication, and cyclomatic-complexity conclusions require language-specific analyzer output",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _tool_set(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _coverage_unit(unit_id: str, label: str, available: bool, evidence: str, limitation: str = "") -> dict[str, Any]:
    return {
        "id": unit_id,
        "label": label,
        "available": bool(available),
        "status": VERIFIED if available and not limitation else VERIFIED_WITH_LIMITATIONS if available else UNAVAILABLE,
        "evidence": evidence if available else "",
        "limitation": limitation if available else limitation or f"{label} evidence is unavailable for this run.",
    }


def _ensure_mid_evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    assessment = _dict(result.get("assessment"))
    existing = _dict(assessment.get("evidence_ledger")) or _dict(result.get("evidence_ledger"))
    if existing.get("entry_count"):
        result["evidence_ledger"] = existing
        if assessment:
            assessment["evidence_ledger"] = existing
            result["assessment"] = assessment
        return existing

    snapshot = _dict(result.get("repository_snapshot"))
    repository = _dict(result.get("repository_evidence"))
    complexity = _dict(result.get("complexity_evidence"))
    scanner = _dict(result.get("scanner_evidence")) or _dict(result.get("scanner"))
    entries: list[dict[str, Any]] = []

    def add(entry_id: str, source: str, available: bool, reference: Any) -> None:
        entries.append(
            {
                "entry_id": entry_id,
                "source": source,
                "status": "verified" if available else "unavailable",
                "reference_hash": _hash(reference) if available else "",
            }
        )

    add("repository_snapshot", "repository_snapshot", snapshot.get("status") == "attached", snapshot)
    add("repository_evidence", "repository_evidence", repository.get("status") == "attached", repository)
    add("complexity_evidence", "complexity_evidence", complexity.get("status") in {"attached", "available", "complete"}, complexity)
    add("scanner_evidence", "scanner_evidence", scanner.get("status") in {"attached", "complete"}, scanner)
    for tool in sorted(_tool_set(scanner, "tools_requested")):
        available = tool in _tool_set(scanner, "tools_run")
        add(f"scanner_tool:{tool}", "scanner_tool", available, {"tool": tool, "scan_id": scanner.get("scan_id")})
    for section in _list(assessment.get("sections")):
        if not isinstance(section, dict) or not section.get("id"):
            continue
        evidence = [str(item) for item in _list(section.get("evidence")) if str(item).strip()]
        add(f"section:{section.get('id')}", "section_evidence", bool(evidence), evidence)

    verified = sum(1 for item in entries if item["status"] == "verified")
    unavailable = len(entries) - verified
    ledger = {
        "status": "complete" if entries and unavailable == 0 else "partial" if entries else "unavailable",
        "entry_count": len(entries),
        "verified_entry_count": verified,
        "unavailable_entry_count": unavailable,
        "entries": entries,
        "ledger_hash": _hash(entries),
        "run_id": result.get("run_id") or "",
        "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        "generated_from_attached_evidence_only": True,
        "human_review_required": True,
    }
    result["evidence_ledger"] = ledger
    if assessment:
        assessment["evidence_ledger"] = ledger
        result["assessment"] = assessment
    return ledger


def build_mid_evidence_coverage(result: dict[str, Any]) -> dict[str, Any]:
    """Calculate coverage from twelve explicit evidence units, never from a score."""

    ledger = _ensure_mid_evidence_ledger(result)
    snapshot = _dict(result.get("repository_snapshot"))
    repository = _dict(result.get("repository_evidence"))
    complexity = _dict(result.get("complexity_evidence"))
    scanner = _dict(result.get("scanner_evidence")) or _dict(result.get("scanner"))

    files = _dict(repository.get("file_evidence"))
    dependencies = _dict(repository.get("dependency_evidence"))
    workflows = _dict(repository.get("workflow_evidence"))
    activity = _dict(repository.get("activity_evidence"))
    tools_run = _tool_set(scanner, "tools_run")
    failed_tools = _tool_set(scanner, "failed_tools") | _tool_set(scanner, "timed_out_tools")
    unavailable_tools = _tool_set(scanner, "unavailable_tools")

    units = [
        _coverage_unit(
            "repository_snapshot",
            "Exact repository snapshot",
            snapshot.get("status") == "attached" and len(str(snapshot.get("commit_sha") or "")) >= 40,
            f"snapshot_id={snapshot.get('snapshot_id')}; commit_sha={snapshot.get('commit_sha')}",
        ),
        _coverage_unit(
            "repository_files",
            "Snapshot-bound repository files",
            repository.get("status") == "attached" and _count(files.get("files_profiled")) > 0,
            f"files_profiled={_count(files.get('files_profiled'))}; snapshot_sha={repository.get('snapshot_commit_sha')}",
            "Coverage is bounded to readable sampled files from the captured commit." if _count(files.get("files_profiled")) > 0 else "",
        ),
        _coverage_unit(
            "dependency_manifests",
            "Dependency manifests and entries",
            bool(dependencies.get("manifest_paths")) or _count(dependencies.get("dependency_entries")) > 0,
            f"manifests={len(_list(dependencies.get('manifest_paths')))}; dependency_entries={_count(dependencies.get('dependency_entries'))}",
        ),
        _coverage_unit(
            "workflow_configuration",
            "Snapshot-bound workflow configuration",
            _count(workflows.get("workflow_file_count")) > 0,
            f"workflow_files={_count(workflows.get('workflow_file_count'))}; snapshot_sha={workflows.get('workflow_configuration_snapshot_sha')}",
        ),
        _coverage_unit(
            "ci_runtime",
            "CI job or deployment runtime evidence",
            _count(workflows.get("jobs_observed")) > 0 or _count(workflows.get("deployments_observed")) > 0,
            f"jobs={_count(workflows.get('jobs_observed'))}; deployments={_count(workflows.get('deployments_observed'))}",
            "Runtime history is time-window operational evidence and may include commits other than the captured snapshot.",
        ),
        _coverage_unit(
            "activity_history",
            "Commit and pull-request activity evidence",
            _count(activity.get("commits_returned")) > 0 or _count(activity.get("pull_requests_returned")) > 0,
            f"commits={_count(activity.get('commits_returned'))}; pull_requests={_count(activity.get('pull_requests_returned'))}",
            "Activity is time-window operational evidence, not exact-commit code evidence.",
        ),
        _coverage_unit(
            "complexity_measurement",
            "Snapshot-bound complexity measurement",
            complexity.get("status") in {"attached", "available", "complete"} and _count(complexity.get("files_analyzed")) > 0,
            f"files_analyzed={_count(complexity.get('files_analyzed'))}; snapshot_sha={complexity.get('snapshot_commit_sha')}",
            "Complexity covers readable source files from the captured commit and records parser limitations separately.",
        ),
        _coverage_unit(
            "snapshot_scanner_match",
            "Scanner execution on exact snapshot",
            scanner.get("status") in {"attached", "complete"} and scanner.get("snapshot_match") is True,
            f"scan_id={scanner.get('scan_id')}; snapshot_match={scanner.get('snapshot_match')}",
            "Scanner evidence remains unavailable until the worker proves exact commit checkout." if scanner.get("snapshot_match") is not True else "",
        ),
        _coverage_unit(
            "dependency_scanners",
            "Dependency vulnerability scanners",
            bool(tools_run & DEPENDENCY_TOOLS),
            f"completed_tools={sorted(tools_run & DEPENDENCY_TOOLS)}",
            f"failed_or_unavailable={sorted((failed_tools | unavailable_tools) & DEPENDENCY_TOOLS)}" if (failed_tools | unavailable_tools) & DEPENDENCY_TOOLS else "",
        ),
        _coverage_unit(
            "secret_scanners",
            "Secrets and credential scanners",
            bool(tools_run & SECRET_TOOLS),
            f"completed_tools={sorted(tools_run & SECRET_TOOLS)}; full_history_verified={sorted(_tool_set(scanner, 'full_history_verified_tools') & SECRET_TOOLS)}",
            f"failed_or_unavailable={sorted((failed_tools | unavailable_tools) & SECRET_TOOLS)}" if (failed_tools | unavailable_tools) & SECRET_TOOLS else "",
        ),
        _coverage_unit(
            "static_scanners",
            "Static-analysis scanners",
            bool(tools_run & STATIC_TOOLS),
            f"completed_tools={sorted(tools_run & STATIC_TOOLS)}",
            f"failed_or_unavailable={sorted((failed_tools | unavailable_tools) & STATIC_TOOLS)}" if (failed_tools | unavailable_tools) & STATIC_TOOLS else "",
        ),
        _coverage_unit(
            "evidence_ledger",
            "Evidence ledger",
            ledger.get("status") in {"available", "partial", "complete"} and _count(ledger.get("entry_count")) > 0,
            f"status={ledger.get('status')}; entries={_count(ledger.get('entry_count'))}; verified_entries={_count(ledger.get('verified_entry_count'))}",
            f"unavailable_entries={_count(ledger.get('unavailable_entry_count'))}" if _count(ledger.get("unavailable_entry_count")) else "",
        ),
    ]
    available = sum(1 for unit in units if unit["available"])
    total = len(units)
    percent = round((available / total) * 100) if total else 0
    return {
        "label": "Automated evidence coverage",
        "calculated": True,
        "percent": percent,
        "numerator": available,
        "denominator": total,
        "units": units,
        "method": "Percentage of twelve explicit evidence units available for this exact Mid run. Maturity scores do not affect coverage.",
        "snapshot_bound_units": ["repository_snapshot", "repository_files", "dependency_manifests", "workflow_configuration", "complexity_measurement", "snapshot_scanner_match", "dependency_scanners", "secret_scanners", "static_scanners", "evidence_ledger"],
        "time_window_units": ["ci_runtime", "activity_history"],
    }


def _technical_source_state(section_id: str, coverage_by_id: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    requirements = {
        "code_audit": (["repository_snapshot", "repository_files"], ["activity_history"]),
        "dependency_health": (["dependency_manifests"], ["dependency_scanners"]),
        "secrets_review": (["secret_scanners"], ["repository_files"]),
        "static_analysis": (["static_scanners"], ["repository_files"]),
        "ci_cd": (["workflow_configuration"], ["ci_runtime"]),
        "architecture_debt": (["repository_files", "complexity_measurement"], []),
        "velocity_complexity": (["complexity_measurement", "activity_history"], ["ci_runtime"]),
    }
    primary, secondary = requirements.get(section_id, ([], []))
    missing_primary = [item for item in primary if not coverage_by_id.get(item, {}).get("available")]
    missing_secondary = [item for item in secondary if not coverage_by_id.get(item, {}).get("available")]
    if missing_primary:
        return UNAVAILABLE, missing_primary + missing_secondary
    if missing_secondary:
        return VERIFIED_WITH_LIMITATIONS, missing_secondary
    return VERIFIED, []


def _is_scope_disclosure(note: str) -> bool:
    lower = str(note or "").strip().lower()
    return any(marker in lower for marker in _SCOPE_DISCLOSURE_MARKERS)


def _technical_sections(result: dict[str, Any], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    assessment = _dict(result.get("assessment"))
    sections = [
        item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and str(item.get("id") or "") in TECHNICAL_SECTION_IDS
    ]
    coverage_by_id = {str(item.get("id")): item for item in _list(coverage.get("units")) if isinstance(item, dict)}
    scanner = _dict(result.get("scanner_evidence")) or _dict(result.get("scanner"))
    failed_tools = _tool_set(scanner, "failed_tools") | _tool_set(scanner, "timed_out_tools")
    output: list[dict[str, Any]] = []
    for original in sections:
        section = deepcopy(original)
        section_id = str(section.get("id") or "unknown")
        status, missing_sources = _technical_source_state(section_id, coverage_by_id)
        evidence = [str(item) for item in _list(section.get("evidence")) if str(item).strip()]
        raw_limitations = [str(item) for item in _list(section.get("unavailable")) if str(item).strip()]
        if section_id == "architecture_debt" and coverage_by_id.get("complexity_measurement", {}).get("available"):
            raw_limitations = [
                item for item in raw_limitations
                if not any(marker in item.lower() for marker in _ARCHITECTURE_SUPERSEDED_MARKERS)
            ]
        scope_disclosures = [item for item in raw_limitations if _is_scope_disclosure(item)]
        material_limitations = [item for item in raw_limitations if item not in scope_disclosures]
        relevant_failures: set[str] = set()
        if section_id == "dependency_health":
            relevant_failures = failed_tools & DEPENDENCY_TOOLS
        elif section_id == "secrets_review":
            relevant_failures = failed_tools & SECRET_TOOLS
        elif section_id == "static_analysis":
            relevant_failures = failed_tools & STATIC_TOOLS
        if relevant_failures and status == UNAVAILABLE:
            status = FAILED
        elif relevant_failures and status == VERIFIED:
            status = VERIFIED_WITH_LIMITATIONS
        if status == VERIFIED and material_limitations:
            status = VERIFIED_WITH_LIMITATIONS
        section["truth_status"] = status
        section["truth_status_slug"] = status.lower().replace(" ", "_")
        section["direct_evidence_count"] = len(evidence)
        section["limitation_count"] = len(material_limitations) + len(missing_sources) + len(relevant_failures)
        section["scope_disclosure_count"] = len(scope_disclosures)
        section["scope_disclosures"] = scope_disclosures
        section["unavailable"] = material_limitations
        section["missing_evidence_sources"] = missing_sources
        section["failed_evidence_tools"] = sorted(relevant_failures)
        section["human_review_required"] = status in {VERIFIED_WITH_LIMITATIONS, FAILED, HUMAN_REVIEW_REQUIRED}
        section["unsupported_claims_permitted"] = False
        output.append(section)
    return output


def _external_sections(optional: dict[str, Any]) -> list[dict[str, Any]]:
    availability = _dict(optional.get("section_availability"))
    output: list[dict[str, Any]] = []
    for section_id, value in availability.items():
        item = _dict(value)
        submitted = [str(field) for field in _list(item.get("submitted_fields"))]
        status = HUMAN_REVIEW_REQUIRED if submitted else UNAVAILABLE
        output.append(
            {
                "id": str(section_id),
                "label": str(item.get("section") or section_id).replace("_", " ").title(),
                "score": None,
                "status": "gray",
                "truth_status": status,
                "truth_status_slug": status.lower().replace(" ", "_"),
                "summary": str(item.get("message") or "External evidence is unavailable."),
                "evidence": [f"User submitted field: {field}" for field in submitted],
                "findings": [],
                "unavailable": [] if submitted else [str(item.get("message") or "Required external evidence was not supplied.")],
                "scope_disclosures": ["User-submitted context requires human validation and does not automatically change the technical score."],
                "source_classification": "user_submitted_external_context" if submitted else "unavailable",
                "direct_repository_proof": False,
                "direct_evidence_count": len(submitted),
                "limitation_count": 1,
                "human_review_required": bool(submitted),
                "unsupported_claims_permitted": False,
                "score_change_allowed_without_review": False,
            }
        )
    return output


def build_mid_truth_status(result: dict[str, Any]) -> dict[str, Any]:
    coverage = build_mid_evidence_coverage(result)
    optional = _dict(result.get("optional_evidence"))
    technical = _technical_sections(result, coverage)
    external = _external_sections(optional)
    sections = technical + external
    counts = {status: sum(1 for item in sections if item.get("truth_status") == status) for status in ALLOWED_SECTION_STATUSES}
    review_items = [item["id"] for item in sections if item.get("human_review_required")]
    unavailable_sources = sum(len(_list(item.get("missing_evidence_sources"))) + len(_list(item.get("unavailable"))) for item in sections)
    return {
        "version": "mid-truth-status-v2",
        "allowed_statuses": [VERIFIED, VERIFIED_WITH_LIMITATIONS, UNAVAILABLE, FAILED, HUMAN_REVIEW_REQUIRED],
        "sections": sections,
        "summary": {
            "section_count": len(sections),
            "verified": counts[VERIFIED],
            "verified_with_limitations": counts[VERIFIED_WITH_LIMITATIONS],
            "unavailable": counts[UNAVAILABLE],
            "failed": counts[FAILED],
            "human_review_required": counts[HUMAN_REVIEW_REQUIRED],
            "items_requiring_review": len(review_items),
            "unavailable_evidence_sources": unavailable_sources,
            "scope_disclosures": sum(len(_list(item.get("scope_disclosures"))) for item in sections),
            "unsupported_claims_permitted": 0,
        },
        "review_item_ids": review_items,
        "evidence_coverage": coverage,
        "human_approval_required": True,
        "unsupported_claims_permitted": 0,
        "rule": "Missing or failed evidence cannot be represented as clean. General epistemic caveats remain disclosed but do not downgrade otherwise complete evidence to unavailable or limited.",
    }


def attach_mid_truth_status(result: dict[str, Any]) -> dict[str, Any]:
    truth = build_mid_truth_status(result)
    result["mid_truth_status"] = truth
    result["evidence_coverage"] = truth["evidence_coverage"]
    assessment = _dict(result.get("assessment"))
    if assessment:
        assessment["sections"] = truth["sections"]
        assessment["evidence_coverage"] = truth["evidence_coverage"]
        assessment["truth_status_summary"] = truth["summary"]
        assessment["evidence_ledger"] = result.get("evidence_ledger") or assessment.get("evidence_ledger") or {}
        assessment["unsupported_claims_permitted"] = 0
        result["assessment"] = assessment
    result["review_summary"] = {
        "sections_verified": truth["summary"]["verified"],
        "sections_verified_with_limitations": truth["summary"]["verified_with_limitations"],
        "items_require_review": truth["summary"]["items_requiring_review"],
        "unavailable_evidence_sources": truth["summary"]["unavailable_evidence_sources"],
        "scope_disclosures": truth["summary"]["scope_disclosures"],
        "unsupported_claims_permitted": 0,
    }
    return result
