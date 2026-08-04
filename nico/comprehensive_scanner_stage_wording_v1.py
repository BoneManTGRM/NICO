from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive-scanner-stage-wording.v1"
_MARKER = "__nico_comprehensive_scanner_stage_wording_v1__"


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _register(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    value = assessment.get("canonical_scanner_finding_register")
    if not isinstance(value, Mapping):
        value = canonical.get("canonical_scanner_finding_register")
    return value if isinstance(value, Mapping) else {}


def _summary_for_scanner(register: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    summary = register.get("summary_by_scanner")
    if not isinstance(summary, Mapping):
        return {}
    raw = summary.get(name.casefold()) or summary.get(name)
    return raw if isinstance(raw, Mapping) else {}


def scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    from nico.v2_premium_report_renderer import _stage

    records = [
        item for item in canonical.get("scanner_execution_records") or []
        if isinstance(item, Mapping)
    ]
    register = _register(canonical)
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    evidence: list[str] = []
    for item in records:
        scanner_name = _text(item.get("scanner_name") or item.get("tool"), 160)
        summary = _summary_for_scanner(register, scanner_name)
        material = _integer(summary.get("material"))
        review_required = _integer(summary.get("review_required"))
        raw_count = _integer(summary.get("raw"))
        payload_state = (
            "retained"
            if item.get("raw_artifact_retention_complete") is True
            or item.get("raw_payload_retention_complete") is True
            or item.get("findings")
            else "count-only"
            if raw_count or item.get("finding_count") not in (None, "")
            else "unavailable"
        )
        evidence.append(
            f"{scanner_name}: execution={_text(item.get('state') or item.get('status') or 'unknown')}; "
            f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
            f"artifact={'retained' if item.get('artifact_hash') or item.get('artifact_sha256') else 'missing'}; "
            f"confirmed material findings={material}; review-required candidates={review_required}; "
            f"raw candidates={raw_count}; raw candidate payload={payload_state}"
        )
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner execution evidence incomplete')}"
        for item in incomplete
    ]
    material_total = _integer(totals.get("material"))
    review_total = _integer(totals.get("review_required"))
    raw_total = _integer(totals.get("raw"))
    summary = (
        f"Scanner execution: {len(completed)}/{len(records)} complete. "
        f"Candidate disposition: {review_total} pending human review from {raw_total} raw candidates. "
        f"Confirmed material findings: {material_total}. Scanner completion does not equal candidate approval."
    )
    return [
        _stage(
            "dependency_security_static_analysis",
            "Dependency, Security, and Static Analysis",
            summary,
            evidence=evidence,
            unavailable=limitations,
            status="complete" if not incomplete else "review_required",
        )
    ]


def install_comprehensive_scanner_stage_wording_v1() -> dict[str, Any]:
    from nico import v2_premium_report_renderer as renderer

    current = renderer._scanner_stages
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "execution_and_disposition_separated": True,
        }
    setattr(scanner_stages, _MARKER, True)
    setattr(scanner_stages, "_nico_previous", current)
    renderer._scanner_stages = scanner_stages
    return {
        "status": "installed",
        "version": VERSION,
        "execution_and_disposition_separated": True,
        "ambiguous_retained_finding_count_removed": True,
        "raw_payload_state_disclosed": True,
        "scanner_completion_not_candidate_approval": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_scanner_stage_wording_v1",
    "scanner_stages",
]
