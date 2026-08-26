from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any

from nico.comprehensive_commercial_release_closure_v1 import (
    semantic_renumber_and_outline,
)

VERSION = "nico.comprehensive_commercial_release_closure.v2"
_MARKER = "__nico_commercial_release_cross_format_identity_v2__"


def _text(value: Any, limit: int = 300) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _regenerate_cross_format_outputs(result: dict[str, Any]) -> dict[str, Any]:
    """Regenerate presentation artifacts after canonical display-identity repair.

    v1 fixes the first destructive boundary by retaining customer/project/contact display
    metadata in canonical report identity. The original package has already rendered its
    first Markdown/HTML/PDF by then, so this v2 pass regenerates those formats from the
    repaired canonical identity. Scope IDs, assessment scores, findings, review state and
    delivery authority are not changed.
    """

    from nico import comprehensive_report_package as report_module

    report_package = (
        deepcopy(dict(result.get("report_package") or {}))
        if isinstance(result.get("report_package"), Mapping)
        else {}
    )
    canonical = (
        deepcopy(dict(report_package.get("json") or {}))
        if isinstance(report_package.get("json"), Mapping)
        else {}
    )
    identity = (
        deepcopy(dict(canonical.get("identity") or {}))
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    if not identity:
        return result

    display_present = any(
        _text(identity.get(key))
        for key in ("customer_name", "project_name", "primary_technical_contact")
    )
    if not display_present:
        return result

    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else deepcopy(dict(result.get("assessment") or {}))
    )
    stages = (
        deepcopy(list(canonical.get("stage_summaries") or []))
        if isinstance(canonical.get("stage_summaries"), list)
        else deepcopy(list(result.get("stage_summaries") or []))
    )
    generated_at = _text(result.get("generated_at"), 80)
    if not generated_at:
        return result

    # Keep the executive summary consistent with the repaired report identity. This
    # summary remains technical and does not alter assessment truth.
    assessment["executive_summary"] = report_module._decision_summary(
        identity,
        assessment,
        stages,
    )
    canonical["assessment"] = assessment
    canonical["identity"] = identity

    markdown = report_module._markdown(identity, assessment, stages, generated_at)
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'), 300)}"
    rendered_html = report_module._semantic_html(markdown, title)
    pdf_base64, pdf_error, page_count = report_module._pdf(
        identity,
        assessment,
        stages,
        generated_at,
    )
    pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""

    report_package.update(
        {
            "markdown": markdown,
            "html": rendered_html,
            "json": canonical,
            "pdf_base64": pdf_base64,
            "pdf_error": pdf_error,
            "pdf_page_count": page_count,
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "",
        }
    )
    truth_sha = report_module._canonical_hash(canonical)
    report_package["canonical_truth_sha256"] = truth_sha
    result["canonical_truth_sha256"] = truth_sha
    result["assessment"] = assessment
    result["report_package"] = report_package

    quality = (
        deepcopy(dict(report_package.get("report_quality_contract") or {}))
        if isinstance(report_package.get("report_quality_contract"), Mapping)
        else {}
    )
    quality.update(
        {
            "display_metadata_preserved_in_canonical_report_identity": True,
            "cross_format_outputs_regenerated_from_repaired_identity": True,
            "canonical_scope_ids_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    report_package["report_quality_contract"] = quality
    result["report_quality_contract"] = deepcopy(quality)

    if pdf_base64 and not pdf_error and pdf_bytes.startswith(b"%PDF"):
        result["status"] = "complete"
    return result


def install_comprehensive_commercial_release_closure_v2() -> dict[str, Any]:
    """Install v1 root-cause repairs plus a cross-format regeneration boundary."""

    from nico.comprehensive_commercial_release_closure_v1 import (
        install_comprehensive_commercial_release_closure_v1,
    )
    import nico.comprehensive_report_worker_runtime_v90 as worker

    v1 = install_comprehensive_commercial_release_closure_v1()
    current = worker.build_comprehensive_report_package
    if getattr(current, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "v1": v1,
            "cross_format_identity_regeneration": True,
            "canonical_scope_ids_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def build_with_cross_format_identity(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        return _regenerate_cross_format_outputs(result)

    setattr(build_with_cross_format_identity, _MARKER, True)
    setattr(build_with_cross_format_identity, "_nico_previous", current)
    worker.build_comprehensive_report_package = build_with_cross_format_identity
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "v1": v1,
        "cross_format_identity_regeneration": True,
        "canonical_scope_ids_unchanged": True,
        "scores_findings_review_and_delivery_authority_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_commercial_release_closure_v2",
    "semantic_renumber_and_outline",
]
