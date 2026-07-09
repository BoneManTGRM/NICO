from __future__ import annotations

import json

from nico.release_readiness_summary_patch import attach_release_readiness_summary, build_release_readiness_summary, install_release_readiness_summary_patch


def result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 91, "level": "Senior"},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 90, "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency", "status": "green", "score": 90, "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static", "status": "yellow", "score": 74, "evidence": [], "findings": [], "unavailable": ["Semgrep unavailable"]},
            {"id": "client_acceptance", "label": "Client", "status": "gray", "score": 0, "evidence": [], "findings": [], "unavailable": []},
        ],
        "final_evidence_score_bridge": {
            "dependency_clean": True,
            "secret_clean_full_history": True,
            "static_clean": False,
            "static_triaged_without_blockers": False,
            "complexity_profile_attached": True,
            "lifts": {"dependency_health": {"previous_score": 74, "new_score": 90}},
        },
        "client_final_review_gate": {
            "status": "ready_for_final_human_review_with_disclosures",
            "disclosure_state": "disclosures_present",
            "required_review_roles": [{"role": "technical_reviewer", "required": True, "status": "pending"}],
            "blockers": ["Client representative signoff pending."],
        },
        "evidence_ledger": {
            "entry_count": 10,
            "verified_entry_count": 8,
            "partial_entry_count": 1,
            "unavailable_entry_count": 1,
            "finding_entry_count": 0,
            "ledger_hash": "abc123",
        },
        "reports": {"markdown": "# Report\n", "html": "<html>Report</html>"},
        "human_review_required": True,
    }


def test_release_readiness_summary_blocks_when_yellow_and_human_review_required():
    summary = build_release_readiness_summary(result())

    assert summary["artifact_schema"] == "nico.release_readiness_summary.v1"
    assert summary["status"] == "not_client_ready"
    assert summary["score"] == 91
    assert summary["score_target_met"] is True
    assert "static_analysis" in summary["yellow_sections"]
    assert summary["client_delivery_allowed"] is False
    assert any("Final human review" in item for item in summary["blockers"])


def test_attach_release_readiness_summary_exports_json_and_markdown():
    output = attach_release_readiness_summary(result())

    assert output["release_readiness_summary"]["artifact_schema"] == "nico.release_readiness_summary.v1"
    assert output["reports"]["release_readiness_summary_filename"].endswith(".json")
    parsed = json.loads(output["reports"]["release_readiness_summary_json"])
    assert parsed["repository"] if "repository" in parsed else True
    assert "## Release Readiness Summary" in output["reports"]["markdown"]
    assert "Release Readiness Summary" in output["reports"]["html"]


def test_release_readiness_patch_wraps_polish(monkeypatch):
    from nico import assessment_quality

    install_release_readiness_summary_patch()

    def fake_original(payload):
        return payload

    monkeypatch.setattr(assessment_quality, "_nico_original_polish_express_result_release_readiness", fake_original)
    output = assessment_quality.polish_express_result(result())

    assert output["release_readiness_summary"]["client_delivery_allowed"] is False
    assert output["reports"]["release_readiness_summary_json"]
