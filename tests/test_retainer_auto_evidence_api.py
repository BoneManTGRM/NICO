from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.api.main as main
import nico.retainer_auto_evidence_api as api
from nico.retainer_auto_evidence_api import (
    RETAINER_AUTO_EVIDENCE_VERSION,
    RETAINER_OPS_ROUTE,
    install_retainer_auto_evidence,
)


class _Store:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert table == "assessment_runs"
        self.records[item_id] = deepcopy(payload)
        return deepcopy(payload)

    def get(self, table: str, item_id: str):
        return deepcopy(self.records.get(item_id))

    def list(self, table: str, customer_id=None, project_id=None):
        return []


def _result() -> dict[str, Any]:
    return {
        "status": "needs_more_retainer_evidence",
        "workflow": "ongoing_product_engineering_retainer",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "maturity_signal": {"level": "Mid", "score": 65, "calculated": True},
        "evidence_readiness": {"readiness_score": 80, "calculated": True},
        "source_binding": {
            "status": "bound",
            "repository": "BoneManTGRM/NICO",
            "observed_commit_sha": "a" * 40,
            "checked_at": "2026-07-12T23:00:00Z",
            "baseline": {
                "run_id": "midrun_1234567890abcdef",
                "snapshot_id": "snapshot_1",
                "snapshot_commit_sha": "b" * 40,
                "scanner_id": "scan_1",
            },
        },
        "sections": [
            {
                "id": "weekly_delivery",
                "status": "yellow",
                "score": 65,
                "score_calculated": True,
            },
            {
                "id": "blockers",
                "status": "unverified",
                "score": 0,
                "score_calculated": False,
            },
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _route_count(app: FastAPI) -> int:
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == RETAINER_OPS_ROUTE[1]
        and RETAINER_OPS_ROUTE[0]
        in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def test_installer_replaces_legacy_retainer_route_once() -> None:
    app = FastAPI()

    @app.post("/retainer/ops")
    def legacy_route():
        return {"status": "legacy"}

    first = install_retainer_auto_evidence(app)
    second = install_retainer_auto_evidence(app)

    assert first["installed"] is True
    assert first["legacy_routes_removed"] == 1
    assert first["technical_evidence_mode"] == "automatic_github_ingestion"
    assert second["idempotent_reuse"] is True
    assert _route_count(app) == 1
    assert app.state.retainer_auto_evidence_version == RETAINER_AUTO_EVIDENCE_VERSION


def test_endpoint_requires_authorization(monkeypatch) -> None:
    app = FastAPI()
    install_retainer_auto_evidence(app)
    client = TestClient(app)

    response = client.post(
        "/retainer/ops",
        json={"repository": "BoneManTGRM/NICO", "authorized": False},
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["status"] == "blocked"
    assert payload["message"] == "Request blocked by NICO safety, authorization, or review policy."


def test_endpoint_auto_ingests_and_persists_only_bounded_summary(monkeypatch) -> None:
    store = _Store()
    monkeypatch.setattr(main, "STORE", store)
    monkeypatch.setattr(main, "_LAST_HOSTED_ASSESSMENT", {})
    monkeypatch.setattr(main, "_LAST_MID_ASSESSMENT", {})
    monkeypatch.setattr(main, "_LAST_RETAINER_OPS", {})

    captured: dict[str, Any] = {}

    def fake_ingestion(payload, **kwargs):
        captured["input"] = deepcopy(payload)
        enriched = deepcopy(payload)
        enriched.update(
            {
                "repository": "BoneManTGRM/NICO",
                "source_binding": {
                    "status": "bound",
                    "repository": "BoneManTGRM/NICO",
                    "observed_commit_sha": "a" * 40,
                    "checked_at": "2026-07-12T23:00:00Z",
                    "baseline": {
                        "run_id": "midrun_1234567890abcdef",
                        "snapshot_id": "snapshot_1",
                        "snapshot_commit_sha": "b" * 40,
                        "scanner_id": "scan_1",
                    },
                },
                "retainer_evidence_ingestion": {"status": "complete"},
            }
        )
        return enriched

    monkeypatch.setattr(api, "build_retainer_evidence_payload", fake_ingestion)
    monkeypatch.setattr(api, "build_truth_bound_retainer_ops", lambda payload: _result())

    app = FastAPI()
    install_retainer_auto_evidence(app)
    client = TestClient(app)
    response = client.post(
        "/retainer/ops",
        json={
            "repository": "BoneManTGRM/NICO",
            "authorized": True,
            "authorized_by": "owner",
            "authorization_scope": "repository assessment only",
            "customer_id": "customer_1",
            "project_id": "project_1",
            "timeframe_days": 30,
            "roadmap_notes": "Approved priorities",
            "client_update": "Draft update for human review",
            "retainer_metrics": "Two merged PRs",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_binding"]["observed_commit_sha"] == "a" * 40
    assert payload["client_delivery_allowed"] is False
    assert captured["input"]["roadmap_notes"] == "Approved priorities"

    record = store.records["retainer_customer_1_project_1"]
    assert record["repository"] == "BoneManTGRM/NICO"
    assert record["source_binding"]["baseline_run_id"] == "midrun_1234567890abcdef"
    assert record["summary"]["section_statuses"]["blockers"]["score_calculated"] is False
    rendered = repr(record)
    assert "Draft update for human review" not in rendered
    assert "Two merged PRs" not in rendered


def test_openapi_accepts_repository_baseline_and_business_context_fields() -> None:
    app = FastAPI()
    install_retainer_auto_evidence(app)
    schema = app.openapi()
    request_schema = schema["components"]["schemas"]["RetainerAutoOpsRequest"]
    properties = request_schema["properties"]

    for field in (
        "repository",
        "baseline_run_id",
        "timeframe_days",
        "roadmap_notes",
        "client_update",
        "retainer_metrics",
        "success_metrics",
        "budget_priorities",
    ):
        assert field in properties
    for legacy in ("commit_summary", "pr_summary", "issue_summary", "blockers", "release_notes"):
        assert legacy in properties
