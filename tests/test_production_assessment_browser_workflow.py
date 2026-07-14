from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-smoke.yml"
BROWSER_SCRIPT = ROOT / "scripts" / "production_assessment_browser_smoke.py"


def test_production_smoke_remains_manual_exact_commit_and_environment_guarded() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "push:" not in source
    assert "environment: production-smoke" in source
    assert 'test "${EXPECTED_COMMIT_SHA}" = "${GITHUB_SHA}"' in source
    assert 'test "${CONFIRMATION}" = "I_CONFIRM_AUTHORIZED_PRODUCTION_SMOKE"' in source
    assert "secrets.NICO_PRODUCTION_SMOKE_ADMIN_TOKEN" in source
    assert "admin_token" not in source.split("inputs:", 1)[1].split("permissions:", 1)[0].lower()


def test_deployment_preflight_finishes_before_any_browser_or_assessment_start() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    preflight = source.index("Verify deployment and health before browser starts")
    install = source.index("Install pinned Playwright Chromium")
    run = source.index("Run exactly one deployed browser start per tier")
    assert preflight < install < run
    assert "--preflight-only" in source


def test_workflow_uses_pinned_playwright_and_browser_generated_api_starts_only() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'playwright==1.61.0' in source
    assert "python -m playwright install --with-deps chromium" in source
    assert source.count("python scripts/production_assessment_browser_smoke.py") == 2
    assert "python scripts/production_assessment_smoke.py" not in source
    assert "browser_generated_the_only_api_starts" in source
    assert "authorized_live_production_browser_api_smoke" in source


def test_workflow_retains_preflight_browser_network_and_screenshot_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    for required in (
        "production-assessment-preflight.json",
        "production-assessment-browser-evidence.json",
        "production-assessment-smoke.json",
        "production-assessment-smoke.md",
        "production-assessment-browser/",
        "retention-days: 90",
    ):
        assert required in source


def test_browser_runner_clicks_each_tier_once_without_api_retry_loop() -> None:
    source = BROWSER_SCRIPT.read_text(encoding="utf-8")

    assert 'for tier in ("express", "mid", "full")' in source
    assert 'get_by_role("button", name=f"Run {label} assessment", exact=True).click()' in source
    assert "run_browser_tier(browser, tier" in source
    assert "smoke.run_tier(" not in source
    assert "request_json(" not in source
