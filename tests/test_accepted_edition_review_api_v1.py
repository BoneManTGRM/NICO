from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from nico import comprehensive_native_providers as providers
from nico.accepted_edition_report_identity_v1 import (
    install_accepted_edition_report_identity,
    wrap_report_builder_with_accepted_edition_identity,
)
from nico.comprehensive_api_routes import COMPREHENSIVE_API_ROUTES


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "nico" / "comprehensive_api_routes.py"
BOOTSTRAP = ROOT / "nico" / "api" / "comprehensive_production_bootstrap.py"


def test_review_route_is_canonical_and_requires_explicit_authorization() -> None:
    source = ROUTES.read_text(encoding="utf-8")

    assert ("POST", "/assessment/comprehensive-run/{run_id}/review") in COMPREHENSIVE_API_ROUTES
    assert "explicit_review_authorization_required" in source
    assert 'payload.get("review_authorized") is not True' in source
    assert 'payload.get("authorization_confirmed") is not True' in source
    assert 'operation="reviewed"' in source


def test_report_identity_wrapper_binds_language_and_depth_before_review() -> None:
    def delegate(*, identity: dict, stage_results: dict) -> dict:
        del stage_results
        return {
            "status": "complete",
            "report_package": {
                "json": {
                    "identity": {
                        "repository": identity["repository"],
                        "commit_sha": identity["commit_sha"],
                        "run_id": identity["run_id"],
                    }
                },
                "report_quality_contract": {},
                "canonical_truth_sha256": "old",
            },
            "canonical_truth_sha256": "old",
        }

    wrapped = wrap_report_builder_with_accepted_edition_identity(delegate)
    result = wrapped(
        identity={
            "repository": "owner/repo",
            "commit_sha": "a" * 40,
            "run_id": "run-1",
            "report_language": "es-MX",
            "assessment_depth": "strategic",
        },
        stage_results={},
    )
    package = result["report_package"]
    canonical = package["json"]

    assert canonical["identity"]["report_language"] == "es-MX"
    assert canonical["identity"]["assessment_depth"] == "strategic"
    assert package["canonical_truth_sha256"] != "old"
    assert package["report_quality_contract"]["accepted_edition_identity_complete"] is True
    assert package["client_delivery_allowed"] is False


def test_production_bootstrap_installs_identity_before_provider_freeze() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "install_accepted_edition_report_identity" in source
    assert "accepted_edition_identity_before_provider_install" in source
    assert '"review_regenerates_report": False' in source


def test_identity_installer_is_idempotent(monkeypatch) -> None:
    original = providers.build_comprehensive_report_package

    def delegate(*args, **kwargs):
        del args, kwargs
        return {"status": "blocked"}

    monkeypatch.setattr(providers, "build_comprehensive_report_package", delegate)
    first = install_accepted_edition_report_identity()
    first_builder = providers.build_comprehensive_report_package
    second = install_accepted_edition_report_identity()

    assert first["bound"] is True
    assert second["bound"] is True
    assert providers.build_comprehensive_report_package is first_builder
    monkeypatch.setattr(providers, "build_comprehensive_report_package", original)
