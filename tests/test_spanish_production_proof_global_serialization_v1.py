from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/spanish-comprehensive-production-proof.yml")


def test_spanish_production_proofs_serialize_without_cancelling_active_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "group: nico-spanish-comprehensive-production\n" in source
    assert "group: nico-spanish-comprehensive-production-${{ github.sha }}" not in source
    assert "cancel-in-progress: false" in source
    assert "cancel-in-progress: true" not in source


def test_queued_release_policy_does_not_weaken_exact_release_or_delivery_gates() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'RELEASE_SHA: ${{ github.sha }}' in source
    assert "Verify exact frontend release identity" in source
    assert "Wait for exact frontend and backend deployments" in source
    assert "scripts/spanish_comprehensive_live_acceptance_v2.py" in source
    assert "spanish-comprehensive-live-proof.progress.json" in source
    assert 'payload["production_proof_scope_verified"] is True' in source
    assert 'payload["spanish_pdf_presentation_verified"] is True' in source
    assert 'payload["human_review_required"] is True' in source
    assert 'payload["client_delivery_allowed"] is False' in source
