from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recovery_installers_are_idempotent_in_an_isolated_runtime() -> None:
    script = r'''
import json
from nico.assessment_recovery_execution_patch import install_assessment_recovery_execution_patch
from nico.assessment_recovery_readiness_patch import install_assessment_recovery_readiness_patch
from nico.mid_checkpoint_optional_evidence_compat import install_mid_checkpoint_optional_evidence_compat
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

first = {
    "execution": install_assessment_recovery_execution_patch(),
    "compatibility": install_mid_checkpoint_optional_evidence_compat(),
    "readiness": install_assessment_recovery_readiness_patch(),
}
second = {
    "execution": install_assessment_recovery_execution_patch(),
    "compatibility": install_mid_checkpoint_optional_evidence_compat(),
    "readiness": install_assessment_recovery_readiness_patch(),
}
print(json.dumps({
    "first": first,
    "second": second,
    "routes": sorted(REQUIRED_OPERATION_ROUTES),
}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["first"]["execution"]["installed"] is True
    assert payload["first"]["execution"]["idempotent_reuse"] is False
    assert payload["first"]["compatibility"]["idempotent_reuse"] is False
    assert payload["first"]["readiness"]["idempotent_reuse"] is False
    assert payload["second"]["execution"]["idempotent_reuse"] is True
    assert payload["second"]["compatibility"]["idempotent_reuse"] is True
    assert payload["second"]["readiness"]["idempotent_reuse"] is True
    assert "GET /operations/recovery/assessments" in payload["routes"]
    assert (
        "POST /operations/recovery/assessment/{run_id}/resume"
        in payload["routes"]
    )


def test_execution_patch_uses_checkpointed_orchestration_for_all_four_paths() -> None:
    source = (
        ROOT / "nico" / "assessment_recovery_execution_patch.py"
    ).read_text(encoding="utf-8")

    assert source.count("result = _run_checkpointed(") == 4
    assert 'new_id("fullrun")' in source
    assert 'mid_api.new_id("midrun")' in source
    assert "orchestrator=orchestrator" in source
    assert "wrap_handlers=orchestrator is canonical_orchestrator" in source
    assert "full_api.full_assessment_response = full_assessment_response" in source
    assert (
        "full_api.full_assessment_status_response = full_assessment_status_response"
        in source
    )
    assert "mid_api.mid_assessment_response = mid_assessment_response" in source
    assert (
        "mid_api.mid_assessment_status_response = mid_assessment_status_response"
        in source
    )


def test_mid_optional_evidence_compat_reissues_only_when_checkpoint_preseed_omitted_it() -> None:
    source = (
        ROOT / "nico" / "mid_checkpoint_optional_evidence_compat.py"
    ).read_text(encoding="utf-8")

    assert 'if result.get("optional_evidence_submission")' in source
    assert "issue_mid_evidence_submission_access" in source
    assert 'run_id.startswith("midrun_")' in source
    assert "mid_api.mid_assessment_response = mid_assessment_response" in source


def test_production_initialization_orders_execution_before_hosted_route_registration() -> None:
    source = (ROOT / "nico" / "api" / "production.py").read_text(encoding="utf-8")
    package_source = (ROOT / "nico" / "__init__.py").read_text(encoding="utf-8")

    execution_index = source.index("install_assessment_recovery_execution_patch()")
    compatibility_index = source.index("install_mid_checkpoint_optional_evidence_compat()")
    readiness_index = source.index("install_assessment_recovery_readiness_patch()")
    hosted_index = source.index('import_module("nico.api.hosted")')

    assert execution_index < compatibility_index < readiness_index < hosted_index
    assert "install_assessment_recovery_execution_patch" not in package_source
    assert "install_mid_checkpoint_optional_evidence_compat" not in package_source
    assert "install_assessment_recovery_readiness_patch" not in package_source
