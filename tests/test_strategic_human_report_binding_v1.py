from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico.strategic_human_report_binding_v1 import install_strategic_human_report_binding_v1


def _base_result() -> dict:
    return {
        "status": "complete",
        "assessment": {},
        "canonical_run_manifest": {
            "status": "complete",
            "identity": {"assessment_depth": "strategic"},
            "module_status": [
                {"module_id": "functional_qa", "status": "not_assessed"},
                {"module_id": "platform_parity", "status": "not_assessed"},
                {"module_id": "stakeholder_context", "status": "not_assessed"},
            ],
            "strategic_modules_not_assessed": ["functional_qa", "platform_parity", "stakeholder_context"],
            "canonical_manifest_sha256": "old",
        },
        "evidence_manifest": {"exports": {}},
        "report_quality_contract": {},
        "report_package": {"report_id": "report_human_evidence"},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_binding_exports_human_evidence_and_updates_canonical_module_truth(monkeypatch) -> None:
    def fake_builder(*, identity, stage_results):
        del identity, stage_results
        return deepcopy(_base_result())

    monkeypatch.setattr(report_module, "build_comprehensive_report_package", fake_builder)
    installed = install_strategic_human_report_binding_v1()
    assert installed["human_evidence_ledger_exported"] is True
    assert installed["repository_inference_for_human_facts_allowed"] is False

    result = report_module.build_comprehensive_report_package(
        identity={
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_human_binding",
            "customer_id": "customer",
            "project_id": "project",
        },
        stage_results={
            "functional_qa": {
                "status": "complete",
                "functional_qa": {
                    "test_cases": [{"test_id": "QA-1", "scenario": "Run assessment", "status": "passed"}],
                    "observed_results": [{"test_id": "QA-1", "status": "passed"}],
                },
            },
            "platform_parity": {
                "status": "complete",
                "platform_parity": {
                    "excluded": True,
                    "exclusion_rationale": "No native mobile client in authorized scope.",
                },
            },
        },
    )

    assert result["strategic_human_evidence"]["status"] == "review_limited"
    package = result["report_package"]
    assert package["strategic_human_evidence_json"]
    assert package["strategic_intake_template_json"]
    assert "QA-1" in package["functional_qa_register_csv"]
    assert package["platform_parity_matrix_csv"].startswith("surface,")
    assert package["stakeholder_decision_log_csv"].startswith("module_id,")
    assert package["strategic_human_evidence_sha256"]

    manifest = result["canonical_run_manifest"]
    status = {item["module_id"]: item["status"] for item in manifest["module_status"]}
    assert status["functional_qa"] == "complete"
    assert status["platform_parity"] == "excluded"
    assert status["stakeholder_context"] == "not_assessed"
    assert manifest["strategic_modules_not_assessed"] == ["stakeholder_context"]
    assert manifest["strategic_modules_excluded_with_rationale"] == ["platform_parity"]
    assert manifest["human_evidence_fabrication_allowed"] is False
    assert manifest["canonical_manifest_sha256"] != "old"

    exports = result["evidence_manifest"]["exports"]
    assert exports["strategic_human_evidence_json_sha256"]
    assert exports["functional_qa_register_csv_sha256"]
    assert result["report_quality_contract"]["repository_inference_for_human_facts_allowed"] is False
    assert result["client_delivery_allowed"] is False


def test_installer_is_idempotent() -> None:
    first = install_strategic_human_report_binding_v1()
    second = install_strategic_human_report_binding_v1()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
