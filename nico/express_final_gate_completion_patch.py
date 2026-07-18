from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import nico.client_acceptance as client_acceptance

PATCH_VERSION = "nico.cross_tier_final_gate_completion.v2"
_PATCH_MARKER = "_nico_cross_tier_final_gate_completion_v2"
SUPPORTED_TIERS = {"express", "mid", "full"}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tier(result: dict[str, Any]) -> str:
    raw = result.get("assessment_type") or result.get("service_tier") or "express"
    return str(raw).strip().lower()


def _artifact_available(bundle: dict[str, Any], name: str) -> bool:
    artifacts = _record(bundle.get("artifacts"))
    artifact = _record(artifacts.get(name))
    return bool(artifact.get("available") is True and str(artifact.get("sha256") or "").strip())


def _report_formats_ready(result: dict[str, Any]) -> bool:
    reports = _record(result.get("reports"))
    direct = all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html", "pdf_base64"))
    if direct:
        return True
    bundle = _record(result.get("evidence_artifact_bundle"))
    return all(_artifact_available(bundle, name) for name in ("markdown", "html", "pdf"))


def _score_ready(result: dict[str, Any]) -> bool:
    maturity = _record(result.get("maturity_signal"))
    score = maturity.get("score", result.get("technical_score"))
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return False
    return 0.0 <= numeric <= 100.0


def _sections_ready(result: dict[str, Any]) -> bool:
    sections = result.get("sections")
    return isinstance(sections, list) and any(isinstance(item, dict) for item in sections)


def normalize_assessment_completion(before_gate: dict[str, Any], after_gate: dict[str, Any]) -> dict[str, Any]:
    """Separate automated completion from approval and delivery for every paid tier."""

    output = deepcopy(after_gate)
    tier = _tier(before_gate) if _tier(before_gate) in SUPPORTED_TIERS else _tier(output)
    if tier not in SUPPORTED_TIERS:
        return output

    formats_ready = _report_formats_ready(output) or _report_formats_ready(before_gate)
    score_ready = _score_ready(output) or _score_ready(before_gate)
    sections_ready = _sections_ready(output) or _sections_ready(before_gate)
    completion = {
        "version": PATCH_VERSION,
        "tier": tier,
        "report_formats_ready": formats_ready,
        "score_ready": score_ready,
        "sections_ready": sections_ready,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    if not (formats_ready and score_ready and sections_ready):
        completion["status"] = "blocked_missing_completion_evidence"
        output["assessment_completion"] = completion
        if tier == "express":
            output["express_completion"] = completion
        else:
            output.pop("express_completion", None)
        output["human_review_required"] = True
        output["client_ready"] = False
        return output

    gate = _record(output.get("client_acceptance"))
    quality = _record(output.get("report_quality_guards"))
    original_status = str(output.get("status") or before_gate.get("status") or "").lower()
    completion.update({
        "status": "complete_pending_human_review",
        "source_status": original_status or "unknown",
        "client_acceptance_status": str(gate.get("status") or "pending"),
        "report_quality_status": str(quality.get("status") or quality.get("overall_status") or "review_required"),
        "rule": "Automated assessment completion is separate from human approval and client delivery.",
    })

    output["status"] = "complete"
    output["current_stage"] = "complete"
    output["progress_percent"] = 100
    output["report_generation_status"] = "complete"
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    output["delivery_status"] = "blocked_pending_human_review"
    output["assessment_completion"] = completion
    if tier == "express":
        output["express_completion"] = completion
    else:
        output.pop("express_completion", None)
    return output


def normalize_express_completion(before_gate: dict[str, Any], after_gate: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for callers introduced by v1."""
    return normalize_assessment_completion(before_gate, after_gate)


def install_express_final_gate_completion_patch() -> dict[str, Any]:
    current: Callable[[dict[str, Any]], dict[str, Any]] = client_acceptance.attach_client_acceptance_gate
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    def wrapped(result: dict[str, Any]) -> dict[str, Any]:
        before = deepcopy(result)
        after = current(result)
        return normalize_assessment_completion(before, after)

    setattr(wrapped, _PATCH_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    client_acceptance.attach_client_acceptance_gate = wrapped
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "tiers": sorted(SUPPORTED_TIERS),
        "completion_separate_from_delivery": True,
        "requires_report_formats": ["markdown", "html", "pdf"],
        "requires_score": True,
        "requires_sections": True,
    }


__all__ = [
    "PATCH_VERSION",
    "SUPPORTED_TIERS",
    "install_express_final_gate_completion_patch",
    "normalize_assessment_completion",
    "normalize_express_completion",
]
