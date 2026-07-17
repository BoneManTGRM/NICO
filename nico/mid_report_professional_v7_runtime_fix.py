from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico import mid_report_professional_v6 as v6
from nico import mid_report_professional_v7 as v7

_PATCH_MARKER = "_nico_mid_report_professional_v7_runtime_fix_installed"


def _fixed_premium_enhance(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an already-enriched v6 payload without mutating v6 module APIs."""
    if str(payload.get("presentation_version") or "") == v6.MID_REPORT_V6_VERSION:
        output = deepcopy(payload)
    else:
        output = v6._enhance(payload)
    output["presentation_version"] = v7.VERSION
    output["presentation_detail_level"] = 7
    output["report_depth_contract"] = {
        **dict(output.get("report_depth_contract") or {}),
        "minimum_pdf_pages": 28,
        "target_pdf_pages": 35,
        "maximum_pdf_pages": 50,
        "premium_decision_brief": True,
        "evidence_funnel": True,
        "risk_matrix": True,
        "repair_impact_matrix": True,
        "evidence_appendix": True,
    }
    return output


def install_mid_report_professional_v7_runtime_fix() -> dict[str, Any]:
    """Bind v7 to the production report module while preserving v6 direct contracts."""
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": v7.VERSION}

    current_payload = report_module._report_payload

    def payload_v7(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _fixed_premium_enhance(current_payload(record, packet, identity, generated_at))

    v7._premium_enhance = _fixed_premium_enhance
    report_module._report_payload = payload_v7
    report_module._pdf = v7._premium_pdf
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": v7.VERSION,
        "target_pdf_pages": 35,
        "report_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
