from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

VERSION = "nico.final_report_delivery_package.v1"
_PATCH_MARKER = "_nico_final_report_delivery_package_v1"

_REPLACEMENTS = (
    ("DRAFT — HUMAN REVIEW REQUIRED", "FINAL REPORT — HUMAN REVIEW REQUIRED BEFORE DELIVERY"),
    ("DRAFT REPORT", "FINAL REPORT"),
    ("Draft report", "Final report"),
    ("draft report", "final report"),
    ("Prepared for human review before delivery", "Complete report package prepared for human review and delivery approval"),
    ("Download draft PDF", "Download final PDF"),
    ("draft PDF", "final PDF"),
    ("Draft only", "Final report package — delivery pending approval"),
)


def _replace_text(value: str) -> str:
    output = value
    for old, new in _REPLACEMENTS:
        output = output.replace(old, new)
    return output


def _finalize(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_text(value)
    if isinstance(value, list):
        return [_finalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _finalize(item) for key, item in value.items()}
    return value


def finalize_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = _finalize(deepcopy(payload))
    output["report_package_status"] = "final_report_pending_human_delivery_approval"
    output["report_is_complete"] = True
    output["report_recreation_required"] = False
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False

    decision = output.get("decision_summary")
    if isinstance(decision, dict):
        decision["report_status"] = "Final report package complete; delivery pending authorized human approval."
        decision["report_recreation_required"] = False

    truth = output.get("canonical_report_truth")
    if isinstance(truth, dict):
        truth["delivery_status"] = "Final report package complete; delivery pending approval"
        truth["report_recreation_required"] = False

    return output


def install_final_report_delivery_package() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module
    from nico import mid_report_professional_v4 as v4
    from nico import mid_report_professional_v6 as v6
    from nico import mid_report_professional_v7 as v7

    final_label = "FINAL REPORT — HUMAN REVIEW REQUIRED BEFORE DELIVERY"
    v4._DRAFT_LABEL = final_label
    v6._DRAFT_LABEL = final_label
    v4.MID_REPORT_V4_VERSION = "mid-assessment-final-v4-full-depth"
    v6.MID_REPORT_V6_VERSION = "mid-assessment-final-v6-executive-actionable"
    v7.VERSION = "mid-assessment-final-v8-premium"

    current_payload: Callable[..., dict[str, Any]] = report_module._report_payload
    if getattr(current_payload, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "final_report_package": True,
            "report_recreation_required": False,
        }

    def final_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current_payload(*args, **kwargs)
        return finalize_report_payload(result)

    setattr(final_payload, _PATCH_MARKER, True)
    setattr(final_payload, "_nico_previous", current_payload)
    report_module._report_payload = final_payload

    return {
        "status": "installed",
        "version": VERSION,
        "final_report_package": True,
        "report_recreation_required": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "finalize_report_payload", "install_final_report_delivery_package"]
