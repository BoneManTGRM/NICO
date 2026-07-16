from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
BOOTSTRAP = ROOT / "nico" / "api" / "production_bootstrap.py"


def test_container_defaults_in_process_assessment_execution_to_one_worker() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ENV NICO_WEB_WORKERS=1" in source
    assert 'workers=${NICO_WEB_WORKERS:-1}' in source
    assert 'if [ -n "${DATABASE_URL:-}" ]; then workers=2' not in source
    assert "NICO_WEB_WORKERS must be a positive integer" in source
    assert "NICO_WEB_WORKERS must be at least 1" in source
    assert "uvicorn nico.api.production_bootstrap:app" in source


def test_runtime_diagnostics_disclose_worker_and_durability_truth() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert '"configured_web_workers": workers' in source
    assert '"single_worker_default": workers == 1' in source
    assert '"atomic_heartbeat_status_guard_installed": atomic_heartbeat_installed' in source
    assert '"heartbeat_can_reopen_terminal_state": False' in source
    assert '"status_read_can_write_terminal_interruption": False' in source
    assert '"scanner_liveness_corroboration": True' in source
    assert '"durability_verified": durability_verified' in source
    assert '"survives_container_replacement_verified": durability_verified' in source
    assert 'EXPRESS_STATUS_LIVENESS = install_express_status_liveness_patch()' in source
