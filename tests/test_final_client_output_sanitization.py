from __future__ import annotations

from nico import report_intelligence_accuracy_patch as accuracy
from nico.express_completion_score_binding import (
    finalize_report_intelligence_at_response,
    install_express_completion_score_binding,
)


QUALITY_HEADING = "## Repository Quality and Governance Signals"
REPAIR_HEADING = "## Prioritized Repair Intelligence"


def _fake_rebuild(_hosted, value: dict) -> dict:
    rebuilt = dict(value)
    rebuilt["reports"] = {
        "markdown": f"{QUALITY_HEADING}\n\n{REPAIR_HEADING}\n",
        "html": "<html>quality and repairs</html>",
        "pdf_base64": "cGRm",
    }
    return rebuilt


def test_final_output_replaces_none_measurements_before_report_rebuild(monkeypatch) -> None:
    captured: dict = {}

    def capture_rebuild(_hosted, value: dict) -> dict:
        captured.update(value)
        return _fake_rebuild(_hosted, value)

    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", capture_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete", "findings": []},
            "sections": [
                {
                    "id": "architecture_debt",
                    "status": "green",
                    "score": 94,
                    "summary": "Complexity evidence is available.",
                    "findings": [
                        "Complexity hotspot: nico/module.py score=410, max_function_cyclomatic=None, density=None, churn=90."
                    ],
                    "evidence": [
                        "Top complexity hotspot: nico/module.py max_function_cyclomatic=None density=None."
                    ],
                    "unavailable": [],
                }
            ],
        }
    )

    rendered_source = str(captured)
    assert "max_function_cyclomatic=None" not in rendered_source
    assert "density=None" not in rendered_source
    assert "max_function_cyclomatic=unavailable" in rendered_source
    assert "density=unavailable" in rendered_source
    assert "None" not in " ".join(
        str(item)
        for candidate in response["repair_intelligence"]["candidates"]
        for item in candidate.get("evidence", [])
    )


def test_green_required_checks_suppress_generic_ci_quick_win(monkeypatch) -> None:
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete", "findings": []},
            "quick_wins": [
                "Add or strengthen CI checks for lint, tests, dependency audit, static analysis, and production build where missing.",
                "Keep evidence ledger and export truth gate attached.",
            ],
            "sections": [
                {
                    "id": "ci_cd",
                    "status": "green",
                    "score": 95,
                    "summary": "Current release readiness is green.",
                    "evidence": [
                        "Current release-readiness latest checks: NICO CI=success, CodeQL Advanced=success, Audit Evidence=success, Security Audit Evidence=success."
                    ],
                    "findings": [
                        "Historical workflow reliability includes 5 non-success run(s); review reliability history separately from current release readiness."
                    ],
                    "unavailable": [],
                }
            ],
        }
    )

    assert not any("add or strengthen ci checks" in item.lower() for item in response["quick_wins"])
    assert "Keep evidence ledger and export truth gate attached." in response["quick_wins"]
    assert response["repair_action_summary"]["generic_ci_quick_win_suppressed_because_required_checks_green"] is True


def test_installer_reports_client_output_sanitization() -> None:
    installed = install_express_completion_score_binding()

    assert installed["client_output_measurements_sanitized"] is True
    assert installed["score_inflation_allowed"] is False
