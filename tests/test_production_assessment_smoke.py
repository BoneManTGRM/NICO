from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production_assessment_smoke.py"
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-smoke.yml"
SPEC = importlib.util.spec_from_file_location("production_assessment_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def config(tmp_path: Path) -> dict:
    return {
        "frontend_origin": "https://app.nicoaudit.com", "backend_origin": "https://nico-production-690a.up.railway.app",
        "repository": "BoneManTGRM/NICO", "allowlisted_repository": "BoneManTGRM/NICO",
        "allowed_hosts": frozenset({"app.nicoaudit.com", "nico-production-690a.up.railway.app"}),
        "customer_id": "production_smoke_customer", "project_id": "production_smoke_project",
        "authorization_reference": "owner-approved-demo-2026-07-13", "confirmation": smoke.CONFIRMATION,
        "commit_sha": "a" * 40, "github_repository": "BoneManTGRM/NICO", "frontend_status_context": "Vercel",
        "backend_status_context": "successful-cat - NICO", "admin_token": "top-secret-admin-token", "github_token": "github-token",
        "output_json": tmp_path / "artifact.json", "output_markdown": tmp_path / "artifact.md",
        "max_polls": 3, "poll_interval": 0, "request_timeout": 60.0, "express_timeout": 900.0,
    }


def test_configuration_requires_exact_authorization_and_allowlisted_hosts(tmp_path: Path) -> None:
    base = config(tmp_path)
    smoke.validate(base)
    with pytest.raises(ValueError, match="confirmation"):
        smoke.validate({**base, "confirmation": "yes"})
    with pytest.raises(ValueError, match="authorized demonstration repository"):
        smoke.validate({**base, "repository": "Other/Repo"})
    with pytest.raises(ValueError, match="allowlisted"):
        smoke.validate({**base, "backend_origin": "https://example.com"})


def test_configuration_bounds_general_and_express_timeouts(tmp_path: Path) -> None:
    base = config(tmp_path)
    with pytest.raises(ValueError, match="General request timeout"):
        smoke.validate({**base, "request_timeout": 121.0})
    with pytest.raises(ValueError, match="Express start timeout"):
        smoke.validate({**base, "express_timeout": 60.0})
    with pytest.raises(ValueError, match="Express start timeout"):
        smoke.validate({**base, "express_timeout": 1201.0})


@pytest.mark.parametrize("value", ["http://app.nicoaudit.com", "https://user:password@app.nicoaudit.com", "https://app.nicoaudit.com/assessment", "https://app.nicoaudit.com?token=secret"])
def test_production_origins_reject_insecure_or_authenticated_urls(value: str) -> None:
    with pytest.raises(ValueError):
        smoke.origin(value, "production URL")


def test_express_start_uses_long_bounded_timeout(tmp_path: Path) -> None:
    observed: list[float] = []
    response = (
        200,
        {
            "status": "complete",
            "assessment_id": "express_1",
            "reports": {"report_id": "report_1"},
            "human_review_required": True,
            "client_ready": False,
        },
    )

    def transport(method, url, payload, headers, timeout):
        observed.append(timeout)
        assert method == "POST"
        assert url.endswith("/assessment/github")
        return response

    result = smoke.run_tier("express", config(tmp_path), transport=transport, sleep=lambda _: None)
    assert result["status"] == "passed"
    assert result["start_timeout_seconds"] == 900.0
    assert observed == [900.0]


def test_mid_posts_one_start_and_continues_only_exact_run(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    timeouts: list[float] = []
    responses = iter([
        (200, {"status": "running", "run_id": "midrun_exact_1", "human_review_required": True, "client_ready": False}),
        (200, {"status": "complete", "run_id": "midrun_exact_1", "report_generation_status": "complete", "mid_report": {"report_id": "report_exact_1"}, "approval_request": {"approval_id": "review_exact_1", "status": "pending"}, "human_review_required": True, "client_ready": False}),
    ])

    def transport(method, url, payload, headers, timeout):
        calls.append((method, url))
        timeouts.append(timeout)
        assert headers["X-NICO-Admin-Token"] == "top-secret-admin-token"
        return next(responses)

    result = smoke.run_tier("mid", config(tmp_path), transport=transport, sleep=lambda _: None)
    assert result["status"] == "passed"
    assert result["start_count"] == 1
    assert result["start_timeout_seconds"] == 60.0
    assert result["continuation_run_ids"] == ["midrun_exact_1"]
    assert result["report_id"] == "report_exact_1"
    assert result["review_request_id"] == "review_exact_1"
    assert calls == [
        ("POST", "https://nico-production-690a.up.railway.app/assessment/mid-run"),
        ("POST", "https://nico-production-690a.up.railway.app/assessment/mid-run/midrun_exact_1/status"),
    ]
    assert timeouts == [60.0, 60.0]


def test_changed_continuation_identity_fails_closed(tmp_path: Path) -> None:
    responses = iter([
        (200, {"status": "running", "run_id": "fullrun_exact_1", "human_review_required": True, "client_ready": False}),
        (200, {"status": "complete", "run_id": "fullrun_changed", "reports": {"report_id": "report_1"}, "approval": {"approval_id": "review_1"}, "human_review_required": True, "client_ready": False}),
    ])
    result = smoke.run_tier("full", config(tmp_path), transport=lambda *_: next(responses), sleep=lambda _: None)
    assert result["status"] == "failed"
    assert result["polled_single_exact_status_url"] is False


def test_completed_payload_with_blocked_progress_fails_closed(tmp_path: Path) -> None:
    response = (
        200,
        {
            "status": "complete",
            "assessment_id": "express_1",
            "reports": {"report_id": "report_1"},
            "human_review_required": True,
            "client_ready": False,
            "progress": [
                {
                    "step": "scanner_worker",
                    "status": "unavailable",
                    "message": "Scanner evidence unavailable.",
                }
            ],
        },
    )
    result = smoke.run_tier("express", config(tmp_path), transport=lambda *_: response, sleep=lambda _: None)
    assert result["status"] == "failed"
    assert result["unavailable_or_failed_evidence"] == ["Scanner evidence unavailable."]


def test_artifact_never_serializes_credentials(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    tiers = [{"tier": tier, "status": "passed", "start_count": 1, "run_id": f"{tier}_run", "polled_single_exact_status_url": True, "human_review_required": True, "client_ready": False} for tier in ("express", "mid", "full")]
    result = smoke.artifact(cfg, {"verified": True}, {"verified": True}, tiers)
    encoded = json.dumps(result)
    assert result["status"] == "passed"
    assert cfg["admin_token"] not in encoded and cfg["github_token"] not in encoded
    assert all(result["proof"].values())
    assert "does not approve, deliver, repair" in " ".join(result["limitations"])


def test_workflow_is_manual_secret_bound_and_retains_artifact() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source and "pull_request:" not in source and "push:" not in source
    assert "environment: production-smoke" in source
    assert "timeout-minutes: 60" in source
    assert "secrets.NICO_PRODUCTION_SMOKE_ADMIN_TOKEN" in source
    assert "vars.NICO_PRODUCTION_FRONTEND_URL" in source and "vars.NICO_PRODUCTION_BACKEND_URL" in source
    assert "vars.NICO_PRODUCTION_SMOKE_REPOSITORY" in source and "I_CONFIRM_AUTHORIZED_PRODUCTION_SMOKE" in source
    assert '--customer-id "production_smoke_${GITHUB_RUN_ID}"' in source
    assert '--project-id "production_smoke_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}"' in source
    assert '--request-timeout-seconds "60"' in source
    assert '--express-timeout-seconds "900"' in source
    assert "actions/upload-artifact@v7" in source and "retention-days: 90" in source
    assert "admin_token" not in source.split("inputs:", 1)[1].split("permissions:", 1)[0].lower()
