from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico import mid_report_professional_v6 as v6
from nico import mid_report_professional_v7 as v7


def _base_v6_enhance(payload: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the v6 enhancement without calling the monkey-patched symbol."""
    output = deepcopy(payload)
    score = v6._canonical_score(output)
    status, status_reason = v6._decision_status(score)
    decision = v6._dict(output.get("decision_summary"))
    decision.update(
        {
            "review_decision": status,
            "review_decision_reason": status_reason,
            "action_plan": v6._action_plan(output),
        }
    )
    output["decision_summary"] = decision
    output["presentation_version"] = v6.MID_REPORT_V6_VERSION
    output["presentation_detail_level"] = 6
    output["evidence_assurance_matrix"] = [
        {"section_id": section.get("id"), "label": section.get("label"), **v6._section_state(section)}
        for section in v6._technical(output)
    ]
    output["grouped_review_exceptions"] = v6._group_exceptions(output)
    output["report_depth_contract"] = {
        **v6._dict(output.get("report_depth_contract")),
        "minimum_pdf_pages": 7,
        "target_pdf_pages": 8,
        "maximum_pdf_pages": 10,
        "paired_technical_dossiers": True,
        "evidence_assurance_matrix": True,
        "finding_specific_action_plan": True,
        "blank_values_normalized": True,
        "full_integrity_values_retained_in_markdown_and_json": True,
        "legacy_payload_contract_preserved": True,
    }
    return output


def _fixed_premium_enhance(payload: dict[str, Any]) -> dict[str, Any]:
    output = _base_v6_enhance(payload)
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


def install_mid_report_professional_v7_runtime_fix() -> None:
    """Install v7 without recursive calls through v6._enhance."""
    v7._premium_enhance = _fixed_premium_enhance
    v6._enhance = _fixed_premium_enhance
    v6._pdf = v7._premium_pdf
