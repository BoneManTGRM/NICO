from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/web/app/assessment/AssessmentRuntimeTruthRepair.tsx"
CSS = ROOT / "apps/web/app/assessment/assessment-runtime-truth.css"


def test_live_run_explains_long_scanner_stages_in_both_languages() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert "The scanner suite runs multiple tools and can remain on this stage for several minutes." in source
    assert "El conjunto de analizadores ejecuta varias herramientas" in source
    assert "NICO is still polling the backend automatically" in source
    assert "no reinicies la ejecución" in source


def test_status_fetch_retries_transient_provider_failures() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert "[429, 502, 503, 504]" in source
    assert 'headers.set("X-NICO-Client", "assessment-command-center-v42")' in source
    assert 'cache: "no-store"' in source


def test_command_center_adds_copy_controls_and_truthful_storage_states() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert "installCopyControl" in source
    assert "Durable · verified Postgres" in source
    assert "Durable · persistent SQLite volume" in source
    assert "Temporary record · persistent volume not verified" in source
    assert "Temporary memory record · Postgres or a persistent volume required" in source


def test_visual_system_includes_live_heartbeat_score_meters_and_sticky_actions() -> None:
    css = CSS.read_text(encoding="utf-8")
    required = {
        ".nico-trust-strip",
        ".nico-service-choice",
        ".nico-live-heartbeat",
        ".nico-section-meter",
        ".nico-report-actions",
        "@keyframes nicoHeartbeat",
        "@keyframes nicoProgressSheen",
    }
    for selector in required:
        assert selector in css
