from __future__ import annotations

import json

from nico.supply_chain_inventory_v1 import (
    build_supply_chain_inventory,
    cyclonedx_sbom,
    inventory_json,
    license_register_csv,
    sbom_json,
    upgrade_register_csv,
)


IDENTITY = {
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "run_id": "comprun_supply_chain",
}


def _stages() -> dict:
    return {
        "repo_evidence": {
            "status": "complete",
            "dependency_evidence": {
                "dependencies": [
                    {
                        "name": "fastapi",
                        "version": "0.115.0",
                        "ecosystem": "PyPI",
                        "license": "MIT",
                        "direct": True,
                        "source": "requirements.txt",
                    },
                    {
                        "name": "react",
                        "version": "19.0.0",
                        "ecosystem": "npm",
                        "direct": True,
                        "source": "apps/web/package-lock.json",
                    },
                ]
            },
        },
        "scanner_worker": {
            "status": "complete",
            "scanner_results": [
                {
                    "tool": "pip-audit",
                    "category": "dependency",
                    "status": "completed",
                    "findings": [
                        {
                            "package": "fastapi",
                            "installed_version": "0.115.0",
                            "ecosystem": "PyPI",
                            "id": "PYSEC-EXAMPLE",
                            "severity": "high",
                        }
                    ],
                }
            ],
        },
    }


def test_inventory_retains_components_and_unknown_license_truth() -> None:
    inventory = build_supply_chain_inventory(identity=IDENTITY, stage_results=_stages())

    assert inventory["status"] == "review_limited"
    assert inventory["component_count"] >= 2
    by_name = {item["name"]: item for item in inventory["components"]}
    assert by_name["fastapi"]["version"] == "0.115.0"
    assert by_name["fastapi"]["license"] == "MIT"
    assert by_name["fastapi"]["purl"] == "pkg:pypi/fastapi@0.115.0"
    assert by_name["react"]["license"] == "UNKNOWN"
    assert inventory["components_with_unknown_license"] >= 1
    assert inventory["license_assurance"] == "REVIEW LIMITED"
    assert "does not become a clean claim" in inventory["guardrail"]


def test_empty_inventory_is_unavailable_not_clean() -> None:
    inventory = build_supply_chain_inventory(identity=IDENTITY, stage_results={})

    assert inventory["status"] == "unavailable"
    assert inventory["component_count"] == 0
    assert inventory["license_assurance"] == "UNAVAILABLE"
    assert inventory["human_review_required"] is True
    assert inventory["client_delivery_allowed"] is False


def test_cyclonedx_export_is_machine_readable_and_evidence_labeled() -> None:
    inventory = build_supply_chain_inventory(identity=IDENTITY, stage_results=_stages())
    bom = cyclonedx_sbom(inventory)

    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    assert bom["metadata"]["component"]["name"] == "BoneManTGRM/NICO"
    assert len(bom["components"]) == inventory["component_count"]
    react = next(item for item in bom["components"] if item["name"] == "react")
    assert react["licenses"] == []
    assert any(item["name"] == "nico:license_evidence" for item in react["properties"])
    assert json.loads(sbom_json(inventory))["bomFormat"] == "CycloneDX"
    assert json.loads(inventory_json(inventory))["component_count"] == inventory["component_count"]


def test_license_and_upgrade_exports_preserve_unknowns() -> None:
    inventory = build_supply_chain_inventory(identity=IDENTITY, stage_results=_stages())
    licenses = license_register_csv(inventory)
    upgrades = upgrade_register_csv(inventory)

    assert "fastapi" in licenses
    assert "MIT" in licenses
    assert "react" in licenses
    assert "UNKNOWN" in licenses
    assert "latest_version" in upgrades
    assert "vulnerability_count" in upgrades
