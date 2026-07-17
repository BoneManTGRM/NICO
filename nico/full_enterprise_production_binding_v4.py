from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.full_enterprise_dossiers_v3 import build_enterprise_dossiers, build_enterprise_visual_data

VERSION = "full_enterprise_production_binding_v4"
_INSTALLED = False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def enrich_full_enterprise_output(assessment: dict[str, Any]) -> dict[str, Any]:
    """Attach enterprise dossiers and visual truth to the active Full payload."""
    enriched = deepcopy(assessment)
    dossiers = build_enterprise_dossiers(enriched)
    visuals = build_enterprise_visual_data(enriched)
    enriched["full_enterprise_production_binding"] = {
        "version": VERSION,
        "production_bound": True,
        "pdf_bound": True,
        "html_bound": True,
        "markdown_bound": True,
        "dossier_count": len(dossiers),
        "visual_count": int(visuals.get("visual_count") or 0),
        "minimum_pages": 70,
        "maximum_pages": 120,
        "target_pages": 90,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    enriched["human_review_required"] = True
    enriched["client_ready"] = False
    return enriched


def install_full_enterprise_production_binding_v4() -> dict[str, Any]:
    """Bind Full enterprise records after the progressive Full production patch."""
    global _INSTALLED
    if _INSTALLED:
        return {"status": "already_installed", "version": VERSION}

    from nico import full_assessment_idempotent_handlers as handler_module
    from nico import full_assessment_trust_pipeline as trust_pipeline

    previous_prepare = trust_pipeline.prepare_full_assessment_trust
    previous_handler = handler_module._reports_handler

    def enterprise_prepare(assessment: dict[str, Any], scanner_evidence: dict[str, Any]) -> dict[str, Any]:
        return enrich_full_enterprise_output(previous_prepare(assessment, scanner_evidence))

    def enterprise_reports_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = previous_handler(context, outputs)
        if result.get("status") != "complete":
            return result

        scoring = _dict(outputs.get("scoring"))
        assessment = enrich_full_enterprise_output(_dict(scoring.get("assessment")))
        dossiers = deepcopy(_dict(assessment.get("full_enterprise_dossiers")))
        visuals = deepcopy(_dict(assessment.get("full_enterprise_visual_data")))
        binding = deepcopy(_dict(assessment.get("full_enterprise_production_binding")))

        package = _dict(result.get("report_package"))
        reports = _dict(result.get("reports"))
        evidence = _dict(result.get("evidence"))

        package["full_enterprise_dossiers"] = dossiers
        package["full_enterprise_visual_data"] = visuals
        package["full_enterprise_production_binding"] = binding
        package["human_review_required"] = True
        package["client_delivery_allowed"] = False

        reports["full_enterprise_dossiers"] = dossiers
        reports["full_enterprise_visual_data"] = visuals
        reports["full_enterprise_production_binding"] = binding
        reports["human_review_required"] = True
        reports["client_delivery_allowed"] = False

        evidence["enterprise_dossier_count"] = int(dossiers.get("count") or 0)
        evidence["enterprise_visual_count"] = int(visuals.get("visual_count") or 0)
        evidence["human_review_required"] = True
        evidence["client_delivery_allowed"] = False

        result["report_package"] = package
        result["reports"] = reports
        result["evidence"] = evidence
        return result

    trust_pipeline.prepare_full_assessment_trust = enterprise_prepare
    handler_module._reports_handler = enterprise_reports_handler
    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "minimum_pages": 70,
        "maximum_pages": 120,
        "target_pages": 90,
        "visuals": 22,
        "human_review_required": True,
    }


__all__ = ["VERSION", "enrich_full_enterprise_output", "install_full_enterprise_production_binding_v4"]
