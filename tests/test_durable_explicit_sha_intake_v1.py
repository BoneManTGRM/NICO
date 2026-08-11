from __future__ import annotations

from pathlib import Path


SOURCE = Path("nico/runtime_deployment_commit_resolution.py").read_text(encoding="utf-8")
NATIVE = Path("nico/comprehensive_native_providers.py").read_text(encoding="utf-8")
ROUTES = Path("nico/comprehensive_api_routes.py").read_text(encoding="utf-8")


def test_explicit_sha_intake_persists_run_before_repository_snapshot_io() -> None:
    assert "def _install_durable_explicit_sha_intake()" in SOURCE
    assert "requested_sha = routes.expected_commit_sha(payload)" in SOURCE
    assert "if not requested_sha:" in SOURCE
    assert "return current(request, payload)" in SOURCE
    assert '"commit_sha": requested_sha' in SOURCE
    assert 'routes._controller(request).start({' in SOURCE
    assert 'projected["repository_snapshot_verification"] = "required_next_stage"' in SOURCE
    assert 'projected["repository_processing_begun"] = False' in SOURCE
    durable_start = SOURCE.index('response = routes._controller(request).start({')
    assert "capture_repository_snapshot(" not in SOURCE[durable_start:SOURCE.index("setattr(intake", durable_start)]


def test_required_snapshot_stage_still_verifies_exact_commit_before_evidence() -> None:
    assert 'def snapshot_provider(context: dict[str, Any])' in NATIVE
    assert "snapshot = capture_repository_snapshot(context)" in NATIVE
    assert 'expected = _text(context.get("commit_sha"), 80).lower()' in NATIVE
    assert 'reason="immutable_snapshot_identity_drift"' in NATIVE
    assert '"immutable_repository_snapshot"' in Path("nico/comprehensive_orchestration_contract.py").read_text(encoding="utf-8")


def test_default_branch_intake_keeps_existing_snapshot_first_behavior() -> None:
    assert "requested_sha = expected_commit_sha(payload)" in ROUTES
    assert "snapshot = capture_repository_snapshot(" in ROUTES
    assert '"default_branch_intake_behavior_preserved": True' in SOURCE
    assert '"immutable_snapshot_stage_still_required": True' in SOURCE
    assert '"client_delivery_allowed": False' in SOURCE
