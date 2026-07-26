from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"
SCRIPT = ROOT / "scripts" / "production_frontend_release_identity.py"


def test_unified_acceptance_requires_exact_custom_domain_release_before_browser_run() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    release_gate = "Verify exact production frontend release and copy contract"
    browser_run = "Run two consecutive unified strategic assessment passes"
    assert release_gate in workflow
    assert workflow.index(release_gate) < workflow.index(browser_run)
    assert "scripts/production_frontend_release_identity.py" in workflow
    assert '--expected-ui-contract "expert-engagement-v2"' in workflow
    assert '--expected-deployment-environment "production"' in workflow
    assert "audit-results/frontend-production-release-identity.json" in workflow
    assert 'release_payload["status"] == "passed"' in workflow
    assert 'release_payload["final_release_observation"]["release_sha"] == release_payload["expected_sha"]' in workflow
    assert "A successful provider deployment status is insufficient" in script
    assert 'data-workspace="assessment"' in script
    assert 'data-engagement-type="comprehensive"' in script
    assert 'data-canonical-assessment="strategic"' in script
    assert 'data-assessment-copy-contract="expert-engagement-v2"' in script
    assert "Create engagement and capture repository snapshot" in script
    assert "Crear encargo y capturar instantánea del repositorio" in script
