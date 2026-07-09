from nico.trust_engine import apply_strict_trust_engine
from nico.trust_report_display import attach_trust_report_display


def test_trust_display_replaces_stale_maturity_summary_score():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 82},
        "sections": [],
        "evidence_ledger": {
            "status": "partial",
            "coverage_by_section": {
                "dependency_health": {"missing_required_tools": ["pip-audit"]},
                "static_analysis": {"missing_required_tools": ["bandit"]},
                "secrets_review": {"missing_required_tools": ["trufflehog"]},
            },
        },
        "report_quality_guards": {"scanner_artifact_integration": {"status": "attached"}},
        "export_truth_gate": {"status": "passed", "export_allowed": True},
        "trust_engine": {"violations": [{"section": "Dependency", "reason": "missing proof"}]},
        "executive_summary": (
            "Trust Level: Review-limited. Client Delivery: Human Review Required. Score: 82/100.\n\n"
            "Why not higher: Dependency required proof incomplete.\n\n"
            "Path to verified: Attach current-run clean scanner evidence.\n\n"
            "NICO completed an authorized hosted Express Technical Health Assessment for BoneManTGRM/NICO. "
            "The final maturity signal is Senior (89/100). Scores are generated from stale pre-gate evidence."
        ),
    }

    output = attach_trust_report_display(result)
    summary = output["executive_summary"]

    assert "Score: 82/100" in summary
    assert "The final maturity signal is Senior (82/100)." in summary
    assert "89/100" not in summary
    assert "stale pre-gate evidence" not in summary


def test_strict_trust_engine_does_not_invert_cannot_be_green_wording():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency was green before final proof checks.",
                "evidence": ["requirements.txt found."],
                "findings": [],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            },
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
        ],
    }

    output = apply_strict_trust_engine(result)
    dependency = next(section for section in output["sections"] if section["id"] == "dependency_health")

    assert dependency["status"] == "yellow"
    assert "cannot be REVIEW-LIMITED" not in dependency["summary"]
    assert "cannot be VERIFIED" in dependency["summary"]
