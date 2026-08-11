from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_storage_availability_patch_v1 import (
    ComprehensiveStorageUnavailable,
    install_comprehensive_storage_availability_patch_v1,
)


def _executors() -> dict:
    return {
        str(item["capability"]): (
            lambda context, _capability=str(item["capability"]): {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
        for item in execution_plan()
    }


def _payload() -> dict:
    return {
        "run_id": "comprun_storage_unavailable",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_storage_unavailable",
        "customer_id": "customer_storage",
        "project_id": "project_storage",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _unavailable_connection():
    raise OSError("simulated production database outage")


def test_connection_factory_failure_is_bounded_storage_unavailable() -> None:
    installation = install_comprehensive_storage_availability_patch_v1()
    assert installation["status"] == "installed"
    assert installation["automatic_cross_store_fallback"] is False

    store = ComprehensiveRunStore(_unavailable_connection, dialect="postgres")
    with pytest.raises(
        ComprehensiveStorageUnavailable,
        match="comprehensive_database_unavailable",
    ):
        store.ensure_schema()

    probe = store.live_persistence_probe()  # type: ignore[attr-defined]
    assert probe == {
        "artifact_schema": "nico.comprehensive_storage_availability_patch.v1",
        "status": "unavailable",
        "available": False,
        "adapter": "postgres",
        "error_detail_exposed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_production_bootstrap_stays_up_and_fails_closed_when_database_is_down() -> None:
    install_comprehensive_storage_availability_patch_v1()
    app = FastAPI()

    controller = install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
        connection_factory=_unavailable_connection,
        dialect="postgres",
    )

    assert controller is None
    runtime = app.state.comprehensive_runtime
    assert runtime["status"] == "blocked"
    assert runtime["configured"] is False
    assert runtime["reason"] == "comprehensive_database_unavailable"
    assert runtime["persistence_adapter"] == "unavailable"
    assert runtime["survives_container_replacement_verified"] is False
    assert runtime["human_review_required"] is True
    assert runtime["client_delivery_allowed"] is False

    response = TestClient(app).post("/assessment/comprehensive-run", json=_payload())
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_service_not_configured"
    assert detail["reason"] == "comprehensive_database_unavailable"
    assert "simulated production database outage" not in str(detail)
    assert detail["retryable"] is True
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False


def test_runtime_storage_failure_translates_to_safe_503() -> None:
    install_comprehensive_storage_availability_patch_v1()
    from nico import comprehensive_api_routes as routes

    translated = routes._translate_error(
        ComprehensiveStorageUnavailable("private database detail")
    )
    assert translated.status_code == 503
    detail = translated.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "comprehensive_database_unavailable"
    assert detail["retryable"] is True
    assert detail["persistence_diagnostic_required"] is True
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False
    assert "private database detail" not in str(detail)


def test_terminal_bootstrap_installs_storage_guard_before_production_app_import() -> None:
    source = Path("nico/api/terminal_authority_bootstrap.py").read_text(encoding="utf-8")
    install_at = source.index("COMPREHENSIVE_STORAGE_AVAILABILITY = install_comprehensive_storage_availability_patch_v1()")
    app_import_at = source.index("from nico.api.comprehensive_production_bootstrap import app")
    assert install_at < app_import_at
    assert '"automatic_cross_store_fallback": False' in Path(
        "nico/comprehensive_storage_availability_patch_v1.py"
    ).read_text(encoding="utf-8")
