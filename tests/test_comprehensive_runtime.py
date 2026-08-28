from __future__ import annotations

import base64
import hashlib
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_runtime import configure_comprehensive_runtime


def _executors() -> dict:
    executors = {}
    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            result = {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            if _capability == "final_report_generation":
                identity = {
                    key: context[key]
                    for key in (
                        "run_id",
                        "repository",
                        "commit_sha",
                        "evidence_ledger_id",
                    )
                }
                identity["report_language"] = "en"
                pdf = b"%PDF-1.4\n%%EOF\n"
                canonical = {
                    "report_language": "en",
                    "locale": "en",
                    "identity": identity,
                    "assessment": {
                        "report_language": "en",
                        "locale": "en",
                    },
                }
                result["report_package"] = {
                    "report_id": f"report_{context['run_id']}",
                    "report_language": "en",
                    "locale": "en",
                    "markdown": (
                        "# NICO Comprehensive Technical Assessment\n"
                        "CLIENT DELIVERY NOT AUTHORIZED"
                    ),
                    "html": (
                        "<html><body>NICO Comprehensive Technical Assessment</body></html>"
                    ),
                    "pdf_base64": base64.b64encode(pdf).decode("ascii"),
                    "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                    "pdf_page_count": 1,
                    "json": canonical,
                    "canonical_truth_sha256": canonical_sha256(canonical),
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            return result

        executors[capability] = execute
    return executors


def _payload() -> dict:
    return {
        "run_id": "comprun_runtime_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "immutable123",
        "evidence_ledger_id": "ledger_runtime_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _continue_to_review(client: TestClient, run_id: str, *, timeout: float = 4.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        response = client.post(f"/assessment/comprehensive-run/{run_id}/continue")
        assert response.status_code == 200
        last = response.json()
        if last.get("status") == "review_required":
            return last
        assert last.get("status") == "running"
        assert last.get("client_delivery_allowed") is False
        time.sleep(0.02)
    raise AssertionError(f"run did not reach human review before timeout: {last}")


def test_runtime_mounts_durable_native_routes(tmp_path: Path) -> None:
    path = tmp_path / "comprehensive.db"
    app = FastAPI()
    configure_comprehensive_runtime(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )

    client = TestClient(app)
    started = client.post("/assessment/comprehensive-run", json=_payload())
    assert started.status_code == 200
    assert started.json()["run_id"] == "comprun_runtime_001"

    body = _continue_to_review(client, "comprun_runtime_001")
    assert body["status"] == "review_required"
    assert body["progress_percent"] == 100.0
    assert body["human_review_required"] is True
    assert body["client_delivery_allowed"] is False
    assert body["reports"]["report_id"] == "report_comprun_runtime_001"
    assert body["reports"]["markdown"].startswith(
        "# NICO Comprehensive Technical Assessment"
    )
    assert body["reports"]["pdf_base64"].startswith("JVBER")
    projected_final = body["record"]["stage_results"][
        "final_comprehensive_report_generation"
    ]
    assert projected_final["status"] == "complete"
    assert "report_package" in projected_final["omitted_large_fields"]
    assert body["response_projection"]["terminal_report_attached"] is True

    restarted = FastAPI()
    configure_comprehensive_runtime(
        restarted,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    restored = TestClient(restarted).get(
        "/assessment/comprehensive-run/comprun_runtime_001"
    )
    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["integrity_sha256"] == body["integrity_sha256"]
    assert restored_body["revision"] == body["revision"]
    assert restored_body["reports"]["report_id"] == "report_comprun_runtime_001"
    assert restored_body["reports"]["canonical_truth_sha256"] == canonical_sha256(
        restored_body["reports"]["json"]
    )
    assert restored_body["human_review_required"] is True
    assert restored_body["client_delivery_allowed"] is False


def test_runtime_rejects_missing_capabilities(tmp_path: Path) -> None:
    app = FastAPI()
    executors = _executors()
    executors.pop(next(iter(executors)))

    with pytest.raises(RuntimeError, match="comprehensive_capabilities_missing"):
        configure_comprehensive_runtime(
            app,
            capability_executors=executors,
            connection_factory=lambda: sqlite3.connect(tmp_path / "missing.db"),
            dialect="sqlite",
        )

    assert not any(
        str(getattr(route, "path", "")).startswith(
            "/assessment/comprehensive-run"
        )
        for route in app.routes
    )


def test_runtime_requires_postgres_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="comprehensive_database_url_required"):
        configure_comprehensive_runtime(FastAPI(), capability_executors=_executors())

    with pytest.raises(RuntimeError, match="comprehensive_database_url_must_be_postgres"):
        configure_comprehensive_runtime(
            FastAPI(),
            capability_executors=_executors(),
            database_url="sqlite:///unsafe.db",
        )


def test_runtime_metadata_discloses_durable_boundary_without_secrets(
    tmp_path: Path,
) -> None:
    app = FastAPI()
    configure_comprehensive_runtime(
        app,
        capability_executors=_executors(),
        connection_factory=lambda: sqlite3.connect(tmp_path / "metadata.db"),
        dialect="sqlite",
    )

    metadata = app.state.comprehensive_runtime
    assert metadata["service_id"] == "comprehensive"
    assert metadata["configured"] is True
    assert metadata["persistence_adapter"] == "sqlite"
    assert metadata["required_capability_count"] == len(execution_plan())
    assert metadata["human_review_required"] is True
    assert metadata["client_delivery_allowed"] is False
    assert "database_url" not in metadata
