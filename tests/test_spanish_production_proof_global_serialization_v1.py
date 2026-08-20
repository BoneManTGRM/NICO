from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/spanish-comprehensive-production-proof.yml")


def test_spanish_production_proof_is_serialized_across_release_shas() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "group: nico-spanish-comprehensive-production\n" in source
    assert "group: nico-spanish-comprehensive-production-${{ github.sha }}" not in source
    assert "cancel-in-progress: false" in source


def test_serialization_does_not_weaken_exact_release_or_delivery_gates() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'RELEASE_SHA: ${{ github.sha }}' in source
    assert "Verify exact frontend release identity" in source
    assert "Wait for exact frontend and backend deployments" in source
    assert "scripts/spanish_comprehensive_live_acceptance_v1.py" in source
    assert 'payload["spanish_pdf_presentation_verified"] is True' in source
    assert 'payload["human_review_required"] is True' in source
    assert 'payload["client_delivery_allowed"] is False' in source
