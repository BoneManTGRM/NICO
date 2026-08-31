from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.comprehensive-client-truth-final.v1"
_MARKER = "__nico_comprehensive_client_truth_final_v1__"
_PREPARE_MARKER = "__nico_comprehensive_client_truth_prepare_v1__"
_COVER_MARKER = "__nico_comprehensive_client_truth_cover_v1__"
_TIMESTAMP = re.compile(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")
_EMPTY = re.compile(r"^[A-Za-z0-9_.\[\]-]+:\s*$")
_INTERNAL_PREFIXES = (
    "stage_execution.",
    "human_evidence_summary.",
    "technical_analysis.activity.sample_commits[",
    "technical_analysis.activity.sample_pull_requests[",
)
_SECTION_CATEGORY = {
    "dependency_health": "dependency",
    "secrets_review": "secret",
    "static_analysis": "static",
}
_ANALYZERS = {
    "dependency": "pip-audit, npm-audit, osv-scanner",
    "secret": "gitleaks, trufflehog",
    "static": "bandit, semgrep, eslint, typescript",
}
_COVER_TEXT = {
    "Decision-Grade Technical Assessment": "Evidence-Bound Technical Review Package",
    "Evaluación técnica para decisiones": "Paquete técnico basado en evidencia",
    "READ-ONLY · IMMUTABLE SNAPSHOT · INTERNAL REVIEW REQUIRED": (
        "READ-ONLY · IMMUTABLE SNAPSHOT · HUMAN REVIEW REQUIRED"
    ),
}


def _text(value: Any, limit: int = 12000) -> str:
    value = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _dict(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in value or [] if isinstance(item, Mapping)]


def _generated_at(value: Mapping[str, Any]) -> str:
    identity = value.get("identity") if isinstance(value.get("identity"), Mapping) else {}
    candidates = (
        identity.get("generated_at"),
        identity.get("generation_timestamp"),
        value.get("generated_at"),
        value.get("generation_timestamp"),
        value.get("markdown"),
        value.get("html"),
    )
    for candidate in candidates:
        match = _TIMESTAMP.search(str(candidate or ""))
        if match:
            return match.group(0)
    encoded = value.get("pdf_base64")
    if encoded:
        try:
            pdf = base64.b64decode(str(encoded), validate=True)
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages[:4]
            )
        except Exception:
            text = ""
        match = _TIMESTAMP.search(text)
        if match:
            return match.group(0)
    return ""


def _set_generated_at(canonical: dict[str, Any], value: str) -> None:
    if not value:
        return
    identity = _dict(canonical.get("identity"))
    identity.update({"generated_at": value, "generation_timestamp": value})
    canonical["identity"] = identity
    canonical["generated_at"] = value
    canonical["generation_timestamp"] = value


