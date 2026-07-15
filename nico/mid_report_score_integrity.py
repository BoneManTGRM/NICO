from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

_MARKER = "_nico_mid_report_score_integrity_v1"


def install_mid_report_score_integrity() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    current: Callable[[dict[str, Any], dict[str, Any], dict[str, Any], str], dict[str, Any]] = report_module._report_payload
    if getattr(current, _MARKER, False):
        return {"status": "already_installed"}

    def payload_with_weighted_score_truth(
        record: dict[str, Any],
        packet: dict[str, Any],
        identity: dict[str, Any],
        generated_at: str,
    ) -> dict[str, Any]:
        payload = deepcopy(current(record, packet, identity, generated_at))
        integrity = payload.get("score_integrity") if isinstance(payload.get("score_integrity"), dict) else {}
        calculated = integrity.get("calculated_score")
        reported = integrity.get("reported_score")
        if not isinstance(calculated, int):
            return payload

        integrity["reported_score_before_final_report_reconciliation"] = reported
        integrity["final_report_score"] = calculated
        integrity["display_score_reconciled_to_weighted_technical_sections"] = reported != calculated
        integrity["score_match"] = reported is None or reported == calculated
        payload["score_integrity"] = integrity
        payload["technical_score"] = calculated

        maturity = payload.get("maturity_signal") if isinstance(payload.get("maturity_signal"), dict) else {}
        maturity["score"] = calculated
        payload["maturity_signal"] = maturity

        decision = payload.get("decision_summary") if isinstance(payload.get("decision_summary"), dict) else {}
        decision["technical_score"] = calculated
        decision["score_source"] = "seven_weighted_technical_sections"
        decision["human_context_sections_affect_score_without_review"] = False
        payload["decision_summary"] = decision

        executive = payload.get("executive_summary") if isinstance(payload.get("executive_summary"), dict) else {}
        executive["technical_score"] = f"{calculated}/100"
        executive["score_basis"] = "Seven weighted technical sections; evidence coverage and human-context modules do not directly change the score."
        payload["executive_summary"] = executive
        return payload

    setattr(payload_with_weighted_score_truth, _MARKER, True)
    setattr(payload_with_weighted_score_truth, "_nico_previous", current)
    report_module._report_payload = payload_with_weighted_score_truth
    return {
        "status": "installed",
        "score_source": "seven_weighted_technical_sections",
        "evidence_coverage_changes_score": False,
        "human_context_changes_score_without_review": False,
    }


__all__ = ["install_mid_report_score_integrity"]
