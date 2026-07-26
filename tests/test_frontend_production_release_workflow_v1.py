from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "frontend-production-release-proof.yml"


def test_frontend_release_workflow_verifies_exact_custom_domain_commit() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Frontend Production Release Proof" in source
    assert "Verify custom domain serves exact main release" in source
    assert "NICO_PRODUCTION_FRONTEND_URL" in source
    assert 'last.get("release_sha") == expected_sha' in source
    assert 'last.get("ui_contract") == "expert-engagement-v2"' in source
    assert 'data-assessment-copy-contract="expert-engagement-v2"' in source
    assert "Run NICO Assessment" in source
    assert "production branch, project root, and app.nicoaudit.com domain assignment" in source
