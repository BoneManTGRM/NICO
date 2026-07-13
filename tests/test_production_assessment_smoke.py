from __future__ import annotations

import json
from typing import Any

import pytest

from nico.hosted_smoke_test import SMOKE_TESTS, _production_assessment_smoke_validation, build_hosted_smoke_test
from nico.production_assessment_smoke import (
    CONFIRMATION_PHRASE,
    SmokeConfig,
    SmokeFailure,
    build_smoke_artifact,
    validate_config,
)

SHA = "a" * 40


class FakeTransport:
    def __init__(self, *, changed_full_run: bool = False, conflicting_express_boundary: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, bool]] = []
        self.changed_full_run = changed_full_run
        self.conflicting_express_boundary = conflicting_express_boundary

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        admin: bool = False,
    ) -> dict[str, Any]:
        self.calls.append((method, path, payload, admin))
        if path == "/health":
            return {"status": "ok"}
        if path == "/targets":
            return {"status": "ok"}
        if path == "/assessment/github":
            result: dict[str, Any] = {
                "status": "complete",
                "run_id": "express_1",
                "human_review_required": True,
                "client_ready": False,
                "reports": {"report_id": "report_express_1", "markdown": "draft"},
                "unavailable_data_notes": ["provider token=must-not-be-retained"],
            }
            if self.conflicting_express_boundary:
                result["delivery"] = {"client_delivery_allowed": True}
            return result
        if path == "/assessment/mid-run":
            return {
                "status": "running",
                "run_id": "midrun_exact_1",
                "human_review_required": True,
                "client_ready": False,
            }
        if path == "/assessment/mid-run/midrun_exact_1/status":
            return {
                "status": "complete",
                "run_id": "midrun_exact_1",
                "human_review_required": True,
                "client_ready": False,
                "report_generation_status": "complete",
                "mid_report": {
                    "report_id": "report_mid_1",
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "approval_request": {"approval_id": "review_mid_1", "status": "pending"},
            }
        if path == "/assessment/full-run":
            return {
                "status": "running",
                "run_id": "fullrun_exact_1",
                "human_review_required": True,
                "client_ready": False,
            }
        if path == "/assessment/full-run/fullrun_exact_1/status":
            return {
                "status": "complete",
                "run_id": "fullrun_changed" if self.changed_full_run else "fullrun_exact_1",
                "human_review_required": True,
                "client_ready": False,
                "reports": {
                    "report_id": "report_full_1",
                    "markdown": "draft",
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "approval": {"approval_id": "review_full_1", "status": "pending"},
            }
        if path.startswith("/assessment/full-run/fullrun_exact_1/approved-delivery/readiness?"):
            assert admin is True
            return {
                "status": "blocked",
                "ready": False,
                "lifecycle": "blocked",
                "checks": [{"id": "human_approval", "passed": False}],
                "summary": {
                    "access_grant_count": 0,
                    "verified_receipt_count": 0,
                    "verified_acknowledgment_count": 0,
                },
            }
        raise AssertionError(f"Unexpected production-smoke path: {path}")


def config(**overrides: Any) -> SmokeConfig:
    values: dict[str, Any] = {
        "frontend_url": "https://app.nicoaudit.com",
        "backend_url": "https://nico-production-690a.up.railway.app",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_nico_smoke",
        "project_id": "project_nico_smoke",
        "authorization_reference": "authorization/ref-1",
        "github_repository": "BoneManTGRM/NICO",
        "github_sha": SHA,
        "confirmation": CONFIRMATION_PHRASE,
        "poll_attempts": 3,
        "poll_interval_seconds": 0,
    }
    values.update(overrides)
    return SmokeConfig(**values)


def deployment() -> dict[str, Any]:
    return {
        "status": "passed",
        "frontend_commit": SHA,
        "backend_commit": SHA,
        "checks": [
            {"context": "Vercel", "state": "success", "provider": "vercel"},
            {"context": "successful-cat - NICO", "state": "success", "provider": "railway"},
        ],
    }


def browser() -> dict[str, Any]:
    return {
        "status": "passed",
        "frontend_commit": SHA,
        "no_assessment_started": True,
        "checks": [{"id": "unified_heading", "passed": True}],
    }


def complete_hosted_evidence(artifact: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for case in SMOKE_TESTS:
        if case["evidence_key"] == "production_assessment_smoke":
            evidence[case["evidence_key"]] = artifact
        else:
            evidence[case["evidence_key"]] = {"status": case.get("required_status") or "ok"}
    return evidence


def test_controlled_smoke_emits_hosted_contract_and_one_start_per_tier() -> None:
    transport = FakeTransport()
    artifact = build_smoke_artifact(config(), transport, deployment(), browser(), sleep=lambda _seconds: None)

    assert artifact["status"] == "passed"
    assert artifact["proof"] == {
        "one_start_per_tier": True,
        "exact_run_continuation": True,
        "human_review_boundary_preserved": True,
        "no_client_ready_claim": True,
        "duplicate_start_guard": True,
        "forbidden_operation_requests": 0,
        "client_delivery_blocked": True,
    }
    assert [item["tier"] for item in artifact["tiers"]] == ["express", "mid", "full"]
    assert all(item["start_count"] == 1 for item in artifact["tiers"])
    assert artifact["tiers"][1]["status_path"] == "/assessment/mid-run/midrun_exact_1/status"
    assert artifact["tiers"][2]["status_path"] == "/assessment/full-run/fullrun_exact_1/status"

    paths = [path for _method, path, _payload, _admin in transport.calls]
    assert paths.count("/assessment/github") == 1
    assert paths.count("/assessment/mid-run") == 1
    assert paths.count("/assessment/full-run") == 1
    assert not any(
        method == "POST" and any(fragment in path for fragment in ("/approval", "/delivery", "/repair"))
        for method, path, _payload, _admin in transport.calls
    )
    admin_calls = [(method, path) for method, path, _payload, admin in transport.calls if admin]
    assert len(admin_calls) == 1
    assert admin_calls[0][0] == "GET"
    assert "/approved-delivery/readiness?" in admin_calls[0][1]
    assert artifact["delivery_boundary"] == {
        "status": "blocked",
        "ready": False,
        "lifecycle": "blocked",
        "human_approval_passed": False,
        "access_grant_count": 0,
        "verified_receipt_count": 0,
        "verified_acknowledgment_count": 0,
    }
    assert "must-not-be-retained" not in json.dumps(artifact)
    assert artifact["tiers"][0]["unavailable_evidence"][0].startswith("unavailable_note_sha256:")

    passed, note = _production_assessment_smoke_validation(artifact)
    assert passed is True
    assert note

    hosted = build_hosted_smoke_test({"evidence": complete_hosted_evidence(artifact)})
    tier_case = next(item for item in hosted["cases"] if item["id"] == "production_assessment_tiers")
    assert tier_case["passed"] is True


def test_changed_exact_run_identity_fails_closed() -> None:
    with pytest.raises(SmokeFailure, match="changed the exact run identity") as error:
        build_smoke_artifact(
            config(),
            FakeTransport(changed_full_run=True),
            deployment(),
            browser(),
            sleep=lambda _seconds: None,
        )
    assert error.value.code == "run_identity_changed"


def test_conflicting_client_delivery_boundary_fails_closed() -> None:
    with pytest.raises(SmokeFailure) as error:
        build_smoke_artifact(
            config(),
            FakeTransport(conflicting_express_boundary=True),
            deployment(),
            browser(),
            sleep=lambda _seconds: None,
        )
    assert error.value.code == "express_not_stable"


def test_configuration_rejects_unallowlisted_hosts_before_execution() -> None:
    environment = {
        "NICO_PRODUCTION_SMOKE_ALLOWLIST": "bonemantgrm/nico",
        "NICO_PRODUCTION_SMOKE_FRONTEND_HOSTS": "app.nicoaudit.com",
        "NICO_PRODUCTION_SMOKE_BACKEND_HOSTS": "nico-production-690a.up.railway.app",
        "NICO_PRODUCTION_SMOKE_ADMIN_TOKEN": "configured-secret",
        "GITHUB_TOKEN": "configured-github-token",
    }
    with pytest.raises(SmokeFailure) as error:
        validate_config(config(backend_url="https://attacker.example"), environment)
    assert error.value.code == "host_not_allowlisted"


