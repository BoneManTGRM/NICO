from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"


def test_unified_production_acceptance_does_not_fabricate_client_context() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'page.get_by_label("Client name, optional").fill("")' in source
    assert 'page.get_by_label("Project name, optional").fill("")' in source
    assert "Production Acceptance Pass" not in source
    assert "NICO {service.title()} Acceptance" not in source
    assert "access method" in source.lower()
    assert "authorized scope" in source.lower()
