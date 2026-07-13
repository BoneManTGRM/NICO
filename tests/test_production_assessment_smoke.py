from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from scripts.production_assessment_smoke import (
    SmokeConfig,
    SmokeFailure,
    normalize_base_url,
    parse_tiers,
    run_smoke,
    run_tier,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-smoke.yml"


def _config() -> SmokeConfig:
    return SmokeConfig(
        api_url="https://api.example.invalid",
        repository="BoneManTGRM/NICO",
        customer_id="smoke_customer",
        project_id="smoke_project",
        authorized_by="test_reviewer",
        authorization_scope="authorized synthetic smoke contract",
        request_timeout_seconds=3,
        poll_interval_seconds=0,
        max_polls=4,
    )


def test_each_tier_starts_once_and_mid_full_only_poll_the_exact_returned_run() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    poll_counts: Counter[str] = Counter()

    def requester(method: str, url: str, payload: dict[str, Any] | None, _timeout: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        if url.endswith("/assessment/github"):
            return {
                "status": "complete",
                "assessment_id": "express-assessment-1",
                "assessment_mode": "express",
                "human_review_required": True,
                "client_ready": False,
            }
        if url.endswith("/assessment/mid-run"):
            return {
                "status": "queued",
                "run_id": "midrun_exact_1",
                "mode": "mid",
                "human_review_required": True,
                "client_ready": False,
            }
        if url.endswith("/assessment/full-run"):
            return {
                "status": "queued",
                "run_id": "fullrun_exact_1",
                "mode": "full",
                "human_review_required": True,
                "client_ready": False,
            }
        if "/assessment/mid-run/midrun_exact_1/status" in url:
            poll_counts["mid"] += 1
            return {
                "status": "running" if poll_counts["mid"] == 1 else "complete",
                "run_id": "midrun_exact_1",
                "assessment_type": "mid",
                "human_review_required": True,
                "client_ready": False,
            }
        if "/assessment/full-run/fullrun_exact_1/status" in url:
            poll_counts["full"] += 1
            return {
                "status": "running" if poll_counts["full"] == 1 else "pending_review",
                "run_id": "fullrun_exact_1",
                "report_path": "full_run",
                "human_review_required": True,
                "client_ready": False,
            }
        raise AssertionError(f"Unexpected URL: {url}")

    evidence = run_smoke(
        _config(),
        ["express", "mid", "full"],
        authorization_confirmed=True,
        requester=requester,
        sleeper=lambda _seconds: None,
    )

    endpoints = [url for _method, url, _payload in calls]
    assert endpoints.count("https://api.example.invalid/assessment/github") == 1
    assert endpoints.count("https://api.example.invalid/assessment/mid-run") == 1
    assert endpoints.count("https://api.example.invalid/assessment/full-run") == 1
    assert all("midrun_exact_1" in url for url in endpoints if "/assessment/mid-run/" in url)
    assert all("fullrun_exact_1" in url for url in endpoints if "/assessment/full-run/" in url)
    assert evidence["status"] == "passed"
    assert evidence["proof"] == {
        "one_start_per_tier": True,
        "exact_run_continuation": True,
        "human_review_boundary_preserved": True,
        "no_client_ready_claim": True,
    }
    tiers = {item["tier"]: item for item in evidence["tiers"]}
    assert tiers["express"]["start_count"] == 1
    assert tiers["mid"]["run_id"] == "midrun_exact_1"
    assert tiers["full"]["run_id"] == "fullrun_exact_1"
    assert tiers["mid"]["poll_count"] == 2
    assert tiers["full"]["poll_count"] == 2


def test_continuation_run_identity_mismatch_fails_closed() -> None:
    def requester(method: str, url: str, payload: dict[str, Any] | None, _timeout: float) -> dict[str, Any]:
        assert method == "POST"
        assert payload
        if url.endswith("/assessment/mid-run"):
            return {"status": "queued", "run_id": "midrun_original", "mode": "mid"}
        return {"status": "complete", "run_id": "midrun_replacement", "mode": "mid"}

    with pytest.raises(SmokeFailure, match="changed run identity"):
        run_tier("mid", _config(), requester=requester, sleeper=lambda _seconds: None)


def test_blocked_or_unavailable_results_never_become_passing_smoke_evidence() -> None:
    def requester(_method: str, _url: str, _payload: dict[str, Any] | None, _timeout: float) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "assessment_id": "express-unavailable",
            "message": "Required repository evidence is unavailable.",
        }

    with pytest.raises(SmokeFailure, match="Unavailable|unavailable"):
        run_tier("express", _config(), requester=requester)


def test_production_execution_requires_explicit_authorization_confirmation() -> None:
    with pytest.raises(SmokeFailure, match="Explicit authorization confirmation"):
        run_smoke(
            _config(),
            ["express"],
            authorization_confirmed=False,
            requester=lambda *_args: {},
        )


def test_tier_metadata_conflict_is_not_corrected_cosmetically() -> None:
    def requester(_method: str, _url: str, _payload: dict[str, Any] | None, _timeout: float) -> dict[str, Any]:
        return {
            "status": "complete",
            "assessment_id": "express-conflict",
            "assessment_mode": "full",
            "human_review_required": True,
            "client_ready": False,
        }

    with pytest.raises(SmokeFailure, match="conflicting tier metadata"):
        run_tier("express", _config(), requester=requester)


def test_url_and_tier_parsing_are_bounded_and_safe() -> None:
    assert normalize_base_url("https://api.example.invalid/") == "https://api.example.invalid"
    assert normalize_base_url("http://127.0.0.1:8000", allow_http=True) == "http://127.0.0.1:8000"
    with pytest.raises(SmokeFailure, match="HTTPS"):
        normalize_base_url("http://api.example.invalid")
    with pytest.raises(SmokeFailure, match="credentials"):
        normalize_base_url("https://user:password@api.example.invalid")
    assert parse_tiers("express,mid,full,mid") == ["express", "mid", "full"]
    with pytest.raises(SmokeFailure, match="Unsupported tier"):
        parse_tiers("express,enterprise")


def test_frontend_proof_is_optional_but_must_pass_when_requested() -> None:
    requested_urls: list[str] = []

    def frontend_requester(url: str, _timeout: float) -> dict[str, Any]:
        requested_urls.append(url)
        return {
            "status": "passed",
            "http_status": 200,
            "required_labels": ["Express", "Mid", "Full"],
            "response_sha256": "a" * 64,
        }

    def requester(_method: str, _url: str, _payload: dict[str, Any] | None, _timeout: float) -> dict[str, Any]:
        return {
            "status": "complete",
            "assessment_id": "express-frontend-proof",
            "assessment_mode": "express",
            "human_review_required": True,
            "client_ready": False,
        }

    result = run_smoke(
        _config(),
        ["express"],
        authorization_confirmed=True,
        frontend_url="https://app.example.invalid",
        requester=requester,
        frontend_requester=frontend_requester,
    )

    assert requested_urls == ["https://app.example.invalid/assessment"]
    assert result["frontend"]["status"] == "passed"


def test_manual_workflow_requires_authorization_and_uploads_the_evidence_artifact() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "schedule:" not in source
    assert "confirm_authorized:" in source
    assert "--confirm-authorized" in source
    assert "scripts/production_assessment_smoke.py" in source
    assert "audit-results/production-assessment-smoke.json" in source
    assert "actions/upload-artifact@v4" in source
    assert "permissions:\n  contents: read" in source
    assert "NICO_ADMIN_TOKEN" not in source
