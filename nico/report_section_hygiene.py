from __future__ import annotations

from typing import Any


def _final_score(result: dict[str, Any]) -> int:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    try:
        return int(maturity.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _trust_status(trust_level: str) -> str:
    if trust_level == "Verified":
        return "green"
    if trust_level in {"Evidence-bound", "Review-limited"}:
        return "yellow"
    if trust_level == "Draft only":
        return "red"
    return "gray"


def normalize_report_section_display(result: dict[str, Any]) -> dict[str, Any]:
    """Keep supplemental display rows clear without changing maturity scoring."""

    if result.get("status") != "complete":
        return result
    score = _final_score(result)
    display = result.get("trust_report_display") if isinstance(result.get("trust_report_display"), dict) else {}
    trust_level = str(result.get("trust_level") or display.get("trust_level") or "")
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        if section_id == "trust_readiness":
            section["score"] = score
            section["status"] = _trust_status(trust_level)
            section["scoring_weight"] = 0
            section["supplemental"] = True
            section["score_basis"] = "final_maturity_signal_display_only"
            evidence = section.setdefault("evidence", [])
            if isinstance(evidence, list):
                note = "Display score mirrors the final maturity score; this supplemental row has scoring_weight=0 and does not change the maturity average."
                if note not in evidence:
                    evidence.append(note)
        elif section_id == "client_acceptance" and int(section.get("score") or 0) == 0:
            section["status"] = "gray"
            section["scoring_weight"] = 0
            section["score_basis"] = "not_scored_until_human_acceptance"
    return result
