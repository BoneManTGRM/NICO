from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from nico.mid_score_truth_v3 import (
    _consolidate_review_packet,
    _is_generic_disclosure,
    _ledger_from_result,
)

MID_REPORT_IDENTITY_VERSION = "mid-assessment-draft-v2"
MID_REPORT_PRESENTATION_VERSION = "mid-assessment-decision-ready-v3"
_INSTALLED = False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").split())
        key = text.lower().rstrip(" .;:")
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _material_finding_count(section: dict[str, Any]) -> int:
    return sum(
        _int(_dict(section.get(key)).get("material_finding_count"))
        for key in ("dependency_scanner_triage", "secret_history_triage", "static_triage")
    )


def _presentation_sections(payload: dict[str, Any]) -> None:
    """Attach display fields without changing approval-bound source truth fields."""

    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        unavailable = _unique([
            *_list(section.get("unavailable")),
            *_list(section.get("missing_evidence_sources")),
            *_list(section.get("failed_evidence_tools")),
        ])
        disclosures = [item for item in unavailable if _is_generic_disclosure(item)]
        blockers = [item for item in unavailable if item not in disclosures]
        source_status = str(section.get("truth_status") or "Unavailable")
        direct = section.get("direct_repository_proof") is not False
        material = _material_finding_count(section)
        if (
            source_status not in {"Failed", "Unavailable", "Human review required"}
            and direct
            and not blockers
            and material == 0
        ):
            display_status = "Verified"
        else:
            display_status = source_status
        section["display_truth_status"] = display_status
        section["scope_disclosures"] = _unique([*_list(section.get("scope_disclosures")), *disclosures])
        section["display_blocking_limitations"] = blockers
        section["verification_basis"] = section.get("verification_basis") or "exact-run evidence within the explicitly disclosed assessment scope"


def _presentation_coverage(payload: dict[str, Any], record: dict[str, Any]) -> None:
    response = _dict(record.get("response"))
    ledger = _ledger_from_result(response)
    coverage = deepcopy(_dict(payload.get("evidence_coverage")))
    if ledger and _int(coverage.get("denominator")) > 0:
        units = [deepcopy(item) for item in _list(coverage.get("units")) if isinstance(item, dict)]
        for unit in units:
            if unit.get("id") == "evidence_ledger":
                unit.update(
                    {
                        "available": True,
                        "status": "Verified",
                        "evidence": f"Evidence ledger attached with {_int(ledger.get('entry_count') or len(_list(ledger.get('entries'))))} entry/entries.",
                        "limitation": "",
                    }
                )
        if units:
            numerator = sum(bool(unit.get("available")) for unit in units)
            denominator = len(units)
            coverage["units"] = units
            coverage["numerator"] = numerator
            coverage["denominator"] = denominator
            coverage["percent"] = round(100 * numerator / denominator) if denominator else 0
        elif _int(coverage.get("numerator")) + 1 <= _int(coverage.get("denominator")):
            coverage["numerator"] = _int(coverage.get("numerator")) + 1
            coverage["percent"] = round(100 * coverage["numerator"] / _int(coverage.get("denominator")))
        coverage["evidence_ledger_recovered_for_presentation"] = True
    payload["evidence_coverage"] = coverage
    decision = _dict(payload.get("decision_summary"))
    decision["evidence_coverage_percent"] = coverage.get("percent", 0)
    payload["decision_summary"] = decision
    executive = _dict(payload.get("executive_summary"))
    executive["evidence_coverage"] = f"{coverage.get('percent', 0)}%"
    payload["executive_summary"] = executive


def _presentation_review(payload: dict[str, Any]) -> None:
    review = deepcopy(_dict(payload.get("review_packet")))
    source_packet = {
        "packet_version": review.get("packet_version") or "mid-review-by-exception-v1",
        "review_packet_id": review.get("review_packet_id") or "",
        "review_packet_sha256": review.get("review_packet_sha256") or "",
        "exceptions": deepcopy(_list(review.get("exceptions"))),
        "summary": deepcopy(_dict(review.get("summary"))),
    }
    display = _consolidate_review_packet(source_packet)
    review["source_exception_count"] = len(_list(source_packet.get("exceptions")))
    review["display_exceptions"] = deepcopy(_list(display.get("display_exceptions")))
    review["display_summary"] = deepcopy(_dict(display.get("display_summary")))
    review["display_rule"] = display.get("display_rule") or ""
    # Preserve the original packet version, exception rows, item IDs, and SHA.
    review["packet_version"] = source_packet["packet_version"]
    review["review_packet_id"] = source_packet["review_packet_id"]
    review["review_packet_sha256"] = source_packet["review_packet_sha256"]
    review["exceptions"] = source_packet["exceptions"]
    payload["review_packet"] = review
    decision = _dict(payload.get("decision_summary"))
    decision["review_items"] = int(_dict(display.get("display_summary")).get("items_requiring_review") or 0)
    decision["source_review_items"] = len(_list(source_packet.get("exceptions")))
    decision["duplicate_review_items_removed"] = int(_dict(display.get("display_summary")).get("consolidated_duplicate_items_removed") or 0)
    payload["decision_summary"] = decision
    executive = _dict(payload.get("executive_summary"))
    executive["items_requiring_review"] = decision["review_items"]
    executive["source_review_items"] = decision["source_review_items"]
    payload["executive_summary"] = executive


