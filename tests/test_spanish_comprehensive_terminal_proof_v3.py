from __future__ import annotations

import os
import subprocess
import sys
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


def test_v3_entrypoint_imports_nico_when_invoked_by_path(tmp_path: Path) -> None:
    playwright = tmp_path / "stubs" / "playwright"
    playwright.mkdir(parents=True)
    (playwright / "__init__.py").write_text("", encoding="utf-8")
    (playwright / "sync_api.py").write_text(
        "class Browser: pass\n"
        "class Page: pass\n"
        "def sync_playwright(): raise AssertionError('preflight must not start a browser')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "stubs")
    script = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    import_only = (
        "import runpy, sys; "
        f"sys.path.insert(0, {str(script.parent)!r}); "
        f"runpy.run_path({str(script)!r}, run_name='nico_spanish_proof_import_preflight')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", import_only],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_production_workflow_preflights_entrypoint_before_assessment() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "spanish-comprehensive-production-proof.yml"
    ).read_text(encoding="utf-8")

    preflight = workflow.index("Verify Spanish proof entrypoint before assessment")
    assessment = workflow.index("Run fresh Spanish Comprehensive final-report proof")
    assert preflight < assessment
    assert 'run_name="nico_spanish_proof_import_preflight"' in workflow
