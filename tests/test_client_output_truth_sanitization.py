from __future__ import annotations

from nico import assessment_quality
from nico import express_completion_score_binding as completion
from nico.client_output_truth_sanitization import (
    install_client_output_truth_sanitization,
    sanitize_client_text,
)


def test_known_none_metrics_render_as_unavailable() -> None:
    source = (
        "Complexity hotspot: nico/example.py score=42.0, "
        "max_function_cyclomatic=None, density=None, coverage_ratio=None."
    )

    sanitized = sanitize_client_text(source)

    assert "max_function_cyclomatic=unavailable" in sanitized
    assert "density=unavailable" in sanitized
    assert "coverage_ratio=unavailable" in sanitized
    assert "=None" not in sanitized


def test_assessment_friendly_note_uses_client_truth_sanitizer() -> None:
    rendered = assessment_quality._friendly_note(
        "Complexity hotspot: nico/example.py max_function_cyclomatic=None, density=None."
    )

    assert "max_function_cyclomatic=unavailable" in rendered
    assert "density=unavailable" in rendered
    assert "None" not in rendered


def test_final_section_reconciliation_sanitizes_all_report_formats_before_rebuild() -> None:
    payload = {
        "sections": [
            {
                "id": "architecture_debt",
                "summary": "Measured density=None.",
                "evidence": ["max_function_cyclomatic=None"],
                "findings": ["density=None"],
                "unavailable": ["coverage_ratio=None"],
            }
        ],
        "executive_summary": "Function measurement max_function_cyclomatic=None.",
        "quick_wins": ["Investigate density=None."],
    }

    completion._reconcile_final_section_truth(payload)

    section = payload["sections"][0]
    assert section["summary"] == "Measured density=unavailable."
    assert section["evidence"] == ["max_function_cyclomatic=unavailable"]
    assert section["findings"] == ["density=unavailable"]
    assert section["unavailable"] == ["coverage_ratio=unavailable"]
    assert "None" not in payload["executive_summary"]
    assert "None" not in payload["quick_wins"][0]


def test_verified_green_ci_suppresses_only_stale_green_run_advice() -> None:
    payload = {
        "sections": [
            {
                "id": "ci_cd",
                "status": "green",
                "score": 95,
                "findings": ["Historical workflow reliability includes non-success runs."],
                "evidence": ["Current required workflows are present and provider checks succeeded."],
            }
        ],
        "quick_wins": [
            "Add one green CI run that includes tests, dependency install, and build checks.",
            "Preserve current deployment evidence.",
        ],
    }
    repairs = {
        "candidates": [],
        "advisories": [],
    }

    completion._refresh_client_actions(payload, repairs)

    assert not any("green ci run" in item.lower() for item in payload["quick_wins"])
    assert "Preserve current deployment evidence." in payload["quick_wins"]
    assert payload["repair_action_summary"]["ci_quick_win_suppressed_because_ci_verified_green"] is True
    assert payload["repair_action_summary"]["human_review_required"] is True


def test_non_green_ci_retains_relevant_ci_action() -> None:
    payload = {
        "sections": [
            {
                "id": "ci_cd",
                "status": "yellow",
                "score": 70,
                "findings": ["Required checks are failing."],
                "evidence": [],
            }
        ],
        "quick_wins": [
            "Add one green CI run that includes tests, dependency install, and build checks."
        ],
    }

    completion._refresh_client_actions(payload, {"candidates": [], "advisories": []})

    assert any("green ci run" in item.lower() for item in payload["quick_wins"])
    assert payload["repair_action_summary"]["ci_quick_win_suppressed_because_ci_verified_green"] is False


def test_installer_is_idempotent_and_preserves_no_write_boundary() -> None:
    first = install_client_output_truth_sanitization()
    second = install_client_output_truth_sanitization()

    assert first["status"] == "installed"
    assert second["friendly_note"] == "already_installed"
    assert second["final_section_reconciliation"] == "already_installed"
    assert second["client_actions"] == "already_installed"
    assert second["report_only"] is True
    assert second["automatic_application_allowed"] is False
