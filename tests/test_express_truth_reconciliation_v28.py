from nico.express_section_status_truth_v26 import reconcile_section_status_truth


def _section(result, section_id):
    return next(item for item in result["sections"] if item["id"] == section_id)


def test_failed_scanner_is_not_described_as_completed_and_clean():
    result = {
        "human_review_required": True,
        "sections": [
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 72,
                "status": "yellow",
                "evidence": [
                    "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                    "Secrets evidence status: full-history gitleaks/trufflehog artifacts are attached, current-run, and clean for this report run.",
                ],
                "findings": [
                    "gitleaks ended with status failed; its output requires human review before client-facing conclusions.",
                    "trufflehog ended with status failed; its output requires human review before client-facing conclusions.",
                ],
                "unavailable": ["Scanner-worker secret tools unavailable: gitleaks, trufflehog."],
            }
        ],
    }

    section = _section(reconcile_section_status_truth(result), "secrets_review")
    joined = " ".join(section["evidence"]).lower()
    assert "tools completed" not in joined
    assert "current-run, and clean" not in joined
    assert "truth reconciliation" in joined
    assert section["assurance_label"] == "REVIEW LIMITED"


def test_static_analyzer_failure_does_not_create_critical_quality_score():
    result = {
        "human_review_required": True,
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 31,
                "status": "yellow",
                "evidence": ["Built-in static risk-pattern hits: 6."],
                "findings": [
                    "bandit ended with status failed; its output requires human review before client-facing conclusions.",
                    "semgrep ended with status failed; its output requires human review before client-facing conclusions.",
                    "typescript ended with status failed; its output requires human review before client-facing conclusions.",
                ],
                "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."],
            }
        ],
    }

    section = _section(reconcile_section_status_truth(result), "static_analysis")
    assert section["score"] is None
    assert section["score_band_label"] == "NOT SCORED"
    assert section["assurance_label"] == "REVIEW LIMITED"
    assert section["source_score_before_evidence_gate"] == 31


def test_architecture_exceptional_score_is_capped_without_runtime_proof():
    result = {
        "human_review_required": True,
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 94,
                "status": "green",
                "evidence": ["Complexity engine current-run artifact completed: 0 call-graph edge(s), max measured complexity 80."],
                "findings": [],
                "unavailable": ["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker."],
            }
        ],
    }

    section = _section(reconcile_section_status_truth(result), "architecture_debt")
    assert section["score"] == 79
    assert section["score_band_label"] == "MODERATE"
    assert section["assurance_label"] == "REVIEW LIMITED"
    assert section["source_score_before_evidence_cap"] == 94
