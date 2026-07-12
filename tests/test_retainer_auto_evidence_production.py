from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nico.retainer_auto_evidence_api import RETAINER_OPS_ROUTE


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def test_retainer_route_is_required_by_production_contract() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "RETAINER_OPS_ROUTE" in source
    assert "install_retainer_auto_evidence" in source
    assert "RETAINER_AUTO_EVIDENCE = install_retainer_auto_evidence(app)" in source
    assert "{STORAGE_SCHEMA_READINESS_ROUTE, RETAINER_OPS_ROUTE}" in source
    assert "install_retainer_auto_evidence(target)" in source
    assert "exactly one truth-bound POST /retainer/ops handler" in source
    assert RETAINER_OPS_ROUTE == ("POST", "/retainer/ops")


def test_production_openapi_exposes_one_auto_evidence_retainer_route() -> None:
    script = r'''
import json
from nico.api.production import app
schema = app.openapi()
paths = schema.get("paths") or {}
route_count = sum(
    1
    for route in app.routes
    if str(getattr(route, "path", "")) == "/retainer/ops"
    and "POST" in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
)
request_schema = schema["components"]["schemas"]["RetainerAutoOpsRequest"]
print(json.dumps({
    "route_count": route_count,
    "path_present": "/retainer/ops" in paths,
    "properties": sorted((request_schema.get("properties") or {}).keys()),
    "version": getattr(app.state, "retainer_auto_evidence_version", ""),
}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["route_count"] == 1
    assert result["path_present"] is True
    assert result["version"] == "nico.retainer_auto_evidence_api.v2"
    for field in (
        "repository",
        "baseline_run_id",
        "timeframe_days",
        "roadmap_notes",
        "client_update",
        "retainer_metrics",
        "budget_priorities",
    ):
        assert field in result["properties"]
