from __future__ import annotations

import base64
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth.v53"
_MARKER = "_nico_comprehensive_final_artifact_truth_v53"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pdf_text(pdf: bytes) -> str:
    if not pdf.startswith(b"%PDF"):
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf))
        text = " ".join((page.extract_text() or "") for page in reader.pages)
        return " ".join(text.split())[:1_500_000]
    except Exception:
        return ""


def _html_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def _decode_pdf(package: dict[str, Any]) -> bytes:
    encoded = str(package.get("pdf_base64") or "")
    try:
        return base64.b64decode(encoded, validate=True) if encoded else b""
    except Exception:
        return b""


def _walk_key_values(node: Any, key_name: str) -> list[Any]:
    output: list[Any] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) == key_name:
                output.append(value)
            output.extend(_walk_key_values(value, key_name))
    elif isinstance(node, list):
        for value in node:
            output.extend(_walk_key_values(value, key_name))
    return output


def _score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _score_truth(canonical: dict[str, Any]) -> tuple[int | None, int | None]:
    assessment = _dict(canonical.get("assessment"))
    maturity = _dict(assessment.get("maturity_signal"))
    technical = next(
        (
            score
            for raw in (
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("score"),
            )
            if (score := _score(raw)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for raw in (
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
            )
            if (score := _score(raw)) is not None
        ),
        None,
    )
    return technical, adjusted


def _score_aliases_consistent(canonical: dict[str, Any]) -> bool:
    technical, adjusted = _score_truth(canonical)
    if technical is None or adjusted is None:
        return False
    assessment = _dict(canonical.get("assessment"))
    maturity = _dict(assessment.get("maturity_signal"))
    technical_values = [
        _score(value)
        for value in (
            assessment.get("technical_score"),
            maturity.get("technical_score"),
            maturity.get("score"),
            maturity.get("source_score"),
        )
        if _score(value) is not None
    ]
    adjusted_values = [
        _score(value)
        for value in (
            assessment.get("canonical_evidence_adjusted_score"),
            assessment.get("evidence_adjusted_score"),
            maturity.get("canonical_evidence_adjusted_score"),
            maturity.get("evidence_adjusted_score"),
        )
        if _score(value) is not None
    ]
    return bool(technical_values and adjusted_values) and all(
        value == technical for value in technical_values
    ) and all(value == adjusted for value in adjusted_values)


def _score_stage_consistent(canonical: dict[str, Any]) -> bool:
    technical, adjusted = _score_truth(canonical)
    if technical is None or adjusted is None:
        return False
    serialized = json.dumps(canonical.get("stage_summaries") or [], default=str)
    technical_values = {
        int(match.group(1))
        for match in re.finditer(
            r"(?:canonical_)?technical_score[^0-9]{0,20}(\d{1,3})", serialized, re.I
        )
    }
    adjusted_values = {
        int(match.group(1))
        for match in re.finditer(
            r"(?:canonical_)?evidence_adjusted_score[^0-9]{0,20}(\d{1,3})",
            serialized,
            re.I,
        )
    }
    return (not technical_values or technical_values == {technical}) and (
        not adjusted_values or adjusted_values == {adjusted}
    )


def _weighted_scores_recompute(canonical: dict[str, Any]) -> bool:
    assessment = _dict(canonical.get("assessment"))
    reconciliation = _dict(assessment.get("score_reconciliation"))
    source_rows = reconciliation.get("rows") or assessment.get("scoring_weights")
    rows = [row for row in _list(source_rows) if isinstance(row, dict)]
    included = [
        row
        for row in rows
        if row.get("included") is True and _score(row.get("technical_score")) is not None
    ]
    if not included:
        return False
    denominator = sum(float(row.get("weight") or 0.0) for row in included)
    if denominator <= 0:
        return False
    technical = round(
        sum(_score(row.get("technical_score")) * float(row.get("weight") or 0.0) for row in included)
        / denominator
    )
    adjusted = round(
        sum(
            _score(row.get("technical_score"))
            * float(row.get("assurance_factor") or 1.0)
            * float(row.get("weight") or 0.0)
            for row in included
        )
        / denominator
    )
    canonical_technical, canonical_adjusted = _score_truth(canonical)
    return technical == canonical_technical and adjusted == canonical_adjusted


def _scanner_consistency(canonical: dict[str, Any]) -> tuple[bool, bool, bool]:
    from nico.comprehensive_report_truth_v53 import authoritative_completed_scanners

    completed = authoritative_completed_scanners(canonical)
    incomplete_values: set[str] = set()
    for value in _walk_key_values(canonical, "incomplete_analyzers"):
        if isinstance(value, list):
            incomplete_values.update(str(item).strip().casefold() for item in value)
    stale = completed.intersection(incomplete_values)

    coverage_values = {
        int(value)
        for value in _walk_key_values(canonical, "analyzer_execution_coverage")
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    coverage_consistent = len(coverage_values) <= 1
    coverage_complete_when_all_complete = (
        not completed or bool(incomplete_values) or coverage_values == {100}
    )
    return not stale, coverage_consistent, coverage_complete_when_all_complete


def _finding_identity(item: Any) -> tuple[Any, ...] | None:
    from nico import comprehensive_report_truth_stabilization_v52 as legacy

    if not isinstance(item, dict) or not legacy._is_finding(item):
        return None
    identity = legacy._source_identity(item)
    return identity if identity and identity[0] and identity[1] else None


def _finding_consistency(canonical: dict[str, Any]) -> tuple[bool, bool, int]:
    from nico.comprehensive_report_truth_stabilization_v52 import _finding_metrics

    register = canonical.get("findings_register")
    if not isinstance(register, list):
        register = _dict(canonical.get("assessment")).get("decision_grade_findings_register")
    register = register if isinstance(register, list) else []
    identities = [identity for item in register if (identity := _finding_identity(item))]
    no_duplicates = len(identities) == len(set(identities))
    _, _, calculated = _finding_metrics(canonical)
    stated_values = {
        int(value)
        for value in _walk_key_values(canonical, "unique_finding_count")
        if isinstance(value, int) and not isinstance(value, bool)
    }
    stated_matches = not stated_values or stated_values == {calculated}
    return no_duplicates, stated_matches, calculated


def _identifier_integrity(*texts: str) -> bool:
    from nico.comprehensive_report_truth_stabilization_v52 import _repair_text

    return all(_repair_text(text) == text for text in texts)


def validate_final_report_package(package: dict[str, Any]) -> dict[str, Any]:
    canonical = _dict(package.get("json"))
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    pdf = _decode_pdf(package)
    pdf_text = _pdf_text(pdf)
    html_text = _html_text(rendered_html)
    scanner_state, coverage_consistent, coverage_complete = _scanner_consistency(canonical)
    no_duplicates, finding_count_matches, finding_count = _finding_consistency(canonical)

    checks = {
        "canonical_json_present": bool(canonical),
        "pdf_full_text_available": bool(pdf_text),
        "score_aliases_consistent": _score_aliases_consistent(canonical),
        "stage_score_evidence_matches_canonical": _score_stage_consistent(canonical),
        "weighted_scores_recompute": _weighted_scores_recompute(canonical),
        "completed_scanners_not_incomplete": scanner_state,
        "analyzer_coverage_values_consistent": coverage_consistent,
        "all_completed_analyzers_report_full_coverage": coverage_complete,
        "finding_register_has_no_equivalent_duplicates": no_duplicates,
        "stated_unique_finding_count_matches_register": finding_count_matches,
        "markdown_identifier_integrity": _identifier_integrity(markdown),
        "html_identifier_integrity": _identifier_integrity(html_text),
        "pdf_identifier_integrity": _identifier_integrity(pdf_text),
    }
    failed = sorted(key for key, value in checks.items() if value is not True)
    return {
        "status": "verified" if not failed else "blocked",
        "version": VERSION,
        "checks": checks,
        "failed_checks": failed,
        "calculated_unique_finding_count": finding_count,
        "full_pdf_page_text_validated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_final_artifact_truth_v53() -> dict[str, Any]:
    from nico import comprehensive_cross_format_finality_v49 as cross_format
    from nico import comprehensive_native_providers as providers

    current: Callable[[dict[str, Any]], dict[str, Any]] = (
        cross_format.finality_aware_cross_format_verification_provider
    )
    if getattr(current, _MARKER, False):
        providers.cross_format_verification_provider = current
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def verify(context: dict[str, Any]) -> dict[str, Any]:
        base = current(context)
        final_stage = providers._prior(context, "final_comprehensive_report_generation")
        package, source = cross_format._report_package(final_stage)
        validation = validate_final_report_package(package)
        if str(base.get("status") or "").casefold() in {
            "blocked",
            "failed",
            "error",
            "unavailable",
            "timed_out",
        }:
            output = deepcopy(base)
            output["final_artifact_truth"] = validation
            output["report_package_source"] = source
            return output
        if validation["status"] != "verified":
            return providers._result(
                context,
                "blocked",
                reason="final_artifact_truth_verification_failed",
                report_package_source=source,
                final_artifact_truth=validation,
                failed_checks=validation["failed_checks"],
            )
        output = deepcopy(base)
        output["final_artifact_truth"] = validation
        output["report_package_source"] = source
        evidence = _dict(output.get("evidence"))
        evidence.update(validation["checks"])
        evidence["calculated_unique_finding_count"] = validation[
            "calculated_unique_finding_count"
        ]
        output["evidence"] = evidence
        return output

    setattr(verify, _MARKER, True)
    setattr(verify, "_nico_previous", current)
    cross_format.finality_aware_cross_format_verification_provider = verify
    providers.cross_format_verification_provider = verify
    return {
        "status": "installed",
        "version": VERSION,
        "bound": (
            cross_format.finality_aware_cross_format_verification_provider is verify
            and providers.cross_format_verification_provider is verify
        ),
        "full_pdf_text_validated": True,
        "weighted_score_recalculation_required": True,
        "scanner_state_consistency_required": True,
        "finding_deduplication_required": True,
        "identifier_integrity_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_artifact_truth_v53",
    "validate_final_report_package",
]
