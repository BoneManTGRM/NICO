from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_native_providers_v5 import install_native_comprehensive_providers
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
    native = app.state.nico_native_comprehensive_provider_status
    assert native["same_sha_score_deterministic"] is True
    assert native["mutable_operational_history_affects_score"] is False
    assert native["score_override_allowed"] is False
    assert native["verified_material_only_technical_scoring"] is True
    assert native["review_candidate_volume_affects_technical_score"] is False
    assert native["canonical_finding_deduplication_bound"] is True
    assert native["score_alias_synchronization_bound"] is True
    assert native["canonical_scanner_finding_register_bound"] is True
    assert native["canonical_scanner_finding_count_parity_fail_closed"] is True
    assert native["candidate_volume_affects_technical_score"] is False
    assert native["candidate_volume_affects_evidence_adjusted_score"] is False
    assert native["review_workload_affects_numeric_score"] is False
    assert native["ci_cd_configuration_and_operational_health_separated"] is True


def test_production_entrypoint_installs_providers_before_building_executors() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "from nico import comprehensive_native_providers_v5 as native_provider_v5" in source
    assert "install_candidate_lineage_runtime_patch" in source
    lineage_install = source.index(
        "candidate_lineage_runtime = install_candidate_lineage_runtime_patch()"
    )
    provider_install = source.index(
        "native_providers = native_provider_v5.install_native_comprehensive_providers(target)"
    )
    executor_build = source.index("executors = build_production_capability_executors(target)")
    runtime_install = source.index("controller = install_comprehensive_production_bootstrap(")
    assert lineage_install < provider_install < executor_build < runtime_install
    assert '"candidate_lineage_runtime_before_provider_install": True' in source
    assert '"candidate_lineage_runtime_bound": candidate_lineage_runtime_bound' in source
    assert '"provider_install_before_executor_build": True' in source
    assert '"category_specific_scoring_bound": category_specific_scoring_bound' in source
    assert '"same_sha_score_deterministic": same_sha_score_deterministic' in source
    assert '"mutable_operational_history_affects_score": mutable_operational_history_affects_score' in source
    assert '"score_override_allowed": False' in source
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["candidate_lineage_runtime_bound"] is not True:' in source
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
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["same_sha_score_deterministic"] is not True:' in source
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["mutable_operational_history_affects_score"] is not False:' in source


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
