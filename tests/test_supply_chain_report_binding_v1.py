from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico.supply_chain_report_binding_v1 import install_supply_chain_report_binding_v1


def _result() -> dict:
    return {
        "status": "complete",
        "assessment": {"findings_register": []},
        "evidence_manifest": {"exports": {}},
        "premium_artifact_manifest": [
            {"artifact_id": "sbom_json", "filename": "13_sbom.json", "status": "planned"}
        ],
        "report_quality_contract": {},
        "report_package": {"report_id": "report_supply_chain"},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_binding_exports_sbom_license_and_upgrade_ledgers(monkeypatch) -> None:
    def fake_builder(*, identity, stage_results):
        del identity, stage_results
        return deepcopy(_result())

    monkeypatch.setattr(report_module, "build_comprehensive_report_package", fake_builder)
    installed = install_supply_chain_report_binding_v1()
    assert installed["sbom_exported"] is True
    assert installed["unsupported_license_clean_claim_allowed"] is False

    result = report_module.build_comprehensive_report_package(
        identity={"repository": "BoneManTGRM/NICO", "commit_sha": "a" * 40, "run_id": "comprun_supply"},
        stage_results={
            "repo_evidence": {
                "dependency_evidence": {
                    "dependencies": [
                        {"name": "fastapi", "version": "0.115.0", "ecosystem": "PyPI", "license": "MIT"},
                        {"name": "react", "version": "19.0.0", "ecosystem": "npm"},
                    ]
                }
            }
        },
    )

    assert result["supply_chain_inventory"]["component_count"] == 2
    package = result["report_package"]
    assert package["supply_chain_inventory_json"]
    assert package["sbom_json"]
    assert "fastapi" in package["license_register_csv"]
    assert "react" in package["dependency_upgrade_register_csv"]
    assert package["sbom_sha256"]

    exports = result["evidence_manifest"]["exports"]
    assert exports["sbom_json_sha256"] == package["sbom_sha256"]
    assert exports["license_register_csv_sha256"] == package["license_register_sha256"]
    assert result["premium_artifact_manifest"][0]["status"] == "ready"
    assert result["report_quality_contract"]["unknown_licenses_disclosed"] is True
    assert result["report_quality_contract"]["unsupported_license_clean_claim_allowed"] is False
    assert result["client_delivery_allowed"] is False


def test_binding_is_idempotent() -> None:
    first = install_supply_chain_report_binding_v1()
    second = install_supply_chain_report_binding_v1()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
