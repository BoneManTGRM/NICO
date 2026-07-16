from __future__ import annotations

from copy import deepcopy

from nico.mid_report_section_boundary_patch import reconcile_mid_report_section_boundaries
from nico.report_quality_gate import evaluate_report_payload


CONTEXT_IDS = (
    "functional_qa",
    "platform_parity",
    "architecture_context",
    "stakeholder_alignment",
    "business_roadmap",
)


def _technical(section_id: str, index: int) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": 70 + index,
        "truth_status": "Verified with limitations",
        "summary": "Retained same-run evidence supports a bounded technical conclusion with explicit limitations.",
        "evidence": [f"Exact-run retained technical evidence {index}."],
        "findings": [f"Review technical finding {index}."],
        "unavailable": ["Automated evidence does not prove exhaustive absence of defects."],
        "human_review_required": True,
    }


def _base_payload() -> dict:
    technical_ids = (
        "code_audit",
        "dependency_health",
        "secrets_review",
        "static_analysis",
        "ci_cd",
        "architecture_debt",
        "velocity_complexity",
    )
    context = [
        {
            "id": section_id,
            "label": section_id.replace("_", " ").title(),
            "score": None,
            "truth_status": "Unavailable",
            "summary": f"Unavailable: {section_id.replace('_', ' ')} requires external evidence not supplied for this run.",
            "evidence": [],
            # Simulate the production report-payload defect: the explicit
            # unavailable list was lost even though the retained assessment has it.
            "unavailable": [],
            "human_review_required": False,
        }
        for section_id in CONTEXT_IDS
    ]
    return {
        "status": "draft",
        "run_id": "midrun_section_boundary_test",
        "repository": "BoneManTGRM/NICO",
        "snapshot_commit_sha": "a" * 40,
        "executive_summary": {
            "assessment": "The exact repository snapshot supports a bounded technical assessment while external context remains explicitly unavailable.",
            "decision": "Human review remains mandatory before approval or delivery.",
        },
        "decision_summary": {
            "technical_maturity": "Mid",
            "technical_score": 74,
            "recommended_actions": ["Review retained findings and unavailable context before approval."],
        },
        "sections": [_technical(section_id, index) for index, section_id in enumerate(technical_ids)] + context,
        "evidence_coverage": {
            "calculated": True,
            "percent": 100,
            "numerator": 12,
            "denominator": 12,
            "method": "Twelve exact-run evidence units were evaluated.",
        },
        "technical_score": 74,
        "score_integrity": {"score_match": True},
        "unsupported_claims_permitted": 0,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _record_with_retained_context(payload: dict) -> dict:
    sections = deepcopy(payload["sections"])
    for section in sections:
        if section["id"] in CONTEXT_IDS:
            section["unavailable"] = [section["summary"]]
            section["scope_disclosures"] = [
                "External context requires human validation and cannot change the technical score automatically."
            ]
    return {
        "response": {
            "mid_truth_status": {"sections": deepcopy(sections)},
            "assessment": {"sections": deepcopy(sections)},
        }
    }


def test_retained_unavailable_boundaries_prevent_false_unsupported_section_blocks() -> None:
    payload = _base_payload()
    output = reconcile_mid_report_section_boundaries(payload, _record_with_retained_context(payload))
    manifest = evaluate_report_payload(output, "mid")
    by_id = {section["id"]: section for section in output["sections"]}

    for section_id in CONTEXT_IDS:
        assert by_id[section_id]["truth_status"] == "Unavailable"
        assert by_id[section_id]["evidence"] == []
        assert by_id[section_id]["unavailable"] == [by_id[section_id]["summary"]]
        assert by_id[section_id]["score"] is None

    unsupported = [item for item in manifest["issues"] if item["code"] == "unsupported_section_conclusion"]
    assert unsupported == []
    assert manifest["status"] in {"ready_for_human_review", "review_required"}
    assert output["mid_report_section_boundary_reconciliation"]["missing_evidence_converted_to_pass"] is False
    assert output["mid_report_section_boundary_reconciliation"]["scores_changed"] is False


def test_non_verified_summary_is_an_explicit_limitation_not_passing_evidence() -> None:
    payload = _base_payload()
    record = {"response": {"mid_truth_status": {"sections": []}, "assessment": {"sections": []}}}
    output = reconcile_mid_report_section_boundaries(payload, record)
    context = next(section for section in output["sections"] if section["id"] == "functional_qa")

    assert context["evidence"] == []
    assert context["unavailable"] == [context["summary"]]
    assert context["explicit_evidence_boundary_source"] == "retained_non_verified_truth_summary"
    assert context["truth_status"] == "Unavailable"
    assert context["score"] is None


def test_verified_section_without_evidence_or_limitation_still_fails_closed() -> None:
    payload = _base_payload()
    payload["sections"][0]["truth_status"] = "Verified"
    payload["sections"][0]["evidence"] = []
    payload["sections"][0]["verified_claims"] = []
    payload["sections"][0]["unavailable"] = []
    payload["sections"][0]["missing_evidence_sources"] = []
    payload["sections"][0]["failed_evidence_tools"] = []
    payload["sections"][0]["unverified_claims"] = []
    record = {"response": {"mid_truth_status": {"sections": []}, "assessment": {"sections": []}}}

    output = reconcile_mid_report_section_boundaries(payload, record)
    manifest = evaluate_report_payload(output, "mid")

    assert output["sections"][0]["evidence"] == []
    assert output["sections"][0]["unavailable"] == []
    assert any(
        item["code"] == "unsupported_section_conclusion" and item["section_id"] == payload["sections"][0]["id"]
        for item in manifest["issues"]
    )
    assert manifest["status"] == "blocked"
