from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "production_assessment_browser_smoke.py"
SPEC = importlib.util.spec_from_file_location("production_assessment_browser_smoke", SCRIPT)
assert SPEC and SPEC.loader
browser_smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = browser_smoke
SPEC.loader.exec_module(browser_smoke)
smoke = sys.modules["production_assessment_smoke"]


def config(tmp_path: Path) -> dict:
    return {
        "frontend_origin": "https://app.nicoaudit.com",
        "backend_origin": "https://nico-production-690a.up.railway.app",
        "repository": "BoneManTGRM/NICO",
        "allowlisted_repository": "BoneManTGRM/NICO",
        "allowed_hosts": frozenset({"app.nicoaudit.com", "nico-production-690a.up.railway.app"}),
        "customer_id": "production_smoke_customer",
        "project_id": "production_smoke_project",
        "authorization_reference": "owner-approved-demo-2026-07-14",
        "confirmation": smoke.CONFIRMATION,
        "commit_sha": "a" * 40,
        "github_repository": "BoneManTGRM/NICO",
        "frontend_status_context": "Vercel",
        "backend_status_context": "successful-cat - NICO",
        "admin_token": "top-secret-admin-token",
        "github_token": "github-token",
        "output_json": tmp_path / "artifact.json",
        "output_markdown": tmp_path / "artifact.md",
        "browser_evidence_json": tmp_path / "browser.json",
        "preflight_output": tmp_path / "preflight.json",
        "screenshot_dir": tmp_path / "screenshots",
        "max_polls": 3,
        "poll_interval": 0,
        "request_timeout": 60.0,
        "express_timeout": 900.0,
    }


def response(tier: str, path: str, payload: dict) -> dict:
    return {
        "origin": "https://nico-production-690a.up.railway.app",
        **browser_smoke.response_summary(tier, path, 200, payload),
    }


def test_express_browser_evidence_requires_one_network_start_and_matching_ui_identity(tmp_path: Path) -> None:
    screenshot = tmp_path / "express.png"
    screenshot.write_bytes(b"synthetic screenshot bytes")
    payload = {
        "status": "complete",
        "run_id": "express_run_exact",
        "report_id": "express_report_exact",
        "customer_id": "customer_production_smoke_customer",
        "project_id": "project_production_smoke_project",
        "human_review_required": True,
        "client_ready": False,
    }

    result = browser_smoke.build_tier_evidence(
        "express",
        "https://nico-production-690a.up.railway.app",
        [{"method": "POST", "origin": "https://nico-production-690a.up.railway.app", "path": "/assessment/github"}],
        [response("express", "/assessment/github", payload)],
        {
            "phase_label": "Complete",
            "message": "Express completed.",
            "run_id": "express_run_exact",
            "page_url": "https://app.nicoaudit.com/assessment?tier=express#assessment",
        },
        screenshot,
        "2026-07-14T17:00:00Z",
        "2026-07-14T17:01:00Z",
    )

    assert result["status"] == "passed"
    assert result["start_count"] == 1
    assert result["run_id"] == "express_run_exact"
    assert result["report_id"] == "express_report_exact"
    assert result["browser_verified"] is True
    assert result["screenshot_sha256"]


