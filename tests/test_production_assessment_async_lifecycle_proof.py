from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "production_assessment_browser_smoke_v2.py"
BASE = ROOT / "scripts" / "production_assessment_browser_smoke.py"
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-smoke.yml"
DOCS = ROOT / "docs" / "PRODUCTION_ASSESSMENT_SMOKE.md"


def test_lifecycle_wrapper_covers_express_mid_and_full_exact_status_paths() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert '"express": "/assessment/express-run"' in source
    assert '"mid": "/assessment/mid-run"' in source
    assert '"full": "/assessment/full-run"' in source
    assert 'STATUS_PATH_RE = re.compile(r"^/assessment/(express|mid|full)-run/([^/]+)/status$")' in source
    assert 'PROXY_PREFIX = "/api/nico"' in source
    assert 'logical_path' in source
    assert 'run_id.startswith("express_run_")' in source
    assert 'final_run_id == run_id' in source
    assert 'all(path == expected_path for path in status_paths)' in source
    assert 'all(value == run_id for value in continuation_ids)' in source


def test_lifecycle_wrapper_requires_same_origin_and_no_long_express_connection() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert 'network_origin_contract' in source
    assert 'same_origin_frontend_proxy' in source
    assert 'same_origin_lifecycle_transport' in source
    assert 'no_long_express_browser_connection' in source
    assert 'len(tiers) == 3' in source
    assert 'all(item.get("status") == "passed" for item in tiers)' in source
    assert 'base.main()' in source


def test_protected_workflow_uses_lifecycle_wrapper_for_preflight_and_browser_run() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count("python scripts/production_assessment_browser_smoke_v2.py") == 2
    assert "python scripts/production_assessment_browser_smoke.py" not in source
    assert 'assert browser["lifecycle_version"] == "express_async_v1"' in source
    assert 'assert browser["proof"]["exact_run_continuation"] is True' in source
    assert 'assert browser["proof"]["same_origin_lifecycle_transport"] is True' in source
    assert 'assert browser["proof"]["no_long_express_browser_connection"] is True' in source
    assert 'all(item["polled_single_exact_status_url"] is True for item in browser["tiers"])' in source
    assert "workflow_dispatch:" in source
    assert "environment: production-smoke" in source


def test_original_proof_engine_remains_present_and_wrapper_is_bounded_compatibility() -> None:
    base = BASE.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert "def build_tier_evidence(" in base
    assert "def run_browser_proof(" in base
    assert "def combined_artifact(" in base
    assert "import production_assessment_browser_smoke as base" in wrapper
    assert "base.build_tier_evidence = build_tier_evidence" in wrapper
    assert "base.run_browser_proof = run_browser_proof" in wrapper


def test_docs_describe_one_quick_start_and_same_run_polling_without_overclaim() -> None:
    source = DOCS.read_text(encoding="utf-8")

    assert "no longer depends on one several-minute mobile browser-to-Railway connection" in source
    assert "one quick same-origin `/assessment/express-run` start" in source
    assert "exact `express_run_*` identity" in source
    assert "polls only `/assessment/express-run/<same-run-id>/status`" in source
    assert "The original synchronous `/assessment/github` endpoint remains available for compatibility" in source
    assert "Human review of the retained package remains required" in source
    assert "interrupted-worker" in source
