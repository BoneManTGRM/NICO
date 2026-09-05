from pathlib import Path


WORKFLOW = Path(".github/workflows/frontend-production-release-proof.yml")


def test_frontend_release_proof_uses_specialist_aware_verifier() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "Verify exact release and bilingual specialist access boundary" in source
    assert "python scripts/production_frontend_release_identity.py" in source
    assert '--expected-ui-contract "expert-engagement-v2"' in source
    assert '--expected-deployment-environment "production"' in source
    assert "frontend-production-release-proof.json" in source


def test_frontend_release_proof_does_not_require_public_workspace_html() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'page_url = origin + "/assessment?"' not in source
    assert 'required = (' not in source
    assert '"Decision-grade technical diligence"' not in source
    assert '"specialist_authentication_gate"' in source
    assert '"Acceso para especialistas en ciberseguridad"' in source
