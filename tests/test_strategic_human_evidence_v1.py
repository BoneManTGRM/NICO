from __future__ import annotations

import json

from nico.strategic_human_evidence_v1 import (
    MODULE_DEFINITIONS,
    build_strategic_human_evidence_ledger,
    parity_matrix_csv,
    qa_register_csv,
    stakeholder_decision_log_csv,
    strategic_intake_template,
)


IDENTITY = {
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "run_id": "comprun_human_evidence",
    "customer_id": "customer_human",
    "project_id": "project_human",
}


def test_missing_human_evidence_is_not_assessed_not_inferred_from_repository() -> None:
    ledger = build_strategic_human_evidence_ledger(identity=IDENTITY, stage_results={})

    assert ledger["status"] == "review_limited"
    assert len(ledger["modules"]) == len(MODULE_DEFINITIONS)
    assert len(ledger["incomplete_modules"]) == len(MODULE_DEFINITIONS)
    assert not ledger["complete_modules"]
    assert all(item["status"] == "not_assessed" for item in ledger["modules"])
    assert all(item["assurance"] == "NOT ASSESSED" for item in ledger["modules"])
    assert all(item["repository_inference_allowed"] is False for item in ledger["modules"])
    assert "never used to fabricate" in ledger["guardrail"]


def test_complete_qa_and_parity_require_explicit_observed_evidence() -> None:
    stage_results = {
        "functional_qa": {
            "status": "complete",
            "functional_qa": {
                "test_cases": [
                    {
                        "test_id": "QA-1",
                        "scenario": "Complete an Express assessment",
                        "expected": "Report generated",
                        "actual": "Report generated",
                        "status": "passed",
                    }
                ],
                "observed_results": [{"test_id": "QA-1", "status": "passed"}],
            },
            "accessibility_ux": {
                "observations": [
                    {"surface": "Assessment", "observation": "Keyboard flow reviewed", "status": "needs-review"}
                ]
            },
        },
        "platform_parity": {
            "status": "complete",
            "platform_parity": {
                "matrix": [
                    {
                        "surface": "Assessment",
                        "platform": "Web",
                        "operating_system": "iOS",
                        "browser_or_client": "Safari",
                        "result": "passed",
                    }
                ]
            },
        },
    }
    ledger = build_strategic_human_evidence_ledger(identity=IDENTITY, stage_results=stage_results)
    by_id = {item["module_id"]: item for item in ledger["modules"]}

    assert by_id["functional_qa"]["status"] == "complete"
    assert by_id["platform_parity"]["status"] == "complete"
    assert by_id["accessibility_ux"]["status"] == "complete"
    assert "QA-1" in qa_register_csv(ledger)
    assert "Safari" in parity_matrix_csv(ledger)
    assert by_id["stakeholder_context"]["status"] == "not_assessed"


def test_partial_evidence_stays_review_limited() -> None:
    ledger = build_strategic_human_evidence_ledger(
        identity=IDENTITY,
        stage_results={
            "stakeholder_and_business_alignment": {
                "status": "complete",
                "stakeholder_context": {"objectives": ["Reduce release risk"]},
            }
        },
    )
    stakeholder = next(item for item in ledger["modules"] if item["module_id"] == "stakeholder_context")

    assert stakeholder["status"] == "partial"
    assert stakeholder["assurance"] == "REVIEW LIMITED"
    assert stakeholder["present_fields"] == ["objectives"]
    assert stakeholder["missing_fields"] == ["constraints"]


def test_explicit_exclusion_requires_rationale() -> None:
    without_reason = build_strategic_human_evidence_ledger(
        identity=IDENTITY,
        stage_results={
            "platform_parity": {
                "status": "complete",
                "platform_parity": {"excluded": True},
            }
        },
    )
    with_reason = build_strategic_human_evidence_ledger(
        identity=IDENTITY,
        stage_results={
            "platform_parity": {
                "status": "complete",
                "platform_parity": {
                    "excluded": True,
                    "exclusion_rationale": "The assessed system has no mobile-native client in the authorized scope.",
                },
            }
        },
    )
    first = next(item for item in without_reason["modules"] if item["module_id"] == "platform_parity")
    second = next(item for item in with_reason["modules"] if item["module_id"] == "platform_parity")

    assert first["status"] != "excluded"
    assert second["status"] == "excluded"
    assert second["assurance"] == "EXCLUDED WITH RATIONALE"
    assert "no mobile-native client" in second["exclusion_rationale"]


def test_intake_template_covers_every_module_and_starts_unassessed() -> None:
    template = strategic_intake_template()

    assert template["artifact_schema"].endswith("v1")
    assert len(template["modules"]) == len(MODULE_DEFINITIONS)
    assert all(item["status"] == "not_assessed" for item in template["modules"])
    assert all(item["excluded"] is False for item in template["modules"])
    assert json.dumps(template)


def test_decision_log_export_contains_only_explicit_decisions() -> None:
    ledger = build_strategic_human_evidence_ledger(
        identity=IDENTITY,
        stage_results={
            "stakeholder_and_business_alignment": {
                "status": "complete",
                "accepted_risks": {
                    "decisions": [
                        {
                            "decision_id": "ADR-17",
                            "decision": "Accept a bounded migration window",
                            "owner": "CTO",
                            "rationale": "Customer cutover constraint",
                            "review_date": "2026-10-01",
                            "status": "accepted",
                        }
                    ]
                },
            }
        },
    )
    export = stakeholder_decision_log_csv(ledger)

    assert "ADR-17" in export
    assert "CTO" in export
    assert "Accept a bounded migration window" in export
