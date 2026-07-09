from __future__ import annotations

from nico.client_acceptance import attach_client_acceptance_gate
from nico.client_final_review_gate_patch import (
    attach_client_final_review_gate,
    build_client_final_review_gate,
    install_client_final_review_gate_patch,
)
from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle
from nico.report_full_detail_export_patch import attach_full_detail_report_exports


def assessment() -> dict:
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T22:30:00Z",
        "assessment_mode": "express",
        "timeframe_days": 180,
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 90,
                "status": "green",
                "summary": "Code audit complete.",
                "evidence": ["Evidence exists."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "findings": [],
        "repairs": [],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "# Report\n", "html": "<html>Report</html>"},
        "human_review_required": True,
        "safety_boundary": "Authorized defensive assessment only.",
    }
    result = attach_evidence_artifact_bundle(result)
    result = attach_full_detail_report_exports(result)
    return result


def test_final_review_gate_blocks_without_required_artifacts():
    gate = build_client_final_review_gate({"status": "complete", "sections": [], "reports": {}, "human_review_required": True})

    assert gate["artifact_schema"] == "nico.client_final_review_gate.v1"
    assert gate["status"] == "blocked_missing_final_review_evidence"
    assert gate["client_delivery_allowed"] is False
    assert gate["blockers"]


def test_final_review_gate_ready_with_hashes_and_full_detail():
    payload = assessment()
    payload["client_acceptance"] = {"status": "ready_for_human_signoff", "disclosures": {"unavailable_count": 0, "finding_count": 0}}

    gate = build_client_final_review_gate(payload)

    assert gate["status"] == "ready_for_final_human_review"
    assert gate["client_delivery_allowed"] is False
    assert gate["evidence_bundle_hash"]
    assert gate["evidence_ledger_hash"]
    assert gate["full_detail_filename"].endswith(".json")
    assert len(gate["required_review_roles"]) == 3


def test_final_review_gate_preserves_disclosures():
    payload = assessment()
    payload["client_acceptance"] = {"status": "ready_for_human_signoff_with_disclosures", "disclosures": {"unavailable_count": 2, "finding_count": 1}}

    gate = build_client_final_review_gate(payload)

    assert gate["status"] == "ready_for_final_human_review_with_disclosures"
    assert gate["disclosure_state"] == "disclosures_present"
    assert gate["unavailable_count"] == 2
    assert gate["finding_count"] == 1


def test_attach_final_review_gate_embeds_gate_into_client_acceptance():
    payload = assessment()
    payload["client_acceptance"] = {"status": "ready_for_human_signoff", "disclosures": {"unavailable_count": 0, "finding_count": 0}}

    output = attach_client_final_review_gate(payload)

    assert output["human_review_required"] is True
    assert output["client_final_review_gate"]["artifact_schema"] == "nico.client_final_review_gate.v1"
    assert output["client_acceptance"]["final_review_gate"]["status"] == "ready_for_final_human_review"
    assert output["client_acceptance"]["client_delivery_allowed"] is False


def test_installed_patch_adds_final_review_to_client_acceptance_gate():
    install_client_final_review_gate_patch()

    output = attach_client_acceptance_gate(assessment())

    assert output["client_final_review_gate"]["artifact_schema"] == "nico.client_final_review_gate.v1"
    assert output["client_acceptance"]["final_review_gate"]["client_delivery_allowed"] is False
    assert output["human_review_required"] is True
