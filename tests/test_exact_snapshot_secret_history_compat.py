from __future__ import annotations

import nico.assessment_score_integrity_compat as legacy
import nico.exact_snapshot_secret_history as history
import nico.exact_snapshot_secret_history_compat as compat
import nico.full_assessment_scorecard as scorecard


def test_legacy_scanner_record_uses_established_scoring(monkeypatch) -> None:
    expected = {"id": "secrets_review", "score": 91, "status": "green"}
    monkeypatch.setattr(legacy, "calibrated_secrets_section", lambda repo, scanner: expected)
    monkeypatch.setattr(history, "history_secrets_section", lambda repo, scanner: {"score": 20})

    result = compat.compatible_history_secrets_section(
        {"code_signal_evidence": {"potential_secret_pattern_hits": 0}},
        {
            "tools_run": ["gitleaks", "trufflehog"],
            "scanner_results": [
                {"scanner": "gitleaks", "status": "passed"},
                {"scanner": "trufflehog", "status": "passed"},
            ],
        },
    )

    assert result is expected


def test_structured_history_record_uses_exact_history_scoring(monkeypatch) -> None:
    expected = {"id": "secrets_review", "score": 95, "status": "green"}
    monkeypatch.setattr(history, "history_secrets_section", lambda repo, scanner: expected)
    monkeypatch.setattr(legacy, "calibrated_secrets_section", lambda repo, scanner: {"score": 68})

    result = compat.compatible_history_secrets_section(
        {},
        {
            "scanner_results": [
                {
                    "scanner": "gitleaks",
                    "status": "passed",
                    "execution_completed": True,
                    "full_history_covered": True,
                    "history_commit_count": 100,
                }
            ]
        },
    )

    assert result is expected


def test_history_score_compatibility_installer_is_idempotent() -> None:
    first = compat.install_secret_history_score_compatibility()
    second = compat.install_secret_history_score_compatibility()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert scorecard._secrets_section is compat.compatible_history_secrets_section
