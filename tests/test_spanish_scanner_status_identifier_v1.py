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


def test_configuration_failure_keeps_failure_meaning_and_exact_identifier():
    """Configuration failure is an existing canonical state, not an unknown result."""
    from nico.comprehensive_spanish_canonical_report_v87 import _scanner_status_visible
    from nico.comprehensive_spanish_current_copy_worker_v98 import install_comprehensive_spanish_current_copy_worker_v98
    assert install_comprehensive_spanish_current_copy_worker_v98()['bound'] is True
    expected = 'configuration_failed (configuración fallida)'
    assert _scanner_status_visible('configuration_failed') == expected
    execution = _translate_presentation(_execution_line('configuration_failed'))
    limitation = _translate_presentation(_limitation_line('configuration_failed'))
    assert f'estado={expected}' in execution
    assert f'permanece {expected}:' in limitation
    assert f'estado={expected}' in limitation
    assert 'completada' not in execution + limitation


def test_unrecognized_scanner_status_still_fails_translation_explicitly():
    from nico.comprehensive_spanish_canonical_report_v87 import _scanner_status_visible
    with pytest.raises(ValueError, match='missing Spanish scanner status translation'):
        _scanner_status_visible('not_a_supported_scanner_status')
