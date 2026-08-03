from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_artifact_truth.v53.2"
_MARKER = "_nico_comprehensive_final_artifact_truth_v53"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _strict_truth_package(canonical: dict[str, Any]) -> bool:
    assessment = _dict(canonical.get("assessment"))
    contract = _dict(assessment.get("score_contract"))
    return bool(
        canonical.get("pre_render_truth_reconciliation") is True
        or assessment.get("pre_render_truth_reconciliation") is True
        or isinstance(assessment.get("score_reconciliation"), dict)
        or contract.get("canonical_finding_register_required") is True
        or isinstance(assessment.get("canonical_scanner_finding_register"), dict)
    )


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
        return not _strict_truth_package(canonical)
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
    metrics_source = {"findings_register": register} if register else canonical
    _, _, calculated = _finding_metrics(metrics_source)
    stated_values = {
        int(value)
        for value in _walk_key_values(canonical, "unique_finding_count")
        if isinstance(value, int) and not isinstance(value, bool)
    }
    stated_matches = not stated_values or stated_values == {calculated}
    return no_duplicates, stated_matches, calculated


def _canonical_scanner_register_truth(canonical: dict[str, Any]) -> dict[str, bool]:
    assessment = _dict(canonical.get("assessment"))
    contract = _dict(assessment.get("score_contract"))
    register = _dict(assessment.get("canonical_scanner_finding_register"))
    required = contract.get("canonical_finding_register_required") is True or bool(register)
    check_names = (
        "canonical_scanner_register_present",
        "canonical_scanner_register_complete",
        "canonical_scanner_count_parity_verified",
        "canonical_scanner_totals_recompute",
        "canonical_scanner_digest_recomputes",
        "canonical_scanner_commit_matches_report",
        "canonical_scanner_ids_are_unique",
        "canonical_scanner_payload_retention_truthful",
        "canonical_scanner_summary_matches_assessment",
        "canonical_scanner_coverage_reference_matches",
        "evidence_adjusted_penalty_recomputes",
        "candidate_volume_does_not_change_technical_score",
        "ci_configuration_and_operational_health_separated",
    )
    if not required:
        return {name: True for name in check_names}

    findings = [item for item in _list(register.get("findings")) if isinstance(item, dict)]
    totals = _dict(register.get("totals"))
    calculated = {
        "raw": 0,
        "material": 0,
        "review_required": 0,
        "approved_or_nonblocking": 0,
        "excluded_test_only": 0,
        "exact_source": 0,
        "source_path": 0,
        "payload_without_source": 0,
        "count_only": 0,
    }
    disposition_keys = {
        "verified_material": "material",
        "review_required": "review_required",
        "approved_or_nonblocking": "approved_or_nonblocking",
        "excluded_test_only": "excluded_test_only",
    }
    records_valid = True
    for finding in findings:
        count = _nonnegative_int(finding.get("occurrence_count"))
        disposition = str(finding.get("disposition") or "")
        quality = str(finding.get("evidence_quality") or "")
        if count <= 0 or disposition not in disposition_keys or quality not in calculated:
            records_valid = False
            continue
        calculated["raw"] += count
        calculated[disposition_keys[disposition]] += count
        calculated[quality] += count

    totals_match = records_valid and all(
        _nonnegative_int(totals.get(key)) == value
        for key, value in calculated.items()
    )
    digest = hashlib.sha256(
        json.dumps(findings, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    identity = _dict(canonical.get("identity"))
    report_commit = str(
        identity.get("commit_sha")
        or assessment.get("commit_sha")
        or ""
    ).strip().casefold()
    register_commit = str(register.get("exact_commit_sha") or "").strip().casefold()
    record_commits = {
        str(item.get("exact_commit_sha") or "").strip().casefold()
        for item in findings
    }
    commit_matches = bool(report_commit and register_commit == report_commit) and (
        not record_commits or record_commits == {report_commit}
    )
    finding_ids = [str(item.get("finding_id") or "") for item in findings]
    fingerprints = [str(item.get("raw_fingerprint") or "") for item in findings]
    ids_unique = (
        all(finding_ids)
        and len(finding_ids) == len(set(finding_ids))
        and all(fingerprints)
        and len(fingerprints) == len(set(fingerprints))
    ) if findings else calculated["raw"] == 0
    retention_truth = (
        register.get("raw_payload_retention_complete") is (calculated["count_only"] == 0)
    )
    summary_matches = assessment.get("scanner_finding_summary") == register.get("summary_by_category")
    coverage = _dict(assessment.get("evidence_coverage"))
    coverage_matches = (
        _nonnegative_int(coverage.get("canonical_finding_count")) == calculated["raw"]
        and str(coverage.get("canonical_finding_digest_sha256") or "") == digest
        and coverage.get("canonical_finding_register_status") == register.get("status")
    )

    technical, adjusted = _score_truth(canonical)
    volume_penalty = _nonnegative_int(contract.get("candidate_volume_penalty"))
    payload_penalty = _nonnegative_int(contract.get("missing_raw_payload_penalty"))
    execution_penalty = _nonnegative_int(contract.get("incomplete_analyzer_penalty"))
    assurance_penalty = min(30, volume_penalty + payload_penalty + execution_penalty)
    expected_adjusted = None if technical is None else max(0, technical - assurance_penalty)
    penalty_recomputes = (
        technical is not None
        and adjusted == expected_adjusted
        and _score(contract.get("technical_score")) == technical
        and _score(contract.get("evidence_adjusted_score")) == adjusted
        and _nonnegative_int(contract.get("assurance_penalty")) == assurance_penalty
    )
    candidate_flags = (
        contract.get("candidate_volume_affects_technical_score") is False
        and contract.get("candidate_volume_affects_evidence_adjusted_score") is True
        and coverage.get("candidate_volume_affects_technical_score") is False
        and coverage.get("candidate_volume_affects_evidence_adjusted_score") is True
    )

    operational = _dict(assessment.get("ci_cd_operational_health"))
    ci_section = next(
        (
            item
            for item in _list(assessment.get("sections"))
            if isinstance(item, dict) and item.get("id") == "ci_cd"
        ),
        {},
    )
    section_operational = _dict(ci_section.get("operational_health"))
    ci_separated = bool(ci_section and operational) and (
        ci_section.get("configuration_maturity_score") == ci_section.get("presented_score")
        and section_operational == operational
        and operational.get("score_effect") == "operational_context_only"
        and operational.get("technical_configuration_score_affected") is False
    )

    return {
        "canonical_scanner_register_present": bool(register),
        "canonical_scanner_register_complete": register.get("status") == "complete",
        "canonical_scanner_count_parity_verified": (
            register.get("count_parity_verified") is True
            and not _list(register.get("discrepancies"))
            and contract.get("canonical_finding_count_parity_verified") is True
        ),
        "canonical_scanner_totals_recompute": totals_match,
        "canonical_scanner_digest_recomputes": str(register.get("canonical_digest_sha256") or "") == digest,
        "canonical_scanner_commit_matches_report": commit_matches,
        "canonical_scanner_ids_are_unique": ids_unique,
        "canonical_scanner_payload_retention_truthful": retention_truth,
        "canonical_scanner_summary_matches_assessment": summary_matches,
        "canonical_scanner_coverage_reference_matches": coverage_matches,
        "evidence_adjusted_penalty_recomputes": penalty_recomputes,
        "candidate_volume_does_not_change_technical_score": candidate_flags,
        "ci_configuration_and_operational_health_separated": ci_separated,
    }


def _automated_delivery_boundary(package: dict[str, Any], canonical: dict[str, Any]) -> bool:
    assessment = _dict(canonical.get("assessment"))
    containers = (package, canonical, assessment)
    review_values = [
        container.get("human_review_required")
        for container in containers
        if "human_review_required" in container
    ]
    delivery_values = [
        container.get("client_delivery_allowed")
        for container in containers
        if "client_delivery_allowed" in container
    ]
    if not review_values and not delivery_values:
        return True
    return (
        bool(review_values)
        and bool(delivery_values)
        and all(value is True for value in review_values)
        and all(value is False for value in delivery_values)
    )


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
    scanner_register_checks = _canonical_scanner_register_truth(canonical)

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
        "automated_package_remains_human_review_gated": _automated_delivery_boundary(package, canonical),
        "markdown_identifier_integrity": _identifier_integrity(markdown),
        "html_identifier_integrity": _identifier_integrity(html_text),
        "pdf_identifier_integrity": _identifier_integrity(pdf_text),
        **scanner_register_checks,
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
        "canonical_scanner_register_required_when_scoring_requires_it": True,
        "canonical_scanner_count_parity_required": True,
        "canonical_scanner_digest_required": True,
        "evidence_adjusted_penalty_recalculation_required": True,
        "ci_configuration_operational_separation_required": True,
        "automated_delivery_boundary_required": True,
        "finding_deduplication_required": True,
        "identifier_integrity_required": True,
        "legacy_packages_without_modern_truth_contract_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_artifact_truth_v53",
    "validate_final_report_package",
]
