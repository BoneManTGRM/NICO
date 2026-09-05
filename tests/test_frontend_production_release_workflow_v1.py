from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "frontend-production-release-proof.yml"


def test_frontend_release_workflow_verifies_exact_custom_domain_commit() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Frontend Production Release Proof" in source
    assert "Verify custom domain serves exact main release" in source
    assert "NICO_PRODUCTION_FRONTEND_URL" in source
    assert "python scripts/production_frontend_release_identity.py" in source
    assert '--expected-sha "${RELEASE_SHA}"' in source
    assert '--expected-ui-contract "expert-engagement-v2"' in source
    assert '--expected-deployment-environment "production"' in source
    assert 'data-assessment-copy-contract="expert-engagement-v2"' in source
    assert "Run NICO Assessment" in source
    assert "Wait for exact Vercel deployment status" in source
    assert "Upload immutable frontend release evidence" in source
    assert 'page_url = origin + "/assessment?"' not in source


@pytest.mark.parametrize("field,value", [
    ("http_status", 503),
    ("release_sha", "b" * 40),
    ("ui_contract", "obsolete"),
    ("deployment_environment", "preview"),
])
def test_canonical_verifier_rejects_wrong_release_identity(field, value) -> None:
    from scripts.production_frontend_release_identity import _release_matches

    expected = {"expected_sha": "a" * 40, "expected_ui_contract": "expert-engagement-v2",
                "expected_deployment_environment": "production"}
    observed = {"http_status": 200, "release_sha": "a" * 40,
                "ui_contract": "expert-engagement-v2", "deployment_environment": "production"}
    assert _release_matches(observed, **expected)
    observed[field] = value
    assert not _release_matches(observed, **expected)
