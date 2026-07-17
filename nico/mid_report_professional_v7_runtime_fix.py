from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico import mid_report_professional_v6 as v6
from nico import mid_report_professional_v7 as v7
from nico.mid_report_premium_contract_v8 import mid_report_contract, reconcile_mid_scores


_PATCH_MARKER = "_nico_mid_report_professional_v8_runtime_fix_installed"


def _fixed_premium_enhance(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an already-enriched payload without mutating v6 module APIs."""
    if str(payload.get("presentation_version") or "") in {v6.MID_REPORT_V6_VERSION, v7.VERSION}:
        output = deepcopy(payload)
    else:
        output = v6._enhance(payload)
    output["presentation_version"] = v7.VERSION
    output["presentation_detail_level"] = 8
    output["report_depth_contract"] = {
        **dict(output.get("report_depth_contract") or {}),
        "minimum_pdf_pages": 35,
        "target_pdf_pages": 42,
        "maximum_pdf_pages": 50,
        "minimum_visuals": 10,
        "maximum_visuals": 15,
        "premium_decision_brief": True,
        "transparent_scoring": True,
        "evidence_funnel": True,
        "risk_matrix": True,
        "repair_impact_matrix": True,
        "architecture_map": True,
        "dependency_topology": True,
        "ownership_analysis": True,
        "ci_reliability": True,
        "test_maturity": True,
        "evidence_appendix": True,
    }
    locale = str(output.get("report_language") or output.get("language") or output.get("locale") or "en")
    mid_report_contract(output, locale)
    reconcile_mid_scores(output)
    return output


def install_mid_report_professional_v7_runtime_fix() -> dict[str, Any]:
    """Bind v8 Mid output to the production report module while preserving direct contracts."""
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": v7.VERSION}

    current_payload = report_module._report_payload

    def payload_v8(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _fixed_premium_enhance(current_payload(record, packet, identity, generated_at))

    v7._premium_enhance = _fixed_premium_enhance
    report_module._report_payload = payload_v8
    report_module._pdf = v7._premium_pdf
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": v7.VERSION,
        "minimum_pdf_pages": 35,
        "target_pdf_pages": 42,
        "maximum_pdf_pages": 50,
        "transparent_scoring": True,
        "report_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
