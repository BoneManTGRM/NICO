from __future__ import annotations

from nico.v2_pipeline_adapter import apply_v2_pipeline


SHA = "a" * 40
GENERATED_AT = "2026-08-04T16:15:00Z"


def test_semicolon_metadata_fragments_are_removed_before_publication():
    criterion = (
        f"Target complexity is at most 30. [method: metric_comparison; target commit: {SHA}]; "
        f"Target complexity is at most 30. [method: metric_comparison; target commit: {SHA}]; "
        f"The repository validation workflow passes. [method: workflow_verification; target commit: {SHA}]"
    )
    result = apply_v2_pipeline(
        {
            "report_package": {
                "json": {
                    "identity": {
                        "repository": "BoneManTGRM/NICO",
                        "commit_sha": SHA,
                        "run_id": "comprun_metadata",
                        "generated_at": GENERATED_AT,
                    },
                    "generated_at": GENERATED_AT,
                    "assessment": {
                        "technical_score": 80,
                        "canonical_evidence_adjusted_score": 79,
                        "sections": [],
                    },
                    "findings_register": [
                        {
                            "finding_id": "RISK-P1-METADATA",
                            "category": "architecture",
                            "title": "High-complexity code hotspot",
                            "location": "apps/web/app/operations/page.tsx:177",
                            "fact": "cyclomatic_complexity=52",
                            "priority": "P1",
                            "status": "open",
                            "recommendation": "Reduce the hotspot.",
                            "acceptance_criteria": criterion,
                        }
                    ],
                },
                "generated_at": GENERATED_AT,
                "pdf_filename": "nico-metadata.pdf",
            }
        }
    )
    finding = result["report_package"]["json"]["canonical_findings"][0]
    assert finding["acceptance_criteria"] == [
        "Target complexity is at most 30",
        "The repository validation workflow passes",
    ]
    markdown = result["report_package"]["markdown"]
    assert "method:" not in markdown.casefold()
    assert "target commit:" not in markdown.casefold()
    assert markdown.count("Target complexity is at most 30") == 1