def test_mid_changed_continuation_identity_fails_closed(tmp_path: Path) -> None:
    screenshot = tmp_path / "mid.png"
    screenshot.write_bytes(b"synthetic screenshot bytes")
    start = {
        "status": "running",
        "run_id": "mid_run_exact",
        "customer_id": "customer_production_smoke_customer",
        "project_id": "project_production_smoke_project",
        "human_review_required": True,
        "client_ready": False,
    }
    final = {
        "status": "complete",
        "run_id": "mid_run_changed",
        "report_generation_status": "complete",
        "mid_report": {"report_id": "mid_report_exact"},
        "approval_request": {"approval_id": "mid_review_exact", "status": "pending"},
        "customer_id": "customer_production_smoke_customer",
        "project_id": "project_production_smoke_project",
        "human_review_required": True,
        "client_ready": False,
    }
    status_path = "/assessment/mid-run/mid_run_exact/status"

    result = browser_smoke.build_tier_evidence(
        "mid",
        "https://nico-production-690a.up.railway.app",
        [
            {"method": "POST", "origin": "https://nico-production-690a.up.railway.app", "path": "/assessment/mid-run"},
            {"method": "POST", "origin": "https://nico-production-690a.up.railway.app", "path": status_path},
        ],
        [
            response("mid", "/assessment/mid-run", start),
            response("mid", status_path, final),
        ],
        {
            "phase_label": "Human review required",
            "message": "Mid completed.",
            "run_id": "mid_run_changed",
            "page_url": "https://app.nicoaudit.com/assessment?tier=mid#assessment",
        },
        screenshot,
        "2026-07-14T17:00:00Z",
        "2026-07-14T17:02:00Z",
    )

    assert result["status"] == "failed"
    assert result["polled_single_exact_status_url"] is False


def test_unexpected_assessment_origin_fails_closed(tmp_path: Path) -> None:
    screenshot = tmp_path / "express.png"
    screenshot.write_bytes(b"synthetic screenshot bytes")
    payload = {
        "status": "complete",
        "run_id": "express_run_exact",
        "report_id": "express_report_exact",
        "human_review_required": True,
        "client_ready": False,
    }

    result = browser_smoke.build_tier_evidence(
        "express",
        "https://nico-production-690a.up.railway.app",
        [{"method": "POST", "origin": "https://unexpected.example", "path": "/assessment/github"}],
        [response("express", "/assessment/github", payload)],
        {"phase_label": "Complete", "run_id": "express_run_exact", "page_url": "https://app.nicoaudit.com/assessment"},
        screenshot,
        "2026-07-14T17:00:00Z",
        "2026-07-14T17:01:00Z",
    )

    assert result["status"] == "failed"
    assert result["unexpected_assessment_origins"] == ["https://unexpected.example"]


def test_combined_artifact_requires_browser_screenshots_identity_and_same_start(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    tiers = []
    for tier in ("express", "mid", "full"):
        tiers.append(
            {
                "tier": tier,
                "status": "passed",
                "evidence_source": "deployed_browser_network",
                "start_count": 1,
                "run_id": f"{tier}_run",
                "report_id": f"{tier}_report",
                "review_request_id": "" if tier == "express" else f"{tier}_review",
                "polled_single_exact_status_url": True,
                "human_review_required": True,
                "client_ready": False,
                "browser_verified": True,
                "screenshot_path": f"audit-results/{tier}.png",
                "screenshot_sha256": f"{tier}hash",
            }
        )
    browser = {
        "status": "passed",
        "generated_at": "2026-07-14T17:00:00Z",
        "playwright_version": browser_smoke.PLAYWRIGHT_VERSION,
        "frontend_origin": cfg["frontend_origin"],
        "backend_origin": cfg["backend_origin"],
        "tenant": {
            "customer_id": "customer_production_smoke_customer",
            "project_id": "project_production_smoke_project",
        },
        "proof": {
            "one_start_per_tier": True,
            "exact_run_continuation": True,
            "matching_browser_network_identity": True,
            "screenshots_retained": True,
            "same_isolated_tenant": True,
            "no_unexpected_assessment_origins": True,
        },
        "tiers": tiers,
    }

    result = browser_smoke.combined_artifact(cfg, {"verified": True}, {"verified": True}, browser)
    encoded = json.dumps(result)

    assert result["status"] == "passed"
    assert result["evidence_kind"] == "authorized_live_production_browser_api_smoke"
    assert result["proof"]["matching_browser_evidence"] is True
    assert result["proof"]["browser_generated_the_only_api_starts"] is True
    assert result["tenant"]["customer_id"].startswith("customer_production_smoke_")
    assert cfg["admin_token"] not in encoded
    assert cfg["github_token"] not in encoded


def test_browser_module_does_not_import_playwright_until_execution() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    prefix = source.split("def run_browser_proof", 1)[0]

    assert "from playwright" not in prefix
    assert 'PLAYWRIGHT_VERSION = "1.61.0"' in source
