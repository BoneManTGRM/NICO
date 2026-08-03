from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import two_service_live_acceptance_v3 as acceptance_v13


def _state(phase_label: str) -> dict[str, str]:
    return {
        "phase_label": phase_label,
        "message": "",
        "run_id": "comprun_terminal_reconciliation",
        "commit_sha": "a" * 40,
        "scanner": "Complete with disclosed limitations",
        "report": "Complete",
        "review": "Internal review required",
        "score": "Exceptional · 93/100",
        "page_url": "https://app.nicoaudit.com/assessment",
    }


def test_final_terminal_ui_read_closes_backend_poll_race() -> None:
    acceptance_v13.install_current_review_terminal_phases()

    assert acceptance_v13._terminal_ui_observed(
        False,
        _state("Internal review required"),
    ) is True


def test_spanish_final_terminal_ui_read_closes_backend_poll_race() -> None:
    acceptance_v13.install_current_review_terminal_phases()

    assert acceptance_v13._terminal_ui_observed(
        False,
        _state("Revisión interna requerida"),
    ) is True


def test_nonterminal_final_ui_read_remains_unverified() -> None:
    acceptance_v13.install_current_review_terminal_phases()

    assert acceptance_v13._terminal_ui_observed(
        False,
        _state("Generating final report"),
    ) is False


def test_prior_terminal_observation_remains_authoritative() -> None:
    acceptance_v13.install_current_review_terminal_phases()

    assert acceptance_v13._terminal_ui_observed(
        True,
        _state("Generating final report"),
    ) is True
