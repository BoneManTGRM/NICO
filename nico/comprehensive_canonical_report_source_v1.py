from __future__ import annotations

from typing import Any, Mapping

from nico.comprehensive_report_package import (
    VERSION as SOURCE_VERSION,
    _assessment,
    _canonical_hash,
    _decision_summary,
    _now,
    _stage_summary,
    _text,
)

VERSION = "nico.comprehensive_canonical_report_source.v1"
_REQUIRED_IDENTITY_FIELDS = (
    "run_id",
    "repository",
    "commit_sha",
    "evidence_ledger_id",
    "customer_id",
    "project_id",
)
_FINAL_STAGE_ID = "final_comprehensive_report_generation"


def build_canonical_report_source(context: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact canonical report model without rendering legacy artifacts.

    The production v2 publisher is the authoritative Markdown, HTML, JSON, and PDF
    renderer. Building a complete legacy draft first caused the final stage to render,
    rewrite, parse, and hash large artifacts twice. This source reuses the same native
    identity, assessment, stage-summary, and decision-summary functions while omitting
    all pre-v2 artifact rendering.
    """

    identity = {
        field: _text(context.get(field), 180)
        for field in _REQUIRED_IDENTITY_FIELDS
    }
    missing = [field for field, value in identity.items() if not value]
    if missing:
        return {
            "status": "blocked",
            "reason": "canonical_report_identity_incomplete",
            "missing_identity_fields": missing,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    raw_stages = context.get("prior_stage_results")
    if not isinstance(raw_stages, Mapping):
        return {
            "status": "blocked",
            "reason": "canonical_report_stage_results_unavailable",
            **identity,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    ordered = [
        _stage_summary(str(stage_id), result)
        for stage_id, result in raw_stages.items()
        if isinstance(result, Mapping) and str(stage_id) != _FINAL_STAGE_ID
    ]
    assessment = _assessment(dict(raw_stages))
    assessment = dict(assessment)
    assessment["repository"] = identity["repository"]
    assessment["commit_sha"] = identity["commit_sha"]
    assessment["run_id"] = identity["run_id"]
    assessment["executive_summary"] = _decision_summary(identity, assessment, ordered)

    canonical = {
        "service_id": "comprehensive",
        "identity": identity,
        "assessment": assessment,
        "stage_summaries": ordered,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = _canonical_hash(canonical)
    report_id = (
        "comprehensive_report_"
        + _canonical_hash({"identity": identity, "stages": ordered})[:20]
    )
    generated_at = _now()
    package = {
        "report_id": report_id,
        "generated_at": generated_at,
        "json": canonical,
        "canonical_truth_sha256": truth_sha,
        "source_artifact_schema": SOURCE_VERSION,
        "canonical_only_source": True,
        "legacy_markdown_rendered": False,
        "legacy_html_rendered": False,
        "legacy_pdf_rendered": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "status": "complete",
        "reason": "",
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "report_id": report_id,
        "generated_at": generated_at,
        "report_package": package,
        "canonical_report": canonical,
        "assessment": assessment,
        "stage_summaries": ordered,
        "canonical_truth_sha256": truth_sha,
        "canonical_only_source": True,
        "single_artifact_render_required": True,
        **identity,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "build_canonical_report_source"]
