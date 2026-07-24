from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico.supply_chain_inventory_v1 import (
    VERSION as INVENTORY_VERSION,
    build_supply_chain_inventory,
    inventory_json,
    license_register_csv,
    sbom_json,
    upgrade_register_csv,
)

VERSION = "nico.supply_chain_report_binding.v1"
_MARKER = "_nico_supply_chain_report_binding_v1"


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def install_supply_chain_report_binding_v1() -> dict[str, Any]:
    current: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "inventory_version": INVENTORY_VERSION,
            "sbom_exported": True,
            "unknown_licenses_disclosed": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def build_with_supply_chain(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        output = deepcopy(result)
        identity = _record(kwargs.get("identity"))
        stages = _record(kwargs.get("stage_results"))
        assessment = _record(output.get("assessment"))
        inventory = build_supply_chain_inventory(identity=identity, stage_results=stages, assessment=assessment)
        inventory_payload = inventory_json(inventory)
        sbom_payload = sbom_json(inventory)
        license_csv = license_register_csv(inventory)
        upgrade_csv = upgrade_register_csv(inventory)

        package = _record(output.get("report_package"))
        package.update(
            {
                "supply_chain_inventory_json": inventory_payload,
                "supply_chain_inventory_sha256": _sha256(inventory_payload),
                "sbom_json": sbom_payload,
                "sbom_sha256": _sha256(sbom_payload),
                "license_register_csv": license_csv,
                "license_register_sha256": _sha256(license_csv),
                "dependency_upgrade_register_csv": upgrade_csv,
                "dependency_upgrade_register_sha256": _sha256(upgrade_csv),
            }
        )

        evidence_manifest = _record(output.get("evidence_manifest") or package.get("evidence_manifest"))
        exports = _record(evidence_manifest.get("exports"))
        exports.update(
            {
                "supply_chain_inventory_json_sha256": package["supply_chain_inventory_sha256"],
                "sbom_json_sha256": package["sbom_sha256"],
                "license_register_csv_sha256": package["license_register_sha256"],
                "dependency_upgrade_register_csv_sha256": package["dependency_upgrade_register_sha256"],
            }
        )
        evidence_manifest["exports"] = exports
        evidence_manifest["supply_chain_inventory_status"] = inventory.get("status")
        evidence_manifest["unknown_license_count"] = inventory.get("components_with_unknown_license")
        package["evidence_manifest"] = evidence_manifest
        package["evidence_manifest_json"] = json.dumps(evidence_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

        artifacts = [
            deepcopy(item)
            for item in (output.get("premium_artifact_manifest") or package.get("premium_artifact_manifest") or [])
            if isinstance(item, dict)
        ]
        for item in artifacts:
            if item.get("artifact_id") == "sbom_json":
                item["status"] = "ready" if inventory.get("component_count") else "review_limited"
        package["premium_artifact_manifest"] = artifacts

        quality = _record(output.get("report_quality_contract") or package.get("report_quality_contract"))
        quality.update(
            {
                "supply_chain_inventory_exported": True,
                "sbom_exported": True,
                "license_register_exported": True,
                "dependency_upgrade_register_exported": True,
                "unknown_licenses_disclosed": "components_with_unknown_license" in inventory,
                "unsupported_license_clean_claim_allowed": False,
            }
        )
        package["report_quality_contract"] = quality
        output["supply_chain_inventory"] = inventory
        output["sbom"] = json.loads(sbom_payload)
        output["evidence_manifest"] = evidence_manifest
        output["premium_artifact_manifest"] = artifacts
        output["report_quality_contract"] = quality
        output["report_package"] = package
        return output

    setattr(build_with_supply_chain, _MARKER, True)
    setattr(build_with_supply_chain, "_nico_previous", current)
    report_module.build_comprehensive_report_package = build_with_supply_chain
    return {
        "status": "installed",
        "version": VERSION,
        "inventory_version": INVENTORY_VERSION,
        "supply_chain_inventory_exported": True,
        "sbom_exported": True,
        "license_register_exported": True,
        "upgrade_register_exported": True,
        "unknown_licenses_disclosed": True,
        "unsupported_license_clean_claim_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_supply_chain_report_binding_v1"]
