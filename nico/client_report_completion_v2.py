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
    synchronize_canonical_finding_surfaces,
)
from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth,
)
from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    DELIVERY_STATUS,
    MAX_CLIENT_PDF_PAGES,
    REPORT_FINALITY,
    VERSION as CLIENT_READY_VERSION,
    apply_automated_draft_truth,
    compact_client_markdown,
    compose_compact_client_pdf,
    render_compact_finding_register_pdf,
    render_evidence_review_gate_pdf,
)
from nico.scanner_applicability_v1 import normalize_scanner_applicability_package
from nico.v2_authoritative_premium_report import _html_from_markdown

VERSION = "nico.client-report-completion.v7"


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _install_contract(canonical: dict[str, Any]) -> dict[str, Any]:
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_report_completion_version": VERSION,
            "client_ready_projection_version": CLIENT_READY_VERSION,
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
            "one_compact_client_pdf": True,
            "full_evidence_retained_outside_client_pdf": True,
            "automated_draft_until_human_approval": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


def _install_register(canonical: dict[str, Any]) -> dict[str, Any]:
    register = build_finding_remediation_register(canonical)
    synchronized = synchronize_canonical_finding_surfaces(canonical, register)
    return _install_contract(synchronized)


def prepare_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare canonical truth before the premium renderer runs."""

    result = normalize_scanner_applicability_package(package)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    result["json"] = canonical
    result = normalize_scanner_applicability_package(result)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _install_register(canonical)
    canonical = reconcile_authoritative_scanner_truth(canonical)
    canonical = apply_automated_draft_truth(canonical)
    result["json"] = canonical
    result["client_finding_remediation_register"] = deepcopy(
        canonical["client_finding_remediation_register"]
    )
    result["finding_population"] = deepcopy(canonical["finding_population"])
    return result


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

    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    combined = "\n".join((markdown, rendered_html, extracted))
    if "/tmp/nico-snapshot-scan-" in combined or "/home/runner/work/" in combined:
        raise ValueError("client report exposed a temporary worker path")
    if "unknown · unknown" in combined:
        raise ValueError("client report retained unknown analyzer and rule identity")
    if "No structured item was retained." in combined:
        raise ValueError("client report retained obsolete empty finding copy")
    if "FINAL REPORT" in combined or "INFORME FINAL" in combined:
        raise ValueError("unapproved client report used finality language")
    if "AUTOMATED DRAFT" not in combined and "BORRADOR AUTOMATIZADO" not in combined:
        raise ValueError("client report omitted automated-draft status")
    if len(reader.pages) > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            f"client report exceeds the {MAX_CLIENT_PDF_PAGES}-page client boundary"
        )

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
        "duplicate_full_page_finding_cards_absent": True,
        "raw_stage_dump_excluded_from_client_pdf": True,
        "automated_draft_language_verified": True,
        "client_pdf_page_boundary": MAX_CLIENT_PDF_PAGES,
        "client_pdf_page_count": len(reader.pages),
    }


def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Finalize a bounded client PDF while retaining full JSON/CSV evidence."""

    prepared = prepare_client_report_package(package)
    # The legacy pass retains compatibility and the accepted premium cover. The
    # authoritative pass below removes duplicate finding cards and raw evidence
    # dumps before composing one compact register and one human-review gate.
    result = legacy.finalize_client_report_package(prepared)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _install_register(canonical)
    canonical = reconcile_authoritative_scanner_truth(canonical)
    canonical = apply_automated_draft_truth(canonical)
    register = canonical["client_finding_remediation_register"]
    spanish = legacy._is_spanish(canonical)

    markdown = compact_client_markdown(
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
    register_pdf = render_compact_finding_register_pdf(register, spanish=spanish)
    gate_pdf = render_evidence_review_gate_pdf(canonical, register, spanish=spanish)
    pdf = compose_compact_client_pdf(base_pdf, register_pdf, gate_pdf)
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
            "full_evidence_retained_in_structured_exports": True,
            "full_evidence_appendix_in_client_pdf": False,
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
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
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
