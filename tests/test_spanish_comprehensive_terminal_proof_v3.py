from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v3_proof_binds_distinct_spanish_terminal_fields() -> None:
    source = (
        ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    ).read_text(encoding="utf-8")

    assert 'SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"' in source
    assert 'SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"' in source
    assert 'SPANISH_TERMINAL_REPORT = "Completa"' in source
    assert 'terminal.get("phase") == SPANISH_TERMINAL_PHASE' in source
    assert 'terminal.get("review") == SPANISH_TERMINAL_REVIEW' in source
    assert 'terminal.get("report") == SPANISH_TERMINAL_REPORT' in source
    assert "return telemetry.main(argv)" in source


def test_production_workflow_uses_v3_and_exact_terminal_assertions() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "spanish-comprehensive-production-proof.yml"
    ).read_text(encoding="utf-8")

    assert "python scripts/spanish_comprehensive_live_acceptance_v3.py" in workflow
    assert 'payload["terminal"]["phase"] == "Se requiere revisión experta"' in workflow
    assert 'payload["terminal"]["review"] == "Revisión interna requerida"' in workflow
    assert 'payload["terminal"]["report"] == "Completa"' in workflow
