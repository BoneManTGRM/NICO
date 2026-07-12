from __future__ import annotations

from pathlib import Path

from nico.assessment_recovery_execution_patch import (
    install_assessment_recovery_execution_patch,
)
from nico.assessment_recovery_readiness_patch import (
    install_assessment_recovery_readiness_patch,
)
from nico.mid_checkpoint_optional_evidence_compat import (
    install_mid_checkpoint_optional_evidence_compat,
)
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


ROOT = Path(__file__).resolve().parents[1]


def test_recovery_installers_are_idempotent_and_routes_are_required() -> None:
    execution = install_assessment_recovery_execution_patch()
    compatibility = install_mid_checkpoint_optional_evidence_compat()
    readiness = install_assessment_recovery_readiness_patch()

    assert execution["installed"] is True
    assert execution["idempotent_reuse"] is True
    assert compatibility["installed"] is True
    assert compatibility["idempotent_reuse"] is True
    assert readiness["installed"] is True
    assert readiness["idempotent_reuse"] is True
    assert "GET /operations/recovery/assessments" in REQUIRED_OPERATION_ROUTES
    assert (
        "POST /operations/recovery/assessment/{run_id}/resume"
        in REQUIRED_OPERATION_ROUTES
    )


def test_execution_patch_uses_checkpointed_orchestration_for_all_four_paths() -> None:
    source = (
        ROOT / "nico" / "assessment_recovery_execution_patch.py"
    ).read_text(encoding="utf-8")

    assert source.count("run_checkpointed_assessment_orchestration(") == 4
    assert "new_id(\"fullrun\")" in source
    assert "new_id(\"midrun\")" in source
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
    assert "run_id.startswith(\"midrun_\")" in source
    assert "mid_api.mid_assessment_response = mid_assessment_response" in source


def test_package_initialization_orders_execution_before_mid_compatibility() -> None:
    source = (ROOT / "nico" / "__init__.py").read_text(encoding="utf-8")

    execution_index = source.index("install_assessment_recovery_execution_patch()")
    compatibility_index = source.index("install_mid_checkpoint_optional_evidence_compat()")
    readiness_index = source.index("install_assessment_recovery_readiness_patch()")

    assert execution_index < compatibility_index < readiness_index
