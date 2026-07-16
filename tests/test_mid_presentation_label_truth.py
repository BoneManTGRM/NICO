from __future__ import annotations

from nico.mid_stage_truth_patch import MID_STAGE_TRUTH_VERSION, normalize_mid_stage_truth


def test_mid_presentation_replaces_inherited_full_assessment_labels_only() -> None:
    result = {
        "status": "complete",
        "report_generation_status": "complete",
        "approval_request_status": "pending",
        "executive_summary": "NICO generated an evidence-bound Full Assessment draft for owner/repo.",
        "assessment": {
            "executive_summary": "The Full Assessment contains seven weighted technical sections.",
            "title": "Full Technical Assessment",
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "score": 70,
                    "status": "yellow",
                    "summary": "Repository evidence was assessed.",
                    "evidence": ["Source text literally mentions Full Assessment and must remain evidence."],
                    "findings": ["A documentation file uses the phrase Full Assessment."],
                    "unavailable": [],
                }
            ],
        },
        "progress": [],
    }

    normalized = normalize_mid_stage_truth(result)

    assert normalized["executive_summary"] == "NICO generated an evidence-bound Mid Assessment draft for owner/repo."
    assert normalized["assessment"]["executive_summary"] == "The Mid Assessment contains seven weighted technical sections."
    assert normalized["assessment"]["title"] == "Mid Technical Assessment"
    assert normalized["assessment"]["sections"][0]["evidence"] == [
        "Source text literally mentions Full Assessment and must remain evidence."
    ]
    assert normalized["assessment"]["sections"][0]["findings"] == [
        "A documentation file uses the phrase Full Assessment."
    ]
    assert normalized["mid_stage_truth_version"] == MID_STAGE_TRUTH_VERSION
    assert normalized["mid_presentation_label_truth"]["generic_full_label_exposed"] is False
    assert normalized["mid_presentation_label_truth"]["evidence_or_findings_rewritten"] is False
