from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from nico.mid_score_truth_v3 import _consolidate_review_packet, _is_generic_disclosure

MID_REPORT_IDENTITY_VERSION = "mid-assessment-draft-v2"
MID_REPORT_PRESENTATION_VERSION = "mid-assessment-decision-ready-v3"
_INSTALLED = False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _presentation_sections(payload: dict[str, Any]) -> None:
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
        original_status = str(section.get("truth_status") or "Unavailable")
        direct = section.get("direct_repository_proof") is not False
        if original_status not in {"Failed", "Unavailable", "Human review required"} and direct and not blockers:
            display_status = "Verified"
        else:
            display_status = original_status
        section["source_truth_status"] = original_status
        section["truth_status"] = display_status
        section["scope_disclosures"] = _unique([*_list(section.get("scope_disclosures")), *disclosures])
        section["unavailable"] = blockers
        section["missing_evidence_sources"] = []
        section["failed_evidence_tools"] = []
        section["verification_basis"] = section.get("verification_basis") or "exact-run evidence within the explicitly disclosed assessment scope"


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
    review["exceptions"] = deepcopy(_list(display.get("display_exceptions")))
    review["display_summary"] = deepcopy(_dict(display.get("display_summary")))
    review["display_rule"] = display.get("display_rule") or ""
    # The source packet identity remains authoritative for approval and delivery.
    review["packet_version"] = source_packet["packet_version"]
    review["review_packet_id"] = source_packet["review_packet_id"]
    review["review_packet_sha256"] = source_packet["review_packet_sha256"]
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


def install_mid_report_v3_compat() -> dict[str, Any]:
    global _INSTALLED
    from nico import mid_assessment_report as report
    from nico import mid_report_v3 as v3

    if _INSTALLED:
        return {
            "status": "already_installed",
            "identity_version": MID_REPORT_IDENTITY_VERSION,
            "presentation_version": MID_REPORT_PRESENTATION_VERSION,
            "approval_identity_preserved": True,
            "display_review_consolidated": True,
        }

    original_payload: Callable[..., dict[str, Any]] = report._report_payload
    original_markdown: Callable[[dict[str, Any]], str] = report._markdown
    original_html: Callable[[dict[str, Any]], str] = report._html
    original_pdf: Callable[[dict[str, Any]], bytes] = report._pdf

    def compatible_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = deepcopy(original_payload(*args, **kwargs))
        payload["report_version"] = MID_REPORT_IDENTITY_VERSION
        payload["presentation_version"] = MID_REPORT_PRESENTATION_VERSION
        payload["approval_identity_contract_changed"] = False
        _presentation_sections(payload)
        _presentation_review(payload)
        return payload

    def compatible_markdown(payload: dict[str, Any]) -> str:
        value = original_markdown(payload)
        return value.replace("DRAFT - HUMAN REVIEW REQUIRED", report.DRAFT_LABEL)

    def compatible_html(payload: dict[str, Any]) -> str:
        value = original_html(payload)
        return value.replace("DRAFT - HUMAN REVIEW REQUIRED", report.DRAFT_LABEL)

    def compatible_pdf(payload: dict[str, Any]) -> bytes:
        original_paragraph = v3._paragraph

        def paragraph_with_legacy_label(value: Any, style: Any, limit: int = 1800) -> Any:
            text = str(value or "").replace(
                "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY BLOCKED",
                f"{report.DRAFT_LABEL} - CLIENT DELIVERY BLOCKED",
            )
            return original_paragraph(text, style, limit)

        v3._paragraph = paragraph_with_legacy_label
        try:
            return original_pdf(payload)
        finally:
            v3._paragraph = original_paragraph

    report._report_payload = compatible_payload
    report._markdown = compatible_markdown
    report._html = compatible_html
    report._pdf = compatible_pdf
    report.MID_REPORT_VERSION = MID_REPORT_IDENTITY_VERSION
    report._nico_mid_report_v3_compat_installed = True
    _INSTALLED = True
    return {
        "status": "installed",
        "identity_version": MID_REPORT_IDENTITY_VERSION,
        "presentation_version": MID_REPORT_PRESENTATION_VERSION,
        "approval_identity_preserved": True,
        "display_review_consolidated": True,
        "generic_scope_disclosures_separated": True,
        "human_review_required": True,
        "client_repository_write_allowed": False,
    }


__all__ = [
    "MID_REPORT_IDENTITY_VERSION",
    "MID_REPORT_PRESENTATION_VERSION",
    "install_mid_report_v3_compat",
]
