from __future__ import annotations

from pathlib import Path

from nico.assessment_recovery import REQUIRED_ASSESSMENT_RECOVERY_ROUTES


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def test_assessment_recovery_route_contract_is_exact() -> None:
    assert REQUIRED_ASSESSMENT_RECOVERY_ROUTES == {
        ("GET", "/operations/recovery/assessments"),
        ("POST", "/operations/recovery/assessment/{run_id}/resume"),
    }


def test_production_source_registers_and_validates_assessment_recovery_once() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "REQUIRED_ASSESSMENT_RECOVERY_ROUTES" in source
    assert "install_assessment_recovery" in source
    assert "OPERATIONS_ASSESSMENT_RECOVERY = install_assessment_recovery(app)" in source
    assert "| REQUIRED_ASSESSMENT_RECOVERY_ROUTES" in source
    assert (
        '_validate_group(existing, REQUIRED_ASSESSMENT_RECOVERY_ROUTES, "assessment recovery")'
        in source
    )
    assert "if not assessment_recovery_present:" in source
    assert "install_assessment_recovery(target)" in source
    assert '"OPERATIONS_ASSESSMENT_RECOVERY"' in source


def test_production_contract_does_not_register_a_second_assessment_execution_path() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")

    assert source.count('"/operations/recovery/assessments"') == 0
    assert source.count('"/operations/recovery/assessment/{run_id}/resume"') == 0
    assert source.count("install_assessment_recovery(target)") == 1
