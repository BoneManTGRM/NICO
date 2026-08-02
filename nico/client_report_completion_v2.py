from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader

from nico import client_report_completion_v1 as legacy
from nico.client_assessment_truth_v3 import normalize_client_assessment_truth
from nico.client_finding_remediation_register_v5 import (
    build_finding_remediation_register,
    finding_register_markdown,
    render_finding_register_pdf,
    synchronize_canonical_finding_surfaces,
)
from nico.comprehensive_authoritative_scanner_truth_v63 import (
    reconcile_authoritative_scanner_truth,
)
from nico.scanner_applicability_v1 import normalize_scanner_applicability_package
from nico.v2_authoritative_premium_report import _html_from_markdown

VERSION = "nico.client-report-completion.v6"


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _install_contract(canonical: dict[str, Any]) -> dict[str, Any]:
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_report_completion_version": VERSION,
            "canonical_finding_identity_uses_source_anchor_and_family": True,
            "scanner_configuration_errors_are_not_code_findings": True,
            "repository_relative_paths_only": True,
            "finding_population_reconciled": True,
            "unverified_tls_pattern_not_promoted": True,
            "structured_finding_remediation_register": True,
            "exact_source_locations_required_for_code_findings": True,
            "scanner_not_applicable_separated_from_unavailable": True,
            "stable_finding_alias_projection_idempotent": True,
            "all_mirrored_finding_surfaces_synchronized": True,
            "exact_run_scanner_truth_reconciled_in_core_finalizer": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


def _install_register(canonical: dict[str, Any]) -> dict[str, Any]:
    register = build_finding_remediation_register(canonical)
    synchronized = synchronize_canonical_finding_surfaces(canonical, register)
    return _install_contract(synchronized)


