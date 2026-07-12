from __future__ import annotations

import json
import subprocess
import sys
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


def test_production_openapi_resolves_checkpointed_mid_and_full_request_models() -> None:
    script = r'''
import json
from nico.api.production import app
schema = app.openapi()
paths = schema.get("paths") or {}
print(json.dumps({
    "full": "/assessment/full-run" in paths,
    "full_status": "/assessment/full-run/{run_id}/status" in paths,
    "mid": "/assessment/mid-run" in paths,
    "mid_status": "/assessment/mid-run/{run_id}/status" in paths,
    "inventory": "/operations/recovery/assessments" in paths,
    "resume": "/operations/recovery/assessment/{run_id}/resume" in paths,
}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result == {
        "full": True,
        "full_status": True,
        "mid": True,
        "mid_status": True,
        "inventory": True,
        "resume": True,
    }
