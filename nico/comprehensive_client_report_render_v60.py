from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader

from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth,
)
from nico.comprehensive_report_coverage_synchronization_v63 import (
    synchronize_final_report_coverage,
)

VERSION = "nico.comprehensive_client_report_render.v63"
_PREPARE_MARKER = "_nico_comprehensive_client_report_prepare_v60"
_FINALIZE_MARKER = "_nico_comprehensive_client_report_finalize_v60"
_PROJECT_MARKER = "_nico_comprehensive_client_report_project_v62"

_DIAGNOSTIC_KEYS = {
    "report_contract_status",
    "report_contract_reason",
    "core_report_contract_status",
    "core_report_contract_reason",
}
_SUPERSEDED_STATUS_VALUES = {"blocked", "failed", "invalid"}
_SUPERSEDED_REASON_VALUES = {
    "executive_decision_brief_page_gate_failed",
    "canonical_score_truth_mismatch",
    "canonical_evidence_adjusted_score_mismatch",
}
_BROKEN_IDENTIFIERS = (
    "appy_ l scanner_artifact_scoring",
    "span ish_pdf",
    "span ish_markdown",
    "co llect_complexity_evidence",
    "co llect_snapshot_repository_evidence",
    "eva luate_report_payload",
    "mar kdown_report",
    "reso lve_repository_commit",
    "install_comprehensive_on_production_ app",
)
_COVERAGE_PATTERNS = (
    re.compile(
        r"analy[sz]er execution coverage\s*(?:is|[:=])\s*(\d{1,3})\s*%?",
        re.I,
    ),
    re.compile(r"analyzer_execution_coverage\s*:\s*(\d{1,3})", re.I),
    re.compile(r"scanner_execution_coverage\s*:\s*(\d{1,3})", re.I),
)
_DESIGN_MARKERS = (
    "NICO COMPREHENSIVE",
    "Canonical Technical Scorecard",
    "Evidence Appendix",
    "Human Review and Acceptance Gate",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _superseded_diagnostic(key: str, value: Any) -> bool:
    normalized_key = key.casefold()
    normalized_value = _text(value).casefold()
    if normalized_key.endswith("status"):
        return normalized_value in _SUPERSEDED_STATUS_VALUES
    if normalized_key.endswith("reason"):
        return normalized_value in _SUPERSEDED_REASON_VALUES
    return False


def _extract_internal_diagnostics(
    node: Any,
    *,
    path: str = "json",
) -> tuple[Any, list[dict[str, Any]]]:
    """Move superseded pre-finalization diagnostics outside current report truth."""

    audit: list[dict[str, Any]] = []
    if isinstance(node, list):
        cleaned: list[Any] = []
        for index, item in enumerate(node):
            value, entries = _extract_internal_diagnostics(
                item,
                path=f"{path}[{index}]",
            )
            cleaned.append(value)
            audit.extend(entries)
        return cleaned, audit
    if not isinstance(node, Mapping):
        return deepcopy(node), audit

    cleaned_map: dict[str, Any] = {}
    for raw_key, raw_value in node.items():
        key = str(raw_key)
        if key.casefold() in _DIAGNOSTIC_KEYS and _superseded_diagnostic(key, raw_value):
            audit.append(
                {
                    "path": path,
                    "key": key,
                    "value": deepcopy(raw_value),
                    "classification": "superseded_pre_finalization_diagnostic",
                }
            )
            continue
        value, entries = _extract_internal_diagnostics(
            raw_value,
            path=f"{path}.{key}",
        )
        cleaned_map[key] = value
        audit.extend(entries)
    return cleaned_map, audit


def reconcile_before_existing_report_renderer(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Correct exact-run truth without replacing any rendered report surface."""

    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    reconciled = reconcile_authoritative_scanner_truth(canonical)
    client_truth, audit = _extract_internal_diagnostics(reconciled)
    result["json"] = client_truth
    if audit:
        existing_audit = (
            result.get("pre_finalization_audit")
            if isinstance(result.get("pre_finalization_audit"), Mapping)
            else {}
        )
        entries = [
            item
            for item in existing_audit.get("entries") or []
            if isinstance(item, Mapping)
        ]
        entries.extend(audit)
        unique_entries: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in entries:
            key = (
                _text(item.get("path")),
                _text(item.get("key")),
                _text(item.get("value")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_entries.append(deepcopy(dict(item)))
        result["pre_finalization_audit"] = {
            "version": VERSION,
            "entries": unique_entries,
            "retained_outside_client_facing_canonical_truth": True,
        }
    contract = deepcopy(dict(result.get("report_design_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "existing_renderer_preserved": True,
            "existing_visual_design_preserved": True,
            "existing_section_order_preserved": True,
            "existing_pdf_composition_preserved": True,
            "canonical_truth_reconciled_before_existing_renderer": True,
            "redesign_performed": False,
        }
    )
    result["report_design_contract"] = contract
    return result


def _expected_truth(package: Mapping[str, Any]) -> tuple[int, int, str, int]:
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    contract = (
        canonical.get("client_readiness_contract")
        if isinstance(canonical.get("client_readiness_contract"), Mapping)
        else {}
    )
    coverage = int(
        contract.get(
            "analyzer_execution_coverage",
            canonical.get("analyzer_execution_coverage", 0),
        )
        or 0
    )
    incomplete = int(canonical.get("incomplete_applicable_analyzers", 0) or 0)
    maturity = _text(contract.get("maturity_label"))
    denominator = int(contract.get("coverage_denominator", 0) or 0)
    return coverage, incomplete, maturity, denominator


def _coverage_values(text: str) -> set[int]:
    values: set[int] = set()
    for pattern in _COVERAGE_PATTERNS:
        values.update(int(match.group(1)) for match in pattern.finditer(text))
    return values


def validate_existing_report_accuracy(package: Mapping[str, Any]) -> dict[str, Any]:
    """Use the existing generated PDF as the final accuracy acceptance artifact."""

    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""))
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise ValueError("client report did not retain a decodable PDF") from exc
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report did not retain a valid final PDF")

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    combined = "\n".join((markdown, rendered_html, extracted))
    coverage, incomplete, maturity, denominator = _expected_truth(package)
    scanner_backed_report = denominator >= 9

    observed_coverage = _coverage_values(combined)
    if observed_coverage and observed_coverage != {coverage}:
        raise ValueError(
            "client report retained conflicting analyzer coverage values: "
            f"expected {coverage}, observed {sorted(observed_coverage)}"
        )
    if scanner_backed_report and not observed_coverage:
        raise ValueError("client report omitted analyzer execution coverage")

    if scanner_backed_report and incomplete == 0:
        if re.search(r"incomplete_analyzers\[\d+\]", combined, re.I):
            raise ValueError("client report listed completed analyzers as incomplete")
        if "Incomplete applicable analyzers: 0" not in combined:
            raise ValueError("client report omitted the canonical incomplete analyzer count")

    if scanner_backed_report and maturity:
        stale_labels = {
            "Exceptional": ("maturity_level: Senior",),
            "Strong": ("maturity_level: Senior", "Maturity Exceptional"),
        }
        for stale in stale_labels.get(maturity, ()):
            if stale.casefold() in combined.casefold():
                raise ValueError(
                    f"client report retained a maturity label conflicting with {maturity}: {stale}"
                )

    for stale in (
        "report_contract_status: blocked",
        "executive_decision_brief_page_gate_failed",
    ):
        if stale.casefold() in combined.casefold():
            raise ValueError(
                f"client report exposed a superseded pre-finalization diagnostic: {stale}"
            )
    for broken in _BROKEN_IDENTIFIERS:
        if broken.casefold() in combined.casefold():
            raise ValueError(f"client report retained malformed identifier: {broken}")

    if scanner_backed_report:
        missing_design = [
            marker for marker in _DESIGN_MARKERS if marker.casefold() not in combined.casefold()
        ]
        if missing_design:
            raise ValueError(
                "approved NICO report design markers were not preserved: "
                + ", ".join(missing_design)
            )

    coverage_sync = (
        package.get("coverage_synchronization")
        if isinstance(package.get("coverage_synchronization"), Mapping)
        else {}
    )
    coverage_sync_applied = bool(coverage_sync)
    coverage_sync_matches = (
        not coverage_sync_applied
        or int(coverage_sync.get("canonical_coverage_value", -1)) == coverage
    )
    if scanner_backed_report and not coverage_sync_matches:
        raise ValueError("final report coverage synchronization did not bind canonical truth")

    return {
        "version": VERSION,
        "existing_renderer_preserved": True,
        "existing_visual_design_preserved": True,
        "canonical_coverage_value": coverage,
        "canonical_incomplete_analyzer_count": incomplete,
        "canonical_maturity_label": maturity,
        "coverage_denominator": denominator,
        "scanner_backed_report": scanner_backed_report,
        "conflicting_coverage_absent": True,
        "coverage_synchronization_applied": coverage_sync_applied,
        "coverage_synchronization_verified": coverage_sync_matches,
        "false_incomplete_analyzers_absent": True,
        "superseded_diagnostics_absent": True,
        "malformed_identifiers_absent": True,
        "production_pdf_validated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _bind_single_pass_projection() -> bool:
    """Reapply exact-run truth after the renderer's authoritative projection pass."""

    from nico import v2_single_pass_premium_report as single_pass

    current = single_pass.project_authoritative_canonical
    if getattr(current, _PROJECT_MARKER, False):
        return True

    @wraps(current)
    def project(value: Mapping[str, Any]) -> dict[str, Any]:
        return reconcile_authoritative_scanner_truth(current(value))

    setattr(project, _PROJECT_MARKER, True)
    setattr(project, "_nico_previous", current)
    single_pass.project_authoritative_canonical = project
    return single_pass.project_authoritative_canonical is project


def install_comprehensive_client_report_render_v60() -> dict[str, Any]:
    """Bind truth correction before, during, and after the approved renderer."""

    from nico import client_report_completion_v2 as completion
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17

    projection_bound = _bind_single_pass_projection()
    current_prepare: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        completion.prepare_client_report_package
    )
    current_finalize: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        completion.finalize_client_report_package
    )

    if getattr(current_prepare, _PREPARE_MARKER, False) and getattr(
        current_finalize,
        _FINALIZE_MARKER,
        False,
    ):
        phase17.prepare_client_report_package = current_prepare
        phase17.finalize_client_report_package = current_finalize
        return {
            "status": "already_installed" if projection_bound else "blocked",
            "version": VERSION,
            "prepare_bound": True,
            "finalize_bound": True,
            "single_pass_projection_bound": projection_bound,
            "final_coverage_synchronization_bound": True,
            "existing_renderer_preserved": True,
        }

    @wraps(current_prepare)
    def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
        prepared = current_prepare(package)
        return reconcile_before_existing_report_renderer(prepared)

    @wraps(current_finalize)
    def finalize(package: Mapping[str, Any]) -> dict[str, Any]:
        result = current_finalize(package)
        result = reconcile_before_existing_report_renderer(result)
        coverage, _incomplete, _maturity, _denominator = _expected_truth(result)
        result = synchronize_final_report_coverage(
            result,
            expected_coverage=coverage,
        )
        validation = validate_existing_report_accuracy(result)
        completion_state = deepcopy(dict(result.get("client_report_completion") or {}))
        completion_state.update(validation)
        result["client_report_completion"] = completion_state
        result["client_accuracy_validation"] = validation
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        return result

    setattr(prepare, _PREPARE_MARKER, True)
    setattr(prepare, "_nico_previous", current_prepare)
    setattr(finalize, _FINALIZE_MARKER, True)
    setattr(finalize, "_nico_previous", current_finalize)

    completion.prepare_client_report_package = prepare
    completion.finalize_client_report_package = finalize
    phase17.prepare_client_report_package = prepare
    phase17.finalize_client_report_package = finalize

    bound = all(
        (
            completion.prepare_client_report_package is prepare,
            completion.finalize_client_report_package is finalize,
            phase17.prepare_client_report_package is prepare,
            phase17.finalize_client_report_package is finalize,
            projection_bound,
        )
    )
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "prepare_bound": completion.prepare_client_report_package is prepare,
        "finalize_bound": completion.finalize_client_report_package is finalize,
        "phase17_prepare_alias_bound": phase17.prepare_client_report_package is prepare,
        "phase17_finalize_alias_bound": phase17.finalize_client_report_package is finalize,
        "single_pass_projection_bound": projection_bound,
        "final_coverage_synchronization_bound": True,
        "existing_renderer_preserved": True,
        "existing_visual_design_preserved": True,
        "canonical_truth_reconciled_before_existing_renderer": True,
        "canonical_truth_reconciled_after_authoritative_projection": True,
        "canonical_coverage_synchronized_after_existing_renderer": True,
        "production_pdf_is_accuracy_acceptance_artifact": True,
        "redesign_performed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_report_render_v60",
    "reconcile_before_existing_report_renderer",
    "validate_existing_report_accuracy",
]
