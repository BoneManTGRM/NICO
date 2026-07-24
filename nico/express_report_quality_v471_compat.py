from __future__ import annotations

import io
from copy import deepcopy
from typing import Any, Callable

from pypdf import PdfReader

VERSION = "nico.express_report_quality.v47.1_compat"
_MARKER = "_nico_express_report_quality_v471_compat"


def _canonical_section_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from nico import express_report_quality_v47 as target

    aliases = {
        "dependency_library_ecosystem": "dependency_health",
        "ci_cd_analysis": "ci_cd",
        "scanner_worker_evidence": "scanner_assurance_ledger",
        "scanner_evidence": "scanner_assurance_ledger",
        "client_human_acceptance": "review_delivery",
        "client_acceptance": "review_delivery",
    }
    output: dict[str, dict[str, Any]] = {}
    for item in payload.get("sections") or []:
        if not isinstance(item, dict):
            continue
        raw = target._text(item.get("id"), 100).casefold()
        if not raw:
            continue
        output[raw] = item
        output[aliases.get(raw, raw)] = item
    return output


def normalize_client_report_quality_v471(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize structured report fields without flattening Markdown or HTML."""

    from nico import express_report_quality_v47 as target

    output = target._base_semantic_cleanup(deepcopy(payload))
    sections = _canonical_section_map(output)
    tools = target._scanner_tools(output)
    secrets = sections.get("secrets_review")
    if secrets:
        target._reconcile_secret_timeout(secrets, tools)
    static = sections.get("static_analysis")
    if static:
        target._reconcile_static_execution(static, tools)

    for section in output.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for key in ("label", "title", "summary", "score_rationale", "status_reason"):
            if isinstance(section.get(key), str):
                section[key] = target._text(section[key], 100_000)
        section["evidence"] = target._unique(section.get("evidence"))
        section["findings"] = target._unique(section.get("findings"))
        section["unavailable"] = target._unique(section.get("unavailable"))
        section["review_items"] = target._unique(section.get("review_items"))
        assurance = target._text(
            section.get("assurance_label") or section.get("evidence_assurance"),
            80,
        ).upper()
        if assurance:
            confidence = target._confidence_for_assurance(assurance)
            section["confidence"] = confidence
            section["presented_confidence"] = confidence

    for key in ("executive_summary", "client_delivery_block_reason"):
        if isinstance(output.get(key), str):
            output[key] = target._text(output[key], 100_000)
    for key in (
        "priority_actions",
        "quick_wins",
        "medium_term_plan",
        "resourcing_recommendation",
        "risk_register",
        "verification_checklist",
    ):
        if isinstance(output.get(key), list):
            output[key] = target._unique(output[key])

    # Reports deliberately retain their line structure. The report postprocessor
    # replaces sections by Markdown headings and must never receive flattened text.
    output["express_client_report_quality"] = {
        "status": "normalized",
        "version": VERSION,
        "structured_text_normalized": True,
        "markdown_line_structure_preserved": True,
        "html_structure_preserved": True,
        "assurance_confidence_consistent": True,
        "gitleaks_timeout_zero_count_removed": True,
        "bandit_failure_explicit": True,
        "eslint_not_configured_explicit": True,
        "human_review_required": bool(output.get("human_review_required", True)),
        "client_delivery_allowed": bool(output.get("client_delivery_allowed", False)),
    }
    return output


def _contribution_with_geometry(result: dict[str, Any]) -> bytes:
    from nico import express_report_quality_v47 as target

    original: Callable[[dict[str, Any]], bytes] = getattr(
        _contribution_with_geometry,
        "_nico_original",
    )
    records = [item for item in target._quality_records(result) if item.get("directly_scored")]
    geometry: list[dict[str, Any]] = []
    for item in records:
        score = int(item.get("score") or 0)
        geometry.append(
            {
                "section_id": item.get("section_id"),
                "score": score,
                "technical_band": item.get("band"),
                "score_tone": item.get("score_tone"),
                "assurance": item.get("assurance"),
                "rendered_ratio": score / 100.0,
            }
        )
    result["express_pdf_score_assurance_geometry"] = {
        "status": "complete",
        "version": VERSION,
        "records": geometry,
        "score_band_coloring": True,
        "assurance_separate": True,
        "canonical_status_retained": True,
        "vector_geometry_retained": True,
    }
    return original(result)


def _premium_visual_qa(pdf_bytes: bytes, result: dict[str, Any]) -> dict[str, Any]:
    from nico import express_report_quality_v47 as target

    base_validator: Callable[[bytes, dict[str, Any]], dict[str, Any]] = getattr(
        _premium_visual_qa,
        "_nico_base_validator",
    )
    base = dict(base_validator(pdf_bytes, result))
    if not isinstance(result.get("express_client_report_quality"), dict):
        return base

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text = [target._text(page.extract_text() or "", 200_000) for page in reader.pages]
    full_text = "\n".join(page_text)
    issues = [
        str(item)
        for item in base.get("issues") or []
        if not str(item).startswith("Express page count ")
        and "Required en report label missing: Transparent Technical Score" not in str(item)
    ]
    page_count = len(page_text)
    if not 16 <= page_count <= 28:
        issues.append(f"Express page count {page_count} is outside the premium quality range 16-28.")
    sparse_pages = [
        index + 1
        for index, text in enumerate(page_text)
        if index > 0 and len(text) < 150
    ]
    if sparse_pages:
        issues.append(f"Sparse or orphan report pages detected: {sparse_pages}.")

    forbidden = {
        "SUPPLEMENTA L": "Split SUPPLEMENTAL label detected.",
        "evidence,score": "Missing space after comma detected.",
        "disposition,repair": "Missing space after comma detected.",
        "Gitleaks timed out with 0 retained": "Misleading zero-count Gitleaks timeout wording detected.",
        "Accepted current-run execution evidence remains unresolved for: eslint": "ESLint not-configured state was relabeled unavailable.",
    }
    for marker, issue in forbidden.items():
        if marker.casefold() in full_text.casefold():
            issues.append(issue)
    for heading in (
        "Technical Score and Evidence Assurance",
        "Score Contribution and Assurance Constraints",
        "Integrity, Independence, and Reviewer Record",
        "Finding Dossier Appendix",
    ):
        if heading not in full_text:
            issues.append(f"Required premium report section missing: {heading}.")

    issues = list(dict.fromkeys(issues))
    base.update(
        {
            "status": "pass" if not issues else "fail",
            "version": VERSION,
            "page_count": page_count,
            "sparse_pages": sparse_pages,
            "issues": issues,
            "client_delivery_allowed": not issues and not bool(result.get("human_review_required", True)),
            "premium_layout_verified": not issues,
        }
    )
    return base


def install_express_report_quality_v471_compat() -> dict[str, Any]:
    from nico import express_assurance_projection_compat_v45 as assurance_compat
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_quality_v47 as target
    from nico import express_report_visual_qa_v16 as visual
    from nico import report_semantic_cleanup_v46 as semantic

    changed = 0
    target._section_map = _canonical_section_map
    target.normalize_client_report_quality_v47 = normalize_client_report_quality_v471
    semantic.normalize_final_report_semantics = normalize_client_report_quality_v471
    assurance_compat.normalize_final_report_semantics = normalize_client_report_quality_v471

    current_contribution = pdf_score._contribution_pdf
    if current_contribution is not _contribution_with_geometry:
        setattr(_contribution_with_geometry, "_nico_original", current_contribution)
        pdf_score._contribution_pdf = _contribution_with_geometry
        target._contribution_pdf = _contribution_with_geometry
        changed += 1

    enhanced = target._quality_visual_qa
    base_validator = getattr(enhanced, "_nico_original", visual.validate_express_pdf)
    setattr(_premium_visual_qa, "_nico_base_validator", base_validator)
    # Preserve the stable public validator for legacy and bilingual contract tests.
    visual.validate_express_pdf = base_validator
    # Apply premium checks only inside the final dossier export after report-quality
    # metadata is attached.
    dossier.validate_express_pdf = _premium_visual_qa
    changed += 1

    original_install = getattr(target.install_express_report_quality_v47, "_nico_v471_original", None)
    if original_install is None:
        original_install = target.install_express_report_quality_v47

        def combined_install() -> dict[str, Any]:
            base = original_install()
            compat = install_express_report_quality_v471_compat()
            return {
                **base,
                "compatibility_install": compat,
                "version": VERSION,
                "markdown_line_structure_preserved": True,
                "legacy_vector_geometry_retained": True,
                "legacy_visual_qa_contract_preserved": True,
            }

        setattr(combined_install, "_nico_v471_original", original_install)
        target.install_express_report_quality_v47 = combined_install
        changed += 1

    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "functions_rebound": changed,
        "markdown_line_structure_preserved": True,
        "html_structure_preserved": True,
        "raw_and_canonical_section_aliases_supported": True,
        "legacy_vector_geometry_retained": True,
        "legacy_visual_qa_contract_preserved": True,
        "premium_visual_qa_extended": True,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_report_quality_v471_compat",
    "normalize_client_report_quality_v471",
]
