from __future__ import annotations

from nico.v2_pipeline_adapter import apply_v2_pipeline


SHA = "a" * 40
GENERATED_AT = "2026-08-04T16:15:00Z"


def test_adapter_rebuilds_one_truth_and_review_state():
    duplicate = {
        "finding_id": "RISK-LEGACY",
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "fact": "cyclomatic_complexity=52; method=typescript_compiler_ast",
        "priority": "P1",
        "status": "open",
        "recommendation": "Decompose the hotspot.",
        "acceptance_criteria": ["Complexity is at most 30."],
    }
    prioritized = {**duplicate, "finding_id": "RISK-P1", "acceptance_criteria": [f"Complexity is at most 30. [target commit: {SHA}]"]}
    result = apply_v2_pipeline(
        {
            "status": "failed",
            "record": {"status": "failed"},
            "report_package": {
                "json": {
                    "identity": {
                        "repository": "BoneManTGRM/NICO",
                        "commit_sha": SHA,
                        "run_id": "run-v2",
                        "evidence_ledger_id": "ledger-v2",
                        "customer_id": "customer-v2",
                        "project_id": "project-v2",
                        "report_language": "en",
                        "generated_at": GENERATED_AT,
                    },
                    "generated_at": GENERATED_AT,
                    "assessment": {"technical_score": 82, "canonical_evidence_adjusted_score": 81, "sections": []},
                    "findings_register": [duplicate, prioritized],
                },
                "generated_at": GENERATED_AT,
                "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL.pdf",
            },
        }
    )
    package = result["report_package"]
    assert result["status"] == "review_required"
    assert result["record"]["status"] == "review_required"
    assert result["client_delivery_allowed"] is False
    assert len(package["json"]["canonical_findings"]) == 1
    assert package["canonical_truth_sha256"] == package["markdown_canonical_sha256"]
    assert package["canonical_truth_sha256"] == package["pdf_canonical_sha256"]
    assert package["canonical_truth_sha256"] == package["ui_canonical_sha256"]
    assert package["json"]["identity"]["generated_at"] == GENERATED_AT
    assert package["pdf_base64"]
    assert package["markdown"]
