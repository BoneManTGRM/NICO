from nico.final_report_consistency import finalize_express_result_consistency
from nico.service_workflows import COVERAGE_TARGETS


def _base_result(**overrides):
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T11:20:00Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "coverage_targets": COVERAGE_TARGETS,
        "executive_summary": "NICO completed an assessment. The current maturity signal is Mid (71/100).",
        "maturity_signal": {"level": "Mid", "score": 77, "summary": "Stale pre-final score."},
        "maturity_semaphore": {"Code Audit": "green"},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 80,
                "status": "green",
                "summary": "Code audit uses final evidence.",
                "evidence": ["Commits reviewed."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "findings": [],
        "quick_wins": ["Review evidence."],
        "medium_term_plan": ["Keep report outputs consistent."],
        "resourcing_recommendation": ["Human review."],
        "risk_register": ["Stale report fields can mislead."],
        "verification_checklist": ["Check one final score."],
        "reports": {
            "markdown": "old markdown says 71/100",
            "html": "old html says 71/100",
            "pdf_base64": "old-pdf-placeholder",
        },
    }
    result.update(overrides)
    return result


def test_final_consistency_rebuilds_summary_and_reports_from_final_sections():
    result = finalize_express_result_consistency(_base_result())
    assert "71/100" not in result["executive_summary"]
    assert "80/100" in result["executive_summary"]
    assert result["score_source_of_truth"]["field"] == "maturity_signal"
    assert result["score_source_of_truth"]["score"] == 80
    assert result["maturity_signal"]["score"] == 80
    assert "71/100" not in result["reports"]["markdown"]
    assert "80/100" in result["reports"]["markdown"]
    assert "71/100" not in result["reports"]["html"]
    assert "80/100" in result["reports"]["html"]


def test_final_consistency_preserves_blocked_results_without_rewriting():
    blocked = {"status": "blocked", "executive_summary": "blocked old 71/100"}
    result = finalize_express_result_consistency(blocked)
    assert result is blocked
    assert result["executive_summary"] == "blocked old 71/100"


def test_final_consistency_rebuilds_es_mx_reports_from_final_sections():
    result = finalize_express_result_consistency(_base_result(assessment_mode="express_es_mx"))
    assert result["score_source_of_truth"]["score"] == 80
    assert result["maturity_signal"]["score"] == 80
    assert "71/100" not in result["executive_summary"]
    assert "80/100" in result["executive_summary"]
    assert "71/100" not in result["reports"]["markdown"]
    assert "Puntaje: **80/100**" in result["reports"]["markdown"]
    assert 'lang="es-MX"' in result["reports"]["html"]