def _clean_evidence(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        item = _text(raw, 1200)
        if not item or _EMPTY.fullmatch(item) or item.startswith(_INTERNAL_PREFIXES):
            continue
        if item in {
            "capability: technical_analysis",
            "capability: functional_qa",
            "capability: platform_parity",
            "report_language: en",
            "report_language: es-MX",
            "assessment_depth: strategic",
        }:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _clean_client_literal_evidence(values: Any) -> list[str]:
    """Remove empty/internal rows without rewriting retained client literals."""

    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        item = str(raw) if raw is not None else ""
        if not item.strip() or item.lstrip().startswith(_INTERNAL_PREFIXES):
            continue
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _client_summary_evidence(
    canonical: Mapping[str, Any], values: Any
) -> list[str]:
    """Rebind the five engagement rows to verified canonical literals."""

    from nico.comprehensive_report_review_integrity_v1 import (
        _display_state_values,
        _retained_client_summary_lines,
    )

    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    language = str(
        identity.get("report_language")
        or identity.get("locale")
        or canonical.get("report_language")
        or canonical.get("locale")
        or "en"
    ).casefold()
    spanish = language in {"es-mx", "es_mx"}
    display = _display_state_values(canonical, spanish=spanish)
    labels = (
        (
            ("customer_name", "Nombre del cliente"),
            ("project_name", "Nombre del proyecto"),
            ("primary_technical_contact", "Contacto técnico principal"),
            ("access_method", "Método de acceso"),
            ("authorized_scope", "Alcance autorizado"),
        )
        if spanish
        else (
            ("customer_name", "Client name"),
            ("project_name", "Project name"),
            ("primary_technical_contact", "Primary technical contact"),
            ("access_method", "Access method"),
            ("authorized_scope", "Authorized scope"),
        )
    )
    exact_rows = [f"{label}: {display.get(key)}" for key, label in labels]
    retained = _clean_client_literal_evidence(
        _retained_client_summary_lines(values)
    )
    return [*exact_rows, *retained]


def _sum(summary: Mapping[str, Any], keys: tuple[str, ...]) -> int:
    return sum(_int(summary.get(key)) for key in keys)


def _validate_register(register: Mapping[str, Any]) -> None:
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    by_category = register.get("summary_by_category")
    by_category = by_category if isinstance(by_category, Mapping) else {}
    populations = [("total", totals)] + [
        (str(key), value) for key, value in by_category.items() if isinstance(value, Mapping)
    ]
    for label, summary in populations:
        raw = _int(summary.get("raw"))
        disposition = _sum(
            summary,
            ("approved_or_nonblocking", "excluded_test_only", "material", "review_required"),
        )
        quality = _sum(
            summary,
            ("exact_source", "source_path", "payload_without_source", "count_only"),
        )
        if raw != disposition:
            raise ValueError(
                f"scanner candidate disposition totals do not reconcile for {label}: "
                f"raw={raw}, dispositions={disposition}"
            )
        if raw != quality:
            raise ValueError(
                f"scanner evidence-quality totals do not reconcile for {label}: "
                f"raw={raw}, evidence_quality={quality}"
            )
    findings = _records(register.get("findings"))
    ids = [_text(item.get("candidate_id"), 300) for item in findings]
    if findings and (any(not item for item in ids) or len(ids) != len(set(ids))):
        raise ValueError("retained scanner candidate IDs must be present and unique")
    if findings and len(findings) != _int(totals.get("raw")):
        raise ValueError("retained scanner candidate population does not match the raw total")


def _sync_scanner_sections(canonical: dict[str, Any]) -> None:
    assessment = _dict(canonical.get("assessment"))
    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    by_category = register.get("summary_by_category")
    by_category = by_category if isinstance(by_category, Mapping) else {}
    if not register or not by_category:
        canonical["assessment"] = assessment
        return
    _validate_register(register)
    sections = _records(assessment.get("sections"))
    for section in sections:
        category = _SECTION_CATEGORY.get(_text(section.get("id"), 80))
        if not category:
            continue
        summary = by_category.get(category)
        if not isinstance(summary, Mapping):
            raise ValueError(f"missing canonical scanner category summary: {category}")
        raw = _int(summary.get("raw"))
        approved = _int(summary.get("approved_or_nonblocking"))
        excluded = _int(summary.get("excluded_test_only"))
        material = _int(summary.get("material"))
        review = _int(summary.get("review_required"))
        section.update(
            {
                "approved_nonblocking_candidates": approved,
                "excluded_nonproduction_candidates": excluded,
                "confirmed_material_findings": material,
                "review_required_candidates": review,
                "evidence": [
                    f"Applicable analyzers: {_ANALYZERS[category]}.",
                    f"Raw candidates: {raw}.",
                    f"Approved/nonblocking: {approved}.",
                    f"Excluded non-production/test-only: {excluded}.",
                    f"Confirmed material findings: {material}.",
                    f"Review-required candidates: {review}.",
                    "Score effect: assurance-only until triaged.",
                ],
            }
        )
        contract = _dict(section.get("score_contract"))
        contract.update({"material_count": material, "review_required_count": review})
        section["score_contract"] = contract
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    assessment["sections"] = sections
    assessment["candidate_disposition"] = {
        "total_raw": _int(totals.get("raw")),
        "approved_nonblocking": _int(totals.get("approved_or_nonblocking")),
        "excluded_nonproduction": _int(totals.get("excluded_test_only")),
        "confirmed_material": _int(totals.get("material")),
        "review_required": _int(totals.get("review_required")),
        "exact_source": _int(totals.get("exact_source")),
        "source_path": _int(totals.get("source_path")),
        "payload_without_source": _int(totals.get("payload_without_source")),
        "count_only": _int(totals.get("count_only")),
        "model_version": "mutually-exclusive-candidate-dispositions.v1",
        "mutually_exclusive": True,
        "disposition_arithmetic_verified": True,
        "evidence_quality_arithmetic_verified": True,
    }
    canonical["assessment"] = assessment


def _ci_lines(canonical: Mapping[str, Any]) -> list[str]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    section = next(
        (
            item
            for item in assessment.get("sections") or []
            if isinstance(item, Mapping) and _text(item.get("id")) == "ci_cd"
        ),
        {},
    )
    contract = section.get("score_contract") if isinstance(section.get("score_contract"), Mapping) else {}
    inputs = contract.get("score_inputs") if isinstance(contract.get("score_inputs"), Mapping) else {}
    controls = inputs.get("configuration_controls")
    controls = controls if isinstance(controls, Mapping) else {}
    operational = section.get("operational_health")
    operational = operational if isinstance(operational, Mapping) else {}
    taxonomy = operational.get("outcome_taxonomy")
    taxonomy = taxonomy if isinstance(taxonomy, Mapping) else {}
    score = section.get("presented_score", section.get("score"))
    score_label = f"{_int(score)}/100" if isinstance(score, (int, float)) else "Not scored"
    return [
        (
            "A. CI/CD configuration maturity: "
            f"{score_label}; exact-SHA match={contract.get('exact_configuration_match') is True}; "
            f"explicit permissions={inputs.get('explicit_permissions_present') is True}; "
            f"immutable controls={sum(value is True for value in controls.values())}/{len(controls)}."
        ),
        (
            "B. Current operational readiness: not established by repository evidence alone; "
            "exact deployed frontend/backend commit proof and current production acceptance must be attached."
        ),
        (
            "C. Required-check health: not treated as passed unless exact required-check records "
            "for the assessed or release commit are attached."
        ),
        (
            "D. Historical workflow outcomes (unscored context): "
            f"success={_int(taxonomy.get('success'))}, failure={_int(taxonomy.get('failure'))}, "
            f"cancelled={_int(taxonomy.get('cancelled'))}, skipped={_int(taxonomy.get('skipped'))}, "
            f"timed_out={_int(taxonomy.get('timed_out'))}, unknown={_int(taxonomy.get('unknown'))}, "
            f"observed={_int(operational.get('workflow_run_count', operational.get('observed_run_count')))}."
        ),
    ]


def _sync_stages(canonical: dict[str, Any]) -> None:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    coverage = canonical.get("scanner_execution_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    completed = _int(
        coverage.get("completed_applicable_scanners", canonical.get("completed_applicable_analyzers"))
    )
    applicable = _int(coverage.get("applicable_scanners")) or completed
    incomplete = _int(
        coverage.get("incomplete_applicable_scanners", canonical.get("incomplete_applicable_analyzers"))
    )
    stages = _records(canonical.get("stage_summaries"))
    ci_lines = _ci_lines(canonical)
    for stage in stages:
        stage_id = _text(stage.get("stage_id"), 100)
        if stage_id == "client_evidence_summary":
            stage["evidence"] = _client_summary_evidence(
                canonical, stage.get("evidence")
            )
        elif stage_id.startswith("client_human_evidence_"):
            stage["evidence"] = _clean_client_literal_evidence(
                stage.get("evidence")
            )
        else:
            stage["evidence"] = _clean_evidence(stage.get("evidence"))
        if stage_id == "dependency_security_static_analysis":
            stage["summary"] = (
                f"{completed} of {applicable} applicable analyzers completed; {incomplete} are incomplete. "
                f"Candidate triage is separate: {_int(totals.get('review_required'))} review-required "
                f"candidates and {_int(totals.get('material'))} confirmed material findings are retained."
            )
        elif stage_id in {
            "ci_cd_architecture_complexity_velocity",
            "ci_cd_operational_readiness",
        }:
            stage["summary"] = (
                "CI/CD configuration maturity, current operational readiness, required-check health, "
                "and historical workflow outcomes are separate evidence concepts."
            )
            stage["evidence"] = list(ci_lines)
    canonical["stage_summaries"] = stages


def _sync_executive(canonical: dict[str, Any]) -> None:
    from nico import comprehensive_client_review_companion_v5 as companion

    assessment = _dict(canonical.get("assessment"))
    maturity = _dict(assessment.get("maturity_signal"))
    readiness = canonical.get("client_readiness_contract")
    readiness = readiness if isinstance(readiness, Mapping) else {}
    label = _text(readiness.get("maturity_label") or maturity.get("level") or "Pending", 80)
    technical = assessment.get(
        "technical_score",
        maturity.get("technical_score", maturity.get("presented_score", maturity.get("score"))),
    )
    score_text = f"{_int(technical)}/100" if isinstance(technical, (int, float)) else "not scored"
    maturity.update({"level": label, "presented_score": technical})
    assessment["maturity_signal"] = maturity

    section_ids = (
        "functional_qa",
        "platform_parity",
        "historical_trends_and_change_failure",
        "requirements_traceability",
        "stakeholder_and_business_alignment",
        "risk_reduction_and_executive_briefing",
        "six_month_roadmap",
        "staffing_sequencing_and_cost",
    )
    markers = ("not assessed", "limited", "framework only", "pending stakeholder validation")
    statuses = {
        section_id: _text(companion._base_section_details(section_id, spanish=False).get("status"))
        for section_id in section_ids
    }
    limited = [
        section_id
        for section_id, status in statuses.items()
        if any(marker in status.casefold() for marker in markers)
    ]
    stages = _records(canonical.get("stage_summaries"))
    terminal = [
        _text(stage.get("title") or stage.get("stage_id"), 180)
        for stage in stages
        if _text(stage.get("status"), 80).casefold()
        in {"blocked", "failed", "unavailable", "timed_out"}
    ]
    boundary = (
        f"{len(terminal)} stage(s) remain terminally blocked: {', '.join(terminal[:4])}."
        if terminal
        else "Every automated stage represented in this package completed without a terminal execution failure."
    )
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    summary = (
        "NICO completed a native Comprehensive Technical Assessment for "
        f"{_text(identity.get('repository'), 300)} at immutable commit "
        f"{_text(identity.get('commit_sha'), 120)}. The evidence-bound maturity signal is "
        f"{label} ({score_text}). {len(limited)} client-review section(s) disclose unavailable, "
        f"limited, or stakeholder-dependent evidence. {boundary} The package is a review-gated "
        "automated draft: automated evidence and recommendations are not client approval or delivery authorization."
    )
    assessment.update(
        {
            "executive_summary": summary,
            "limited_review_section_count": len(limited),
            "limited_review_section_ids": limited,
            "review_section_statuses": statuses,
        }
    )
    canonical["assessment"] = assessment
    canonical["executive_summary"] = summary
    for key in ("maturity_label_truth", "post_readiness_maturity_truth"):
        truth = _dict(canonical.get(key))
        truth.update(
            {
                "canonical_label": label,
                "canonical_source": "client_readiness_contract.maturity_label",
                "stale_label_reconciled_before_render": True,
            }
        )
        canonical[key] = truth


def normalize_client_truth(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(canonical))
    _sync_scanner_sections(output)
    _sync_stages(output)
    _sync_executive(output)
    contract = _dict(output.get("v2_prepublication_contract"))
    contract.update(
        {
            "comprehensive_client_truth_final_version": VERSION,
            "candidate_disposition_arithmetic_verified": True,
            "candidate_evidence_quality_arithmetic_verified": True,
            "scanner_sections_rebuilt_from_canonical_register": True,
            "blank_client_fields_removed": True,
            "limited_review_count_recomputed": True,
            "maturity_label_reconciled": True,
            "ci_cd_four_part_presentation": True,
            "generated_at_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["v2_prepublication_contract"] = contract
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def _replace_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        replacement = _COVER_TEXT.get(str(value))
        return (TextStringObject(replacement), True) if replacement else (value, False)
    if isinstance(value, ByteStringObject):
        try:
            decoded = bytes(value).decode("latin-1")
        except Exception:
            return value, False
        replacement = _COVER_TEXT.get(decoded)
        if replacement:
            return ByteStringObject(replacement.encode("latin-1", errors="replace")), True
    return value, False


def replace_cover_text(pdf: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], replaced = _replace_operand(operands[0])
                changed = changed or replaced
            elif operator == b"TJ" and operands:
                for index, item in enumerate(operands[0]):
                    operands[0][index], replaced = _replace_operand(item)
                    changed = changed or replaced
            elif operator in {b"'", b'"'} and operands:
                operands[-1], replaced = _replace_operand(operands[-1])
                changed = changed or replaced
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _report_language(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    value = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return "es-MX" if value.startswith("es") else "en"


def _ci_boundary_markers(canonical: Mapping[str, Any]) -> tuple[str, ...]:
    if _report_language(canonical) == "es-MX":
        return (
            "A. Madurez de configuración de CI/CD:",
            "B. Preparación operativa actual:",
            "C. Estado de las verificaciones requeridas:",
            "D. Resultados históricos de los flujos de trabajo",
        )
    return (
        "A. CI/CD configuration maturity:",
        "B. Current operational readiness:",
        "C. Required-check health:",
        "D. Historical workflow outcomes",
    )


def _validate_surfaces(result: Mapping[str, Any]) -> None:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    if register:
        _validate_register(register)
    markdown = str(result.get("markdown") or "")
    rendered_html = str(result.get("html") or "")
    try:
        pdf = base64.b64decode(str(result.get("pdf_base64") or ""), validate=True)
        extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    except Exception as exc:
        raise ValueError("Comprehensive client package has no valid PDF") from exc
    combined = "\n".join((markdown, rendered_html, extracted))
    forbidden = (
        "Platform Parity: Complete",
        "remain incomplete or review-limited",
        "Decision-Grade Technical Assessment",
        "candidate_disposition.count_only:\n",
        "candidate_disposition.confirmed_material:\n",
        "source_loc:\n",
        "human_evidence_partial_count:\n",
        "human_evidence_complete_count:\n",
        "business_objectives_attached:\n",
        "directly_verified_requirement_count:\n",
    )
    retained = [marker for marker in forbidden if marker in combined]
    if retained:
        raise ValueError("client report retained contradictory or blank markers: " + ", ".join(retained))
    generated = _generated_at(result)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    if not generated or _text(identity.get("generated_at")) != generated:
        raise ValueError("canonical generated_at does not match rendered surfaces")
    summary = _text(assessment.get("executive_summary"), 5000)
    if summary not in combined:
        raise ValueError("canonical executive summary is not rendered consistently")
    for marker in _ci_boundary_markers(canonical):
        if marker not in combined:
            raise ValueError(f"client report omitted CI/CD boundary: {marker}")


def install_comprehensive_client_truth_final_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5
    from nico import v2_dark_branded_cover as cover

    current_sections = v5.substantive_review_sections
    if not getattr(current_sections, _MARKER, False):

        @wraps(current_sections)
        def substantive_review_sections(
            canonical: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> list[dict[str, Any]]:
            sections = current_sections(normalize_client_truth(canonical), spanish=spanish)
            for section in sections:
                section["evidence"] = _clean_evidence(section.get("evidence"))
                if _text(section.get("id")) == "platform_parity":
                    section["status"] = (
                        "Indicadores del repositorio revisados; paridad de ejecución no evaluada"
                        if spanish
                        else "Repository indicator review complete; runtime platform parity not assessed"
                    )
            return sections

        setattr(substantive_review_sections, _MARKER, True)
        setattr(substantive_review_sections, "_nico_previous", current_sections)
        v5.substantive_review_sections = substantive_review_sections
        for module in (v2, v3, v4):
            module.review_sections = substantive_review_sections

    current_cover = cover._cover
    if not getattr(current_cover, _COVER_MARKER, False):

        @wraps(current_cover)
        def _cover(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
            return replace_cover_text(current_cover(normalize_client_truth(canonical), spanish=spanish))

        setattr(_cover, _COVER_MARKER, True)
        setattr(_cover, "_nico_previous", current_cover)
        cover._cover = _cover

    current_prepare = completion.prepare_client_report_package
    if not getattr(current_prepare, _PREPARE_MARKER, False):

        @wraps(current_prepare)
        def prepare_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
            result = current_prepare(package)
            canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
            normalized = normalize_client_truth(canonical)
            _set_generated_at(normalized, _generated_at(result) or _generated_at(package))
            result["json"] = normalized
            return result

        setattr(prepare_client_report_package, _PREPARE_MARKER, True)
        setattr(prepare_client_report_package, "_nico_previous", current_prepare)
        completion.prepare_client_report_package = prepare_client_report_package

    current_finalize = completion.finalize_client_report_package
    if not getattr(current_finalize, _MARKER, False):

        @wraps(current_finalize)
        def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
            result = current_finalize(package)
            generated = _generated_at(result) or _generated_at(package)
            if not generated:
                raise ValueError("Comprehensive review package is missing generated_at")
            canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
            normalized = normalize_client_truth(canonical)
            _set_generated_at(normalized, generated)
            result.update(
                {
                    "json": normalized,
                    "generated_at": generated,
                    "generation_timestamp": generated,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            _validate_surfaces(result)
            return result

        setattr(finalize_client_report_package, _MARKER, True)
        setattr(finalize_client_report_package, "_nico_previous", current_finalize)
        completion.finalize_client_report_package = finalize_client_report_package

    return {
        "status": "installed",
        "version": VERSION,
        "candidate_arithmetic_verified": True,
        "canonical_generated_at_required": True,
        "blank_client_fields_removed": True,
        "limited_review_count_recomputed": True,
        "platform_parity_language_bounded": True,
        "scanner_execution_and_triage_separated": True,
        "ci_cd_four_part_presentation": True,
        "ci_cd_boundary_validation_language_aware": True,
        "decision_grade_claim_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_truth_final_v1",
    "normalize_client_truth",
    "replace_cover_text",
]
