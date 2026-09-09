"""Final-report identity must be validated before operator source acquisition."""
from types import SimpleNamespace

import pytest

from nico import hosted_provider_comprehensive_runtime_v1 as runtime
from nico.phase3_engagement_intake_v1 import client_delivery_identity_valid


def payload():
    return {
        "repository": "owner/synthetic-fixture", "provider": "github",
        "customer_id": "synthetic_customer", "project_id": "synthetic_project",
        "client_name": "SYNTHETIC SOFTWARE-TEST INFORMATION - client",
        "project_name": "SYNTHETIC SOFTWARE-TEST INFORMATION - project",
        "authorized": True, "authorization_confirmed": True,
        "expected_commit_sha": "a" * 40, "execution_mode": "internal_test",
        "human_evidence": {"stakeholder_context": {
            "reviewer": "OpenAI Codex - synthetic test supplier",
            "evidence": {"access_method": ["Read-only fixture access"],
                         "primary_technical_contact": ["Synthetic contact - no real person"],
                         "authorized_scope": ["Owner-authorized fixture only"]}}},
    }


@pytest.mark.parametrize("field", ["client_name", "project_name", "access_method", "primary_technical_contact", "authorized_scope"])
def test_missing_final_identity_rejected_before_acquisition(monkeypatch, field):
    data = payload()
    if field in data:
        del data[field]
    else:
        del data["human_evidence"]["stakeholder_context"]["evidence"][field]
    monkeypatch.setattr(runtime, "_operator_required", lambda token: None)
    monkeypatch.setattr(runtime, "capture_repository_snapshot", lambda *_: pytest.fail("source capture before identity validation"))
    with pytest.raises(ValueError, match="(?:client|project)_.*required"):
        runtime._operator_intake(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())), data, "synthetic")


def test_operator_final_identity_reaches_controller(monkeypatch):
    from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY
    monkeypatch.setattr(runtime, "_operator_required", lambda token: None)
    monkeypatch.setattr(ProviderRolloutRegistry, "preflight", lambda *args, **kwargs: {})
    monkeypatch.setattr(runtime, "capture_repository_snapshot", lambda data: {"status": "attached", "commit_sha": "a" * 40})
    class Controller:
        def start(self, data):
            record = {"identity": {"customer_id": data["customer_id"], "project_id": data["project_id"]},
                      "human_evidence": {"modules": data["human_evidence"]}}
            assert client_delivery_identity_valid(record)
            assert data["client_name"] == payload()["client_name"]
            assert data["project_name"] == payload()["project_name"]
            raise RuntimeError("validated-controller-boundary")
    monkeypatch.setattr(runtime.api_routes, "_controller", lambda request: Controller())
    state = SimpleNamespace()
    setattr(state, STATE_KEY, ProviderRolloutRegistry())
    with pytest.raises(RuntimeError, match="validated-controller-boundary"):
        runtime._operator_intake(SimpleNamespace(app=SimpleNamespace(state=state)), payload(), "synthetic")


@pytest.mark.parametrize("mode", ["production_engagement", "PRODUCTION_ENGAGEMENT", " production_engagement "])
def test_production_mode_cannot_omit_identity(monkeypatch, mode):
    data = payload()
    del data["client_name"]
    del data["project_name"]
    data["execution_mode"] = mode
    monkeypatch.setattr(runtime, "_operator_required", lambda token: None)
    with pytest.raises(ValueError, match="client_identity_required"):
        runtime._operator_intake(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())), data, "synthetic")


def test_complete_identity_survives_real_controller_storage(monkeypatch, tmp_path):
    import sqlite3
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY
    database = tmp_path / "engagement.db"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    service = ComprehensiveRunService(store, {})
    controller = ComprehensiveApiController(service)
    monkeypatch.setattr(runtime, "_operator_required", lambda token: None)
    monkeypatch.setattr(ProviderRolloutRegistry, "preflight", lambda *args, **kwargs: {})
    monkeypatch.setattr(runtime, "capture_repository_snapshot", lambda data: {"status": "attached", "commit_sha": "a" * 40})
    monkeypatch.setattr(runtime.api_routes, "_controller", lambda request: controller)
    monkeypatch.setattr(runtime.api_routes, "_with_runtime_truth", lambda request, result: result)
    state = SimpleNamespace()
    setattr(state, STATE_KEY, ProviderRolloutRegistry())
    started = runtime._operator_intake(SimpleNamespace(app=SimpleNamespace(state=state)), payload(), "synthetic")
    saved = service.load(started["run_id"])
    assert client_delivery_identity_valid(saved)
    assert saved["identity"]["commit_sha"] == "a" * 40
    assert saved.get("accepted_edition") is None
    assert saved.get("delivery_authorization") is None
