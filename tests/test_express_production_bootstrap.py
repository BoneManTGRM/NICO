from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
BOOTSTRAP = ROOT / "nico" / "api" / "production_bootstrap.py"


def test_container_uses_explicit_express_production_bootstrap() -> None:
    docker = DOCKERFILE.read_text(encoding="utf-8")

    assert "uvicorn nico.api.production_bootstrap:app" in docker
    assert "uvicorn nico.api.production:app" not in docker


def test_bootstrap_installs_repairs_after_complete_production_app_loads() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    production_import = "from nico.api.production import app as production_app"
    redaction_install = "SCANNER_REDACTION_SAFETY = install_scanner_redaction_safety()"
    diagnostics_install = "EXPRESS_PRODUCTION_BOOTSTRAP = install_assessment_block_messages()"

    assert production_import in source
    assert redaction_install in source
    assert diagnostics_install in source
    assert source.index(production_import) < source.index(redaction_install)
    assert source.index(redaction_install) < source.index(diagnostics_install)
    assert 'raise RuntimeError("Express production bootstrap did not install cycle-safe scanner redaction")' in source
    assert 'raise RuntimeError("Express production bootstrap did not install bounded backend diagnostics")' in source
    assert '"/assessment/express-run"' in source
    assert '"/assessment/express-run/{run_id}/status"' in source
    assert 'EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/express-runtime"' in source


def test_fresh_production_process_has_safe_redactor_diagnostic_worker_and_single_routes() -> None:
    script = """
import nico.api.production_bootstrap as bootstrap
import nico.express_async_api as express
import nico.scanner_tool_runners as tool_runners

runtime = bootstrap.EXPRESS_PRODUCTION_RUNTIME
redaction = bootstrap.SCANNER_REDACTION_SAFETY
assert runtime["status"] == "ok", runtime
assert runtime["bounded_backend_diagnostics_installed"] is True, runtime
assert runtime["cycle_safe_scanner_redaction_installed"] is True, runtime
assert runtime["worker_name"] == "execute_with_diagnostics", runtime
assert all(count == 1 for count in runtime["route_counts"].values()), runtime
assert getattr(express._execute, "_nico_express_backend_diagnostics_v1", False) is True
assert getattr(tool_runners.redact_payload, "_nico_scanner_redaction_safety_v1", False) is True
assert bootstrap._route_count(bootstrap.app, "GET", bootstrap.EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE) == 1
assert redaction["cycle_safe_redaction_installed"] is True
assert bootstrap.app.state.nico_scanner_redaction_safety["cycle_safe_redaction_installed"] is True
assert runtime["replacement_run_allowed"] is False
assert runtime["automatic_retry_allowed"] is False
assert runtime["human_review_required"] is True
assert runtime["client_ready"] is False
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, f"stdout={completed.stdout}\nstderr={completed.stderr}"