def _rendering_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a presentation copy; never mutate the JSON evidence contract."""

    rendered = deepcopy(payload)
    for section in _list(rendered.get("sections")):
        if not isinstance(section, dict):
            continue
        section["truth_status"] = section.get("display_truth_status") or section.get("truth_status")
        section["unavailable"] = deepcopy(_list(section.get("display_blocking_limitations")))
        section["missing_evidence_sources"] = []
        section["failed_evidence_tools"] = []
    review = _dict(rendered.get("review_packet"))
    if review.get("display_exceptions") is not None:
        review["exceptions"] = deepcopy(_list(review.get("display_exceptions")))
    rendered["review_packet"] = review
    return rendered


def install_mid_report_v3_compat() -> dict[str, Any]:
    global _INSTALLED
    from nico import mid_assessment_report as report
    from nico import mid_report_v3 as v3

    metadata = {
        "identity_version": MID_REPORT_IDENTITY_VERSION,
        "presentation_version": MID_REPORT_PRESENTATION_VERSION,
        "approval_identity_preserved": True,
        "source_truth_fields_preserved": True,
        "display_review_consolidated": True,
        "generic_scope_disclosures_separated": True,
        "material_findings_preserve_review_status": True,
        "human_review_required": True,
        "client_repository_write_allowed": False,
    }
    if _INSTALLED:
        return {"status": "already_installed", **metadata}

    original_payload: Callable[..., dict[str, Any]] = report._report_payload
    original_markdown: Callable[[dict[str, Any]], str] = report._markdown
    original_html: Callable[[dict[str, Any]], str] = report._html
    original_pdf: Callable[[dict[str, Any]], bytes] = report._pdf

    def compatible_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = deepcopy(original_payload(*args, **kwargs))
        record = args[0] if args and isinstance(args[0], dict) else _dict(kwargs.get("record"))
        payload["report_version"] = MID_REPORT_IDENTITY_VERSION
        payload["presentation_version"] = MID_REPORT_PRESENTATION_VERSION
        payload["approval_identity_contract_changed"] = False
        _presentation_sections(payload)
        _presentation_coverage(payload, record)
        _presentation_review(payload)
        return payload

    def compatible_markdown(payload: dict[str, Any]) -> str:
        value = original_markdown(_rendering_payload(payload))
        value = value.replace("DRAFT - HUMAN REVIEW REQUIRED", report.DRAFT_LABEL)
        return value.replace("## Consolidated human review", "## Review by exception - Consolidated human review")

    def compatible_html(payload: dict[str, Any]) -> str:
        value = original_html(_rendering_payload(payload))
        value = value.replace("DRAFT - HUMAN REVIEW REQUIRED", report.DRAFT_LABEL)
        value = value.replace("Consolidated human review", "Review by exception - Consolidated human review")
        return value.replace("Evidence coverage", "Automated evidence coverage", 1)

    def compatible_pdf(payload: dict[str, Any]) -> bytes:
        original_paragraph = v3._paragraph

        def paragraph_with_legacy_label(value: Any, style: Any, limit: int = 1800) -> Any:
            text = str(value or "").replace(
                "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY BLOCKED",
                f"{report.DRAFT_LABEL} - CLIENT DELIVERY BLOCKED",
            ).replace(
                "Consolidated human review",
                "Review by exception - Consolidated human review",
            )
            return original_paragraph(text, style, limit)

        v3._paragraph = paragraph_with_legacy_label
        try:
            return original_pdf(_rendering_payload(payload))
        finally:
            v3._paragraph = original_paragraph

    report._report_payload = compatible_payload
    report._markdown = compatible_markdown
    report._html = compatible_html
    report._pdf = compatible_pdf
    report.MID_REPORT_VERSION = MID_REPORT_IDENTITY_VERSION
    report._nico_mid_report_v3_compat_installed = True
    _INSTALLED = True
    return {"status": "installed", **metadata}


__all__ = [
    "MID_REPORT_IDENTITY_VERSION",
    "MID_REPORT_PRESENTATION_VERSION",
    "install_mid_report_v3_compat",
]
