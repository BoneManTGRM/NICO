from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable


READINESS_SCHEMA = "nico.release_readiness_summary.v1"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sections(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get("id")): section
        for section in _safe_list(result.get("sections"))
        if isinstance(section, dict) and section.get("id")
    }


def _score_state(result: dict[str, Any]) -> dict[str, Any]:
    sections = _sections(result)
    counted = [
        section
        for section in sections.values()
        if section.get("status") != "gray"
        and section.get("supplemental") is not True
        and int(section.get("scoring_weight", 1) or 0) != 0
    ]
    score = round(sum(int(section.get("score") or 0) for section in counted) / len(counted)) if counted else 0
    return {
        "score": int(result.get("maturity_signal", {}).get("score") or score) if isinstance(result.get("maturity_signal"), dict) else score,
        "computed_score": score,
        "green_sections": [section.get("id") for section in counted if section.get("status") == "green"],
        "yellow_sections": [section.get("id") for section in counted if section.get("status") == "yellow"],
        "red_sections": [section.get("id") for section in counted if section.get("status") == "red"],
        "gray_sections": [section.get("id") for section in sections.values() if section.get("status") == "gray"],
        "counted_section_count": len(counted),
    }


def _bridge(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("final_evidence_score_bridge"))


def _final_gate(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("client_final_review_gate")) or _safe_dict(_safe_dict(result.get("client_acceptance")).get("final_review_gate"))


def _ledger(result: dict[str, Any]) -> dict[str, Any]:
    bundle = _safe_dict(result.get("evidence_artifact_bundle"))
    return _safe_dict(result.get("evidence_ledger")) or _safe_dict(bundle.get("evidence_ledger"))


def _blockers(result: dict[str, Any], score_state: dict[str, Any], bridge: dict[str, Any], gate: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if score_state["yellow_sections"]:
        blockers.append("One or more scored sections remain yellow: " + ", ".join(score_state["yellow_sections"]))
    if score_state["red_sections"]:
        blockers.append("One or more scored sections remain red: " + ", ".join(score_state["red_sections"]))
    if bridge and not bridge.get("dependency_clean"):
        blockers.append("Dependency scanner evidence is not final-clean.")
    if bridge and not bridge.get("secret_clean_full_history"):
        blockers.append("Full-history secret scanner evidence is not final-clean.")
    if bridge and not (bridge.get("static_clean") or bridge.get("static_triaged_without_blockers")):
        blockers.append("Static scanner evidence is not clean or fully triaged.")
    if bridge and not bridge.get("complexity_profile_attached"):
        blockers.append("Current-run complexity evidence is not attached.")
    if ledger and int(ledger.get("unavailable_entry_count") or 0) > 0:
        blockers.append(f"Evidence ledger still has {ledger.get('unavailable_entry_count')} unavailable entry/entries.")
    if ledger and int(ledger.get("finding_entry_count") or 0) > 0:
        blockers.append(f"Evidence ledger still has {ledger.get('finding_entry_count')} finding-bearing entry/entries.")
    gate_blockers = _safe_list(gate.get("blockers"))
    blockers.extend(str(item) for item in gate_blockers)
    if result.get("human_review_required", True):
        blockers.append("Final human review is still required before client delivery.")
    return list(dict.fromkeys(blockers))


def build_release_readiness_summary(result: dict[str, Any]) -> dict[str, Any]:
    score_state = _score_state(result)
    bridge = _bridge(result)
    gate = _final_gate(result)
    ledger = _ledger(result)
    blockers = _blockers(result, score_state, bridge, gate, ledger)
    if blockers:
        status = "not_client_ready"
    elif score_state["score"] >= 90:
        status = "ready_for_human_final_review"
    else:
        status = "score_below_target"
    return {
        "artifact_schema": READINESS_SCHEMA,
        "status": status,
        "client_delivery_allowed": False,
        "score": score_state["score"],
        "computed_score": score_state["computed_score"],
        "target_score": 90,
        "score_target_met": score_state["score"] >= 90,
        "green_sections": score_state["green_sections"],
        "yellow_sections": score_state["yellow_sections"],
        "red_sections": score_state["red_sections"],
        "gray_sections": score_state["gray_sections"],
        "final_evidence_score_bridge": deepcopy(bridge),
        "client_final_review_gate": {
            "status": gate.get("status"),
            "disclosure_state": gate.get("disclosure_state"),
            "required_review_roles": deepcopy(gate.get("required_review_roles") or []),
            "blockers": deepcopy(gate.get("blockers") or []),
        },
        "evidence_ledger": {
            "entry_count": ledger.get("entry_count"),
            "verified_entry_count": ledger.get("verified_entry_count"),
            "partial_entry_count": ledger.get("partial_entry_count"),
            "unavailable_entry_count": ledger.get("unavailable_entry_count"),
            "finding_entry_count": ledger.get("finding_entry_count"),
            "ledger_hash": ledger.get("ledger_hash"),
        },
        "blockers": blockers,
        "guardrail": "Release readiness is a visibility summary only. It does not certify delivery, hide unavailable evidence, waive findings, or replace final human review.",
    }


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "",
        "## Release Readiness Summary",
        f"Status: {summary.get('status')}",
        f"Score: {summary.get('score')}/100, target {summary.get('target_score')}/100",
        f"Score target met: {summary.get('score_target_met')}",
        f"Client delivery allowed: {summary.get('client_delivery_allowed')}",
        "",
        "### Section State",
        f"- Green: {', '.join(summary.get('green_sections') or []) or 'none'}",
        f"- Yellow: {', '.join(summary.get('yellow_sections') or []) or 'none'}",
        f"- Red: {', '.join(summary.get('red_sections') or []) or 'none'}",
        f"- Gray: {', '.join(summary.get('gray_sections') or []) or 'none'}",
        "",
        "### Remaining Blockers",
    ]
    blockers = summary.get("blockers") if isinstance(summary.get("blockers"), list) else []
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None recorded. Final human review is still required before delivery.")
    return "\n".join(lines).rstrip() + "\n"


def attach_release_readiness_summary(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result
    summary = build_release_readiness_summary(result)
    result["release_readiness_summary"] = summary
    reports = result.setdefault("reports", {})
    reports["release_readiness_summary_json"] = json.dumps(summary, indent=2, sort_keys=True, default=str)
    reports["release_readiness_summary_filename"] = f"nico-release-readiness-{str(result.get('repository') or 'assessment').replace('/', '-')}.json"
    markdown = reports.get("markdown") if isinstance(reports.get("markdown"), str) else ""
    appendix = _markdown(summary)
    if "## Release Readiness Summary" not in markdown:
        reports["markdown"] = (markdown.rstrip() + "\n" + appendix).lstrip()
    reports["release_readiness_summary_markdown"] = appendix
    try:
        from nico.hosted_assessment import build_html

        reports["html"] = build_html(reports["markdown"])
    except Exception:
        pass
    return result


def install_release_readiness_summary_patch() -> None:
    from nico import assessment_quality

    original: Callable[[dict[str, Any]], dict[str, Any]] | None = getattr(assessment_quality, "_nico_original_polish_express_result_release_readiness", None)
    if original is None:
        original = assessment_quality.polish_express_result
        assessment_quality._nico_original_polish_express_result_release_readiness = original

    def polish_express_result_with_release_readiness(result: dict[str, Any]) -> dict[str, Any]:
        original_func = assessment_quality._nico_original_polish_express_result_release_readiness
        return attach_release_readiness_summary(original_func(result))

    assessment_quality.polish_express_result = polish_express_result_with_release_readiness
