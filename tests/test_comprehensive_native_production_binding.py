from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_native_providers import install_native_comprehensive_providers
from nico.comprehensive_production_capabilities import build_production_capability_executors


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "nico" / "api" / "comprehensive_production_bootstrap.py"


def test_native_provider_install_covers_every_required_capability() -> None:
    app = FastAPI()
    providers = install_native_comprehensive_providers(app)
    executors = build_production_capability_executors(app)
    required = {str(item["capability"]) for item in execution_plan()}

    assert set(executors) == required
    assert set(providers) >= required - {"authorization"}
    status = app.state.nico_comprehensive_capability_provider_status
    assert status["missing_capabilities"] == []
    assert status["fail_closed"] is True
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False


def test_production_entrypoint_installs_providers_before_building_executors() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "from nico.comprehensive_native_providers import install_native_comprehensive_providers" in source
    provider_install = source.index("native_providers = install_native_comprehensive_providers(target)")
    executor_build = source.index("executors = build_production_capability_executors(target)")
    runtime_install = source.index("controller = install_comprehensive_production_bootstrap(")
    assert provider_install < executor_build < runtime_install
    assert '"provider_install_before_executor_build": True' in source
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["missing_capabilities"]:' in source


def test_production_entrypoint_registers_bounded_runtime_diagnostics() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert 'COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/comprehensive-runtime"' in source
    assert "def _register_runtime_diagnostics(target: FastAPI)" in source
    assert 'target.add_api_route(' in source
    assert 'methods=["GET"]' in source
    assert 'status["human_review_required"] = True' in source
    assert 'status["client_delivery_allowed"] = False' in source
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["diagnostics_route_count"] != 1:' in source


def test_dynamic_executor_uses_installed_authorization_provider() -> None:
    app = FastAPI()
    install_native_comprehensive_providers(app)
    executor = build_production_capability_executors(app)["authorization"]
    result = executor(
        {
            "service_id": "comprehensive",
            "run_id": "comprun_binding_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_binding_001",
            "customer_id": "customer_binding",
            "project_id": "project_binding",
        }
    )

    assert result["status"] == "complete"
    assert result["capability"] == "authorization"
    assert result["authorization_confirmed"] is True
    assert result["run_id"] == "comprun_binding_001"
    assert result["commit_sha"] == "a" * 40
