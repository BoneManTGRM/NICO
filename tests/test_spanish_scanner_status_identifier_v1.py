"""Spanish reports keep exact scanner-status identifiers."""
import pytest

from nico.comprehensive_spanish_canonical_report_v87 import (
    _SCANNER_STATUS_ES,
    _translate_presentation,
)


def _execution_line(status: str) -> str:
    return (
        f"bandit: status={status}; exact_commit_match=True; "
        "verified_complete=True; findings=1; artifact_hash=abc"
    )


def _limitation_line(status: str) -> str:
    return (
        f"bandit exact-SHA evidence remains {status}: status={status}; "
        "current_run_not_proven"
    )


@pytest.mark.parametrize("status,label", sorted(_SCANNER_STATUS_ES.items()))
def test_execution_line_keeps_identifier_or_display_label(status, label):
    rendered = _translate_presentation(_execution_line(status))
    assert label in rendered
    if "_" in status:
        assert status in rendered
        assert f"estado={status} ({label})" in rendered
    else:
        assert f"estado={label}" in rendered
        assert f"estado={status}" not in rendered


@pytest.mark.parametrize(
    "status",
    [status for status in _SCANNER_STATUS_ES if "_" in status],
)
def test_limitation_line_keeps_machine_identifier(status):
    rendered = _translate_presentation(_limitation_line(status))
    label = _SCANNER_STATUS_ES[status]
    assert status in rendered
    assert rendered.count(status) == 2
    assert label in rendered
    assert "La evidencia de bandit para el SHA exacto permanece" in rendered


def test_ordinary_completed_and_failed_labels_stay_spanish_only():
    completed = _translate_presentation(_execution_line("completed"))
    failed = _translate_presentation(_limitation_line("failed"))
    assert "estado=completada" in completed
    assert "completed_with_findings" not in completed
    assert "estado=completed" not in completed
    assert "permanece fallida" in failed
    assert "estado=fallida" in failed
    assert "failed" not in failed
