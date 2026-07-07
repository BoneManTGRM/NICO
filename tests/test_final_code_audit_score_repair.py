from nico.final_report_consistency import finalize_express_result_consistency


def test_final_consistency_lifts_code_audit_after_clean_marker_evidence():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "executive_summary": "old",
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "status": "green",
                "score": 80,
                "summary": "old code summary",
                "evidence": [
                    "Commits returned since 2026-01-01T00:00:00Z: 100.",
                    "Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2. General security wording in docs/workflows was not treated as an actionable code marker.",
                ],
                "findings": [],
            },
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "green", "score": 90, "evidence": [], "findings": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "green", "score": 93, "evidence": [], "findings": []},
            {"id": "static_analysis", "label": "Static Analysis", "status": "green", "score": 86, "evidence": [], "findings": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "evidence": [], "findings": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "evidence": [], "findings": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "green", "score": 83, "evidence": [], "findings": []},
        ],
        "reports": {},
    }

    finalized = finalize_express_result_consistency(result)
    code = next(section for section in finalized["sections"] if section["id"] == "code_audit")

    assert code["score"] == 86
    assert code["status"] == "green"
    assert finalized["maturity_signal"]["score"] == 90
    assert "Senior (90/100)" in finalized["executive_summary"]
    assert finalized["score_source_of_truth"]["score"] == 90


def test_final_consistency_does_not_lift_code_audit_with_actionable_finding():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "executive_summary": "old",
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "status": "green",
                "score": 80,
                "summary": "old code summary",
                "evidence": ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2."],
                "findings": ["TODO/FIXME/security-note markers require triage before client-ready delivery."],
            }
        ],
        "reports": {},
    }

    finalized = finalize_express_result_consistency(result)
    code = finalized["sections"][0]

    assert code["score"] == 80
    assert finalized["maturity_signal"]["score"] == 80
