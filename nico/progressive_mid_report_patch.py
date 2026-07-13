from __future__ import annotations

from copy import deepcopy
from typing import Any


_INSTALLED = False
MID_REPORT_VERSION = "mid-assessment-draft-v2"
MID_DETAIL_LEVEL = 2
MID_INCLUDED_MODULES = (
    "express_baseline",
    "snapshot_bound_evidence",
    "evidence_coverage",
    "section_scorecard",
    "review_by_exception",
    "integrity_bindings",
    "decision_support",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def build_mid_executive_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive a bounded executive layer from already-retained Mid evidence.

    The result summarizes existing section truth; it never upgrades evidence,
    changes a score, or creates a client-delivery decision.
    """

    sections = [item for item in _list(payload.get("sections")) if isinstance(item, dict)]
    verified: list[str] = []
    waiting: list[str] = []
    evidence_categories: dict[str, int] = {}
    finding_count = 0
    limitation_count = 0

    for section in sections:
        label = str(section.get("label") or section.get("id") or "Unnamed section")
        status = str(section.get("truth_status") or "unavailable").strip().lower()
        evidence = _texts(section.get("evidence"))
        findings = _texts(section.get("findings"))
        limitations = (
            _texts(section.get("unavailable"))
            + _texts(section.get("missing_evidence_sources"))
            + _texts(section.get("failed_evidence_tools"))
        )
        source = str(section.get("source_classification") or "repository_evidence")
        evidence_categories[source] = evidence_categories.get(source, 0) + len(evidence)
        finding_count += len(findings)
        limitation_count += len(limitations)
        if status in {"verified", "green", "complete", "clean", "passed"} and not limitations:
            verified.append(label)
        else:
            waiting.append(label)

    coverage = _dict(payload.get("evidence_coverage"))
    review_packet = _dict(payload.get("review_packet"))
    exceptions = [item for item in _list(review_packet.get("exceptions")) if isinstance(item, dict)]

    return {
        "report_tier": "mid",
        "detail_level": MID_DETAIL_LEVEL,
        "detail_relationship": "includes Express baseline and adds snapshot-bound evidence, review-by-exception, and decision support",
        "included_modules": list(MID_INCLUDED_MODULES),
        "executive_quick_view": {
            "verified_areas": verified,
            "areas_awaiting_verification": waiting,
            "evidence_coverage_percent": coverage.get("percent", 0),
            "finding_count": finding_count,
            "limitation_count": limitation_count,
            "review_exception_count": len(exceptions),
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "evidence_categories": dict(sorted(evidence_categories.items())),
        "decision_support": {
            "strengths": verified[:8],
            "waiting_for": waiting[:8],
            "review_required_items": [
                str(item.get("title") or item.get("category") or "Review item")
                for item in exceptions[:12]
            ],
            "score_changed": False,
            "evidence_upgraded": False,
            "approval_created": False,
            "client_delivery_allowed": False,
        },
        "next_tier_delta": {
            "tier": "full",
            "adds": [
                "deeper cross-domain synthesis",
                "expanded risk and remediation planning",
                "verification and rollback detail",
                "final-review preparation",
            ],
            "automatic_approval": False,
        },
    }


def install_progressive_mid_report_patch() -> None:
    """Make Mid reports explicitly deeper than Express without weakening truth gates."""

    global _INSTALLED
    if _INSTALLED:
        return

    from nico import mid_assessment_report as report_module

    original_payload = report_module._report_payload

    def progressive_payload(
        record: dict[str, Any],
        packet: dict[str, Any],
        identity: dict[str, Any],
        generated_at: str,
    ) -> dict[str, Any]:
        payload = original_payload(record, packet, identity, generated_at)
        detail = build_mid_executive_detail(payload)
        payload["report_version"] = MID_REPORT_VERSION
        payload["report_tier"] = detail["report_tier"]
        payload["detail_level"] = detail["detail_level"]
        payload["detail_relationship"] = detail["detail_relationship"]
        payload["included_modules"] = deepcopy(detail["included_modules"])
        payload["executive_quick_view"] = deepcopy(detail["executive_quick_view"])
        payload["evidence_categories"] = deepcopy(detail["evidence_categories"])
        payload["decision_support"] = deepcopy(detail["decision_support"])
        payload["next_tier_delta"] = deepcopy(detail["next_tier_delta"])

        summary = _dict(payload.get("executive_summary"))
        summary.update(
            {
                "report_tier": "Mid",
                "detail_level": MID_DETAIL_LEVEL,
                "verified_areas": len(detail["executive_quick_view"]["verified_areas"]),
                "areas_awaiting_verification": len(detail["executive_quick_view"]["areas_awaiting_verification"]),
                "review_exceptions": detail["executive_quick_view"]["review_exception_count"],
                "client_delivery": "Human Review Required",
            }
        )
        payload["executive_summary"] = summary

        decision_section = {
            "id": "executive_decision_support",
            "label": "Executive Decision Support",
            "score": None,
            "truth_status": "Human Review Required",
            "summary": (
                "This section summarizes existing Mid evidence for decision support. "
                "It does not change scores, upgrade evidence, approve findings, or permit client delivery."
            ),
            "evidence": [
                f"Verified areas: {', '.join(detail['decision_support']['strengths']) or 'none verified without limitations'}.",
                f"Areas awaiting verification: {', '.join(detail['decision_support']['waiting_for']) or 'none'}.",
                f"Evidence coverage: {detail['executive_quick_view']['evidence_coverage_percent']}%.",
                f"Review exceptions retained: {detail['executive_quick_view']['review_exception_count']}.",
                "Mid includes the Express baseline plus snapshot-bound evidence, review-by-exception, and decision-support detail.",
            ],
            "findings": deepcopy(detail["decision_support"]["review_required_items"]),
            "unavailable": [
                f"Awaiting verification: {item}" for item in detail["decision_support"]["waiting_for"]
            ],
            "missing_evidence_sources": [],
            "failed_evidence_tools": [],
            "source_classification": "derived_from_retained_mid_evidence",
            "direct_repository_proof": False,
            "human_review_required": True,
            "unsupported_claims_permitted": False,
        }
        payload["sections"] = [decision_section] + [deepcopy(item) for item in payload.get("sections") or []]
        return payload

    report_module.MID_REPORT_VERSION = MID_REPORT_VERSION
    report_module._report_payload = progressive_payload
    _INSTALLED = True