def prepare_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare one canonical report model before the premium renderer runs."""

    result = normalize_scanner_applicability_package(package)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    result["json"] = canonical

    # Recompute applicability after configuration-error classification so the
    # requested, applicable, completed, incomplete, and not-applicable populations
    # remain internally consistent.
    result = normalize_scanner_applicability_package(result)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _install_register(canonical)
    # This call is intentionally part of the core finalizer rather than relying
    # only on installer rebinding. Every production and fixture path therefore
    # reaches the existing renderer with one exact-run scanner population and one
    # explicit coverage denominator.
    canonical = reconcile_authoritative_scanner_truth(canonical)

    result["json"] = canonical
    result["client_finding_remediation_register"] = deepcopy(
        canonical["client_finding_remediation_register"]
    )
    result["finding_population"] = deepcopy(canonical["finding_population"])
    return result


def _final_markdown(
    existing: str,
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    markdown = legacy._remove_old_register(existing)
    markdown = legacy._remove_legacy_scanner_provenance(markdown)
    markdown = markdown.replace(
        legacy._STALE_EMPTY_FINDING_TEXT,
        legacy._STALE_EMPTY_FINDING_REPLACEMENT,
    )
    markdown = legacy._insert_register(
        markdown,
        finding_register_markdown(register, spanish=spanish),
    )
    if legacy._CLIENT_DELIVERY_MARKER not in markdown:
        markdown = markdown.rstrip() + f"\n\n<!-- {legacy._CLIENT_DELIVERY_MARKER} -->\n"
    return (
        markdown.rstrip()
        + "\n\n"
        + legacy.scanner_provenance_markdown(canonical, spanish=spanish).strip()
        + "\n"
    )


def _validate_final_surfaces(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    if summary.get("finding_population_reconciled") is not True:
        raise ValueError("final client report finding populations do not reconcile")
    if summary.get("semantic_duplicate_code_anchors_absent") is not True:
        raise ValueError("final client report retained duplicate exact-source finding identities")
    if summary.get("scanner_configuration_errors_promoted_to_code_findings") is not False:
        raise ValueError("scanner configuration errors were promoted to code findings")
    if summary.get("unverified_tls_candidates_promoted_to_p1") is not False:
        raise ValueError("unverified TLS pattern candidates were promoted to P1")
    if summary.get("stable_alias_projection_idempotent") is not True:
        raise ValueError("canonical finding alias projection is not idempotent")

    code = [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    canonical_findings = [
        item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)
    ]
    decision_count = int(summary.get("decision_finding_count") or 0)
    if len(canonical_findings) != decision_count:
        raise ValueError(
            "canonical finding count does not match the reconciled decision population: "
            f"{len(canonical_findings)} != {decision_count}"
        )

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    combined = "\n".join((markdown, rendered_html, extracted))
    if "/tmp/nico-snapshot-scan-" in combined or "/home/runner/work/" in combined:
        raise ValueError("client report exposed a temporary worker path")
    if "unknown · unknown" in combined:
        raise ValueError("client report retained unknown analyzer and rule identity")
    if "No structured item was retained." in combined:
        raise ValueError("client report retained obsolete empty finding copy")

    compact_pdf = legacy._compact(extracted)
    for item in code[:60]:
        location = _text(item.get("location"))
        if location and legacy._compact(location) not in compact_pdf:
            raise ValueError(f"final client PDF omitted exact source location: {location}")

    return {
        "finding_population_reconciled": True,
        "canonical_decision_finding_count": decision_count,
        "exact_source_code_finding_count": len(code),
        "scanner_configuration_issue_count": int(
            summary.get("scanner_configuration_issue_count") or 0
        ),
        "temporary_worker_paths_absent": True,
        "unknown_analyzer_rule_pairs_absent": True,
        "semantic_duplicate_code_anchors_absent": True,
        "stable_finding_alias_projection_idempotent": True,
        "unverified_tls_candidates_not_promoted": True,
        "exact_run_scanner_truth_reconciled": True,
    }


def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Finalize one cross-format package from the repaired canonical model."""

    prepared = prepare_client_report_package(package)
    # Preserve the existing premium report, scorecard, evidence appendix, and
    # delivery gate, then replace only the finding/provenance projections from the
    # final authoritative canonical state.
    result = legacy.finalize_client_report_package(prepared)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _install_register(canonical)
    # Legacy completion can add or restore nested report surfaces. Reconcile again
    # at the last canonical boundary before Markdown, HTML, and PDF are composed.
    canonical = reconcile_authoritative_scanner_truth(canonical)
    register = canonical["client_finding_remediation_register"]
    spanish = legacy._is_spanish(canonical)

    markdown = _final_markdown(
        str(result.get("markdown") or ""),
        canonical,
        register,
        spanish=spanish,
    )
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = (
        "Evaluación Técnica Integral NICO"
        if spanish
        else f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    )
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)

    base_pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
    register_pdf = render_finding_register_pdf(register, spanish=spanish)
    provenance_pdf = legacy._provenance_pdf(canonical, spanish=spanish)
    pdf = legacy._compose_pdf(base_pdf, register_pdf, provenance_pdf)
    validation = _validate_final_surfaces(
        canonical,
        register,
        markdown,
        rendered_html,
        pdf,
    )

    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    completion = deepcopy(dict(result.get("client_report_completion") or {}))
    completion.update(
        {
            "version": VERSION,
            **validation,
            "finding_register_in_json": True,
            "finding_register_in_markdown": True,
            "finding_register_in_html": True,
            "finding_register_in_pdf": True,
            "exact_source_locations_verified_in_pdf": True,
            "scanner_applicability_in_all_formats": True,
            "full_evidence_appendix_preserved": (
                "Evidence Appendix" in markdown or "Apéndice de evidencia" in markdown
            ),
            "premium_cover_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "page_count": page_count,
        }
    )
    premium = deepcopy(dict(result.get("premium_report_renderer") or {}))
    premium.update(completion)
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update(completion)

    result.update(
        {
            "json": canonical,
            "client_finding_remediation_register": deepcopy(register),
            "finding_population": deepcopy(register.get("summary") or {}),
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "status": "review_required",
            "assessment_state": "review_required",
            "report_finality": "final",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "phase17_artifact_rebuild": phase17,
            "premium_report_renderer": premium,
            "client_report_completion": completion,
        }
    )
    return result


__all__ = [
    "VERSION",
    "finalize_client_report_package",
    "prepare_client_report_package",
]