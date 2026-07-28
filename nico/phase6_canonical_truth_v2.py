from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import sys
from copy import deepcopy
from typing import Any, Iterable

from nico import phase6_final_remediation_v1 as phase6

VERSION = "nico.phase6_canonical_truth.v2"
_PATCH_MARKER = "_nico_phase6_canonical_truth_v2"
_REPOSITORY_ROOTS = (
    ".github/",
    "apps/",
    "config/",
    "docs/",
    "nico/",
    "scripts/",
    "tests/",
)

_ORIGINAL_RECONCILE = phase6.reconcile_assessment
_ORIGINAL_CANONICALIZE_FINDING = phase6._canonicalize_finding
_ORIGINAL_MERGE_FINDING = phase6._merge_finding


def _text(value: Any, limit: int = 6000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _ordered_unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _repository_relative_path(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    raw = re.sub(r"^[A-Za-z]:/", "/", raw)
    raw = re.sub(r"/+/", "/", raw)
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    lowered = raw.casefold()
    candidates: list[tuple[int, str]] = []
    for root in _REPOSITORY_ROOTS:
        index = lowered.find(root.casefold())
        if index >= 0:
            candidates.append((index, raw[index:]))
    if candidates:
        raw = min(candidates, key=lambda item: item[0])[1]
    return raw.lstrip("./") or "location-not-retained"


def _line_number(item: dict[str, Any]) -> int | None:
    for key in ("canonical_line", "line", "line_number", "start_line", "lineNumber"):
        value = item.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    location = _text(item.get("canonical_location") or item.get("location"), 1200)
    match = re.search(r":(\d+)(?::\d+)?$", location)
    return int(match.group(1)) if match else None


def _nested_extra(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("extra") if isinstance(item.get("extra"), dict) else {}


def _tool(item: dict[str, Any]) -> str:
    return _text(item.get("tool") or item.get("scanner") or item.get("analyzer") or "unknown", 120).casefold()


def _rule(item: dict[str, Any]) -> str:
    extra = _nested_extra(item)
    return _text(
        item.get("rule_id")
        or item.get("check_id")
        or item.get("test_id")
        or item.get("code")
        or extra.get("check_id")
        or extra.get("rule_id")
        or "unknown",
        260,
    ).casefold()


def _symbol_or_query(item: dict[str, Any]) -> str:
    extra = _nested_extra(item)
    metavars = extra.get("metavars") if isinstance(extra.get("metavars"), dict) else {}
    direct = (
        item.get("symbol")
        or item.get("function")
        or item.get("function_name")
        or item.get("method")
        or item.get("method_name")
        or item.get("query")
        or item.get("code_snippet")
        or item.get("snippet")
        or extra.get("lines")
        or extra.get("message")
    )
    parts = [_text(direct, 1200)] if direct else []
    for key, value in sorted(metavars.items(), key=lambda pair: str(pair[0])):
        if not isinstance(value, dict):
            continue
        abstract = value.get("abstract_content") or value.get("match")
        if abstract:
            parts.append(f"{key}={_text(abstract, 500)}")
    return " | ".join(part for part in parts if part) or "context-not-retained"


def _analyzer_message(item: dict[str, Any]) -> str:
    extra = _nested_extra(item)
    return _text(
        item.get("analyzer_message")
        or item.get("rule_message")
        or item.get("message")
        or item.get("description")
        or extra.get("message")
        or item.get("title")
        or "Analyzer result requires review.",
        5000,
    )


def _canonicalize_finding_v2(raw: dict[str, Any]) -> dict[str, Any]:
    item = _ORIGINAL_CANONICALIZE_FINDING(raw)
    path = _repository_relative_path(
        raw.get("canonical_path")
        or raw.get("file_path")
        or raw.get("filename")
        or raw.get("path")
        or raw.get("filePath")
        or item.get("canonical_path")
    )
    line = _line_number(raw) or _line_number(item)
    location = f"{path}:{line}" if line else path
    tool = _tool(raw)
    rule_id = _rule(raw)
    symbol = _symbol_or_query(raw)
    analyzer_message = _analyzer_message(raw)
    normalized_evidence = re.sub(r"\bline\s+\d+\b|:\d+(?::\d+)?", "", analyzer_message.casefold())
    normalized_evidence = " ".join(normalized_evidence.split())
    source_fingerprint = _fingerprint(
        {
            "tool": tool,
            "rule_id": rule_id,
            "path": path.casefold(),
            "symbol_or_query": symbol.casefold(),
            "normalized_evidence": normalized_evidence,
        }
    )
    occurrence_fingerprint = _fingerprint(
        {
            "source_evidence_fingerprint": source_fingerprint,
            "canonical_line": line,
        }
    )
    incoming_id = _text(raw.get("finding_id") or raw.get("id"), 180)
    finding_id = incoming_id if incoming_id.upper().startswith("RISK-") else f"RISK-{source_fingerprint[:12].upper()}"
    item.update(
        {
            "id": finding_id,
            "finding_id": finding_id,
            "tool": tool,
            "rule_id": rule_id,
            "canonical_path": path,
            "canonical_line": line,
            "canonical_location": location,
            "location": location,
            "primary_location": location,
            "original_analyzer_location": _text(raw.get("location") or item.get("original_analyzer_location") or location, 1200),
            "symbol_or_query": symbol,
            "analyzer_message": analyzer_message,
            "rule_message": analyzer_message,
            "source_evidence_fingerprint": source_fingerprint,
            "occurrence_fingerprint": occurrence_fingerprint,
            "finding_key": f"finding:{source_fingerprint}",
            "occurrence_key": f"occurrence:{occurrence_fingerprint}",
            "identity_components": {
                "tool": tool,
                "rule_id": rule_id,
                "canonical_path": path,
                "canonical_location": location,
                "symbol_or_query": symbol,
                "normalized_evidence_fingerprint": source_fingerprint,
            },
        }
    )
    if path in phase6._SQL_DISPOSITIONS and phase6._is_sql_message(analyzer_message):
        disposition = deepcopy(phase6._SQL_DISPOSITIONS[path])
        item["disposition"] = disposition
        item["status"] = "bounded_exception"
        item["executive_title"] = "Source-reviewed SQL construction"
        item["technical_summary"] = disposition["rationale"]
        item["recommendation"] = disposition["verification"]
    return item


def _location_sort_key(value: str) -> tuple[str, int, str]:
    text = _text(value, 1200)
    match = re.search(r"^(.*?):(\d+)(?::\d+)?$", text)
    if not match:
        return (_repository_relative_path(text).casefold(), 0, text.casefold())
    return (_repository_relative_path(match.group(1)).casefold(), int(match.group(2)), text.casefold())


def _merge_finding_v2(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = _ORIGINAL_MERGE_FINDING(target, candidate)
    locations = _ordered_unique(
        [
            target.get("canonical_location"),
            candidate.get("canonical_location"),
            *(target.get("related_locations") or []),
            *(candidate.get("related_locations") or []),
        ]
    )
    locations = sorted(locations, key=_location_sort_key)
    primary = locations[0] if locations else _text(merged.get("canonical_location"), 1200)
    match = re.search(r"^(.*?):(\d+)(?::\d+)?$", primary)
    merged["canonical_path"] = _repository_relative_path(match.group(1) if match else primary)
    merged["canonical_line"] = int(match.group(2)) if match else None
    merged["canonical_location"] = primary
    merged["primary_location"] = primary
    merged["location"] = primary
    merged["related_locations"] = locations
    merged["original_analyzer_locations"] = _ordered_unique(
        [
            target.get("original_analyzer_location"),
            candidate.get("original_analyzer_location"),
            *(target.get("original_analyzer_locations") or []),
            *(candidate.get("original_analyzer_locations") or []),
        ]
    )
    merged["analyzer_messages"] = _ordered_unique(
        [
            target.get("analyzer_message"),
            candidate.get("analyzer_message"),
            *(target.get("analyzer_messages") or []),
            *(candidate.get("analyzer_messages") or []),
        ]
    )
    if merged["analyzer_messages"]:
        merged["analyzer_message"] = merged["analyzer_messages"][0]
        merged["rule_message"] = merged["analyzer_messages"][0]
    merged["occurrence_fingerprints"] = _ordered_unique(
        [
            target.get("occurrence_fingerprint"),
            candidate.get("occurrence_fingerprint"),
            *(target.get("occurrence_fingerprints") or []),
            *(candidate.get("occurrence_fingerprints") or []),
        ]
    )
    return merged


def canonicalize_findings_v2(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = _canonicalize_finding_v2(raw)
        key = str(item["finding_key"])
        grouped[key] = _merge_finding_v2(grouped[key], item) if key in grouped else item
    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            phase6._PRIORITY_ORDER.get(str(item.get("priority") or "P3"), 9),
            str(item.get("category") or ""),
            str(item.get("canonical_path") or ""),
            int(item.get("canonical_line") or 0),
            str(item.get("finding_id") or ""),
        ),
    )
    used: dict[str, str] = {}
    actionable: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for item in ordered:
        finding_id = str(item.get("finding_id") or "")
        key = str(item.get("finding_key") or "")
        if finding_id in used and used[finding_id] != key:
            finding_id = f"{finding_id}-{_fingerprint(key)[:6].upper()}"
            item["id"] = finding_id
            item["finding_id"] = finding_id
        used[finding_id] = key
        if isinstance(item.get("disposition"), dict):
            dispositions.append(item)
        else:
            actionable.append(item)
    return actionable, dispositions


def _canonicalize_surface_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    output.pop("phase5_verified_outcomes", None)
    output.pop("phase5_tracked_complexity_metrics", None)
    sections = [
        item
        for item in output.get("sections") or []
        if isinstance(item, dict) and item.get("id") != "phase5_verified_outcomes"
    ]
    output["sections"] = sections
    raw_findings: list[dict[str, Any]] = []
    for field in ("decision_grade_findings_register", "findings_register", "executive_risk_register"):
        raw_findings.extend(item for item in output.get(field) or [] if isinstance(item, dict))
    actionable, dispositions = canonicalize_findings_v2(raw_findings)
    output["findings_register"] = actionable
    output["decision_grade_findings_register"] = actionable
    output["executive_risk_register"] = actionable[:7]
    output["finding_dispositions"] = dispositions
    output["finding_integrity"] = {
        "schema": VERSION,
        "canonical_model_version": VERSION,
        "actionable_unique_count": len(actionable),
        "source_reviewed_disposition_count": len(dispositions),
        "stable_ids_unique": len({item["finding_id"] for item in actionable}) == len(actionable),
        "canonical_locations_present": all(bool(item.get("canonical_location")) for item in actionable),
        "occurrence_identity_retained": all(bool(item.get("occurrence_fingerprints") or item.get("occurrence_fingerprint")) for item in actionable),
        "ordered_set_mappings": True,
    }
    output["canonical_assessment_model"] = VERSION
    return output


def reconcile_assessment_v2(assessment: dict[str, Any], stage_results: dict[str, Any]) -> dict[str, Any]:
    return _canonicalize_surface_assessment(_ORIGINAL_RECONCILE(assessment, stage_results))


def _projection(assessment: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}
    ci = assessment.get("ci_health") if isinstance(assessment.get("ci_health"), dict) else {}
    limitations = assessment.get("limitation_metrics") if isinstance(assessment.get("limitation_metrics"), dict) else {}
    findings = [item for item in assessment.get("decision_grade_findings_register") or assessment.get("findings_register") or [] if isinstance(item, dict)]
    return {
        "identity": {
            key: _text((identity or {}).get(key) or assessment.get(key), 500)
            for key in ("repository", "commit_sha", "run_id", "evidence_ledger_id", "customer_id", "project_id")
        },
        "technical_score": maturity.get("presented_score", maturity.get("score", assessment.get("technical_score"))),
        "evidence_adjusted_score": assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score")),
        "scanner_states": {
            "completed": sorted(_text(item, 120).casefold() for item in health.get("completed_scanners") or []),
            "incomplete": sorted(
                (
                    _text(item.get("scanner"), 120).casefold(),
                    _text(item.get("status"), 80).casefold(),
                )
                for item in health.get("incomplete_scanners") or []
                if isinstance(item, dict)
            ),
        },
        "findings": [
            {
                "finding_id": item.get("finding_id") or item.get("id"),
                "priority": item.get("priority"),
                "status": item.get("status"),
                "canonical_path": item.get("canonical_path"),
                "canonical_line": item.get("canonical_line"),
                "canonical_location": item.get("canonical_location") or item.get("location"),
                "acceptance_criteria": _ordered_unique(item.get("acceptance_criteria") or []),
                "roadmap_mappings": _ordered_unique(item.get("roadmap_mappings") or []),
                "backlog_mappings": _ordered_unique(item.get("backlog_mappings") or [item.get("backlog_issue_mapping")]),
            }
            for item in findings
        ],
        "limitation_count": limitations.get("individual_limitation_records"),
        "ci_assessed_commit": ci.get("assessed_commit"),
        "delivery_status": assessment.get("delivery_status"),
        "human_review_required": assessment.get("human_review_required") is True,
        "client_delivery_allowed": assessment.get("client_delivery_allowed") is True,
    }


def factual_parity_fingerprint(assessment: dict[str, Any], identity: dict[str, Any] | None = None) -> str:
    return _fingerprint(_projection(assessment, identity))


def compare_language_factual_parity(
    english_assessment: dict[str, Any],
    spanish_assessment: dict[str, Any],
    *,
    english_identity: dict[str, Any] | None = None,
    spanish_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    english = _projection(english_assessment, english_identity)
    spanish = _projection(spanish_assessment, spanish_identity)
    return {
        "schema": "nico.phase6.language_factual_parity.v1",
        "equivalent": english == spanish,
        "english_fingerprint": _fingerprint(english),
        "spanish_fingerprint": _fingerprint(spanish),
        "facts_compared": [
            "identity",
            "technical_score",
            "evidence_adjusted_score",
            "scanner_states",
            "findings",
            "limitation_count",
            "ci_assessed_commit",
            "delivery_status",
            "human_review_required",
            "client_delivery_allowed",
        ],
    }


def _pdf_text(package: dict[str, Any]) -> str:
    encoded = str(package.get("pdf_base64") or "")
    if not encoded:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(base64.b64decode(encoded)))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _csv_projection(csv_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(csv_text or "")):
        rows.append(
            {
                "finding_id": row.get("finding_id") or row.get("id"),
                "priority": row.get("priority"),
                "status": row.get("status"),
                "canonical_path": row.get("canonical_path"),
                "canonical_line": int(row["canonical_line"]) if str(row.get("canonical_line") or "").isdigit() else None,
                "canonical_location": row.get("canonical_location") or row.get("location"),
                "acceptance_criteria": _ordered_unique(str(row.get("acceptance_criteria") or "").split(";")),
                "roadmap_mappings": _ordered_unique(str(row.get("roadmap_mappings") or "").split(";")),
                "backlog_mappings": _ordered_unique(str(row.get("backlog_mappings") or row.get("backlog_issue_mapping") or "").split(";")),
            }
        )
    return rows


def validate_cross_format_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = result
    assessment = output.get("assessment") if isinstance(output.get("assessment"), dict) else {}
    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    canonical_json = package.get("json") if isinstance(package.get("json"), dict) else {}
    json_assessment = canonical_json.get("assessment") if isinstance(canonical_json.get("assessment"), dict) else assessment
    identity = canonical_json.get("identity") if isinstance(canonical_json.get("identity"), dict) else {}
    expected = _projection(assessment, identity)
    json_projection = _projection(json_assessment, identity)
    violations: list[str] = []
    if expected != json_projection:
        violations.append("canonical_json_projection_mismatch")
    expected_findings = expected["findings"]
    csv_findings = _csv_projection(str(package.get("findings_csv") or ""))
    if csv_findings != expected_findings:
        violations.append("findings_csv_projection_mismatch")
    surfaces = {
        "markdown": str(package.get("markdown") or ""),
        "html": str(package.get("html") or ""),
        "pdf": _pdf_text(package),
    }
    for surface, text in surfaces.items():
        if not text:
            violations.append(f"{surface}_missing")
            continue
        compact = " ".join(text.split())
        for finding in expected_findings:
            finding_id = _text(finding.get("finding_id"), 200)
            path = _text(finding.get("canonical_path"), 1200)
            line = finding.get("canonical_line")
            if finding_id and finding_id not in compact:
                violations.append(f"{surface}_missing_finding_id:{finding_id}")
            if path and path not in compact:
                violations.append(f"{surface}_missing_path:{finding_id}")
            if line and str(line) not in compact:
                violations.append(f"{surface}_missing_line:{finding_id}")
        for scanner in expected["scanner_states"]["completed"]:
            if scanner and scanner not in compact.casefold():
                violations.append(f"{surface}_missing_completed_scanner:{scanner}")
    manifest = {
        "schema": "nico.phase6.cross_format_truth.v1",
        "status": "valid" if not violations else "invalid",
        "projection": expected,
        "projection_sha256": _fingerprint(expected),
        "violations": _ordered_unique(violations),
        "formats_checked": ["canonical_json", "findings_csv", "markdown", "html", "pdf"],
    }
    package["canonical_truth_manifest"] = manifest
    package["canonical_truth_manifest_json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    package["canonical_truth_manifest_sha256"] = _fingerprint(manifest)
    package["language_factual_parity_projection"] = expected
    package["language_factual_parity_fingerprint"] = _fingerprint(expected)
    output["report_package"] = package
    quality = output.get("report_quality_contract") if isinstance(output.get("report_quality_contract"), dict) else {}
    quality["cross_format_truth_consistent"] = not violations
    quality["cross_format_truth_violation_count"] = len(manifest["violations"])
    quality["language_factual_parity_projection_present"] = True
    output["report_quality_contract"] = quality
    if violations:
        output["status"] = "blocked"
        output["reason"] = "phase6_cross_format_truth_mismatch"
    return output


def _patch_report_boundaries() -> None:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_view = report.apply_report_view
    if not getattr(current_view, _PATCH_MARKER, False):
        def apply_report_view(assessment: dict[str, Any], contract: Any) -> dict[str, Any]:
            return _canonicalize_surface_assessment(current_view(assessment, contract))

        setattr(apply_report_view, _PATCH_MARKER, True)
        report.apply_report_view = apply_report_view

    current_prepare = report._prepare_report_context
    if not getattr(current_prepare, _PATCH_MARKER, False):
        def prepare(identity: dict[str, Any], stage_results: dict[str, dict[str, Any]]) -> tuple[Any, ...]:
            generated_at, assessment, stages, limitations, roadmap, staffing = current_prepare(identity, stage_results)
            assessment = reconcile_assessment_v2(assessment, stage_results)
            limitations = report._limitation_metrics(assessment, stages)
            assessment["limitation_metrics"] = {
                **dict(assessment.get("limitation_metrics") or {}),
                **limitations,
            }
            return generated_at, assessment, stages, limitations, roadmap, staffing

        setattr(prepare, _PATCH_MARKER, True)
        report._prepare_report_context = prepare

    current_build = report.build_comprehensive_report_package
    if not getattr(current_build, _PATCH_MARKER, False):
        def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = current_build(*args, **kwargs)
            if isinstance(result.get("assessment"), dict):
                result["assessment"] = _canonicalize_surface_assessment(result["assessment"])
            return validate_cross_format_truth(result)

        setattr(build, _PATCH_MARKER, True)
        report.build_comprehensive_report_package = build
        for module in tuple(sys.modules.values()):
            name = str(getattr(module, "__name__", ""))
            if name.startswith("nico.") and getattr(module, "build_comprehensive_report_package", None) is current_build:
                setattr(module, "build_comprehensive_report_package", build)


def install_phase6_canonical_truth_v2() -> dict[str, Any]:
    phase6._normalize_path = _repository_relative_path
    phase6._canonicalize_finding = _canonicalize_finding_v2
    phase6._merge_finding = _merge_finding_v2
    phase6.canonicalize_findings = canonicalize_findings_v2
    phase6.reconcile_assessment = reconcile_assessment_v2
    _patch_report_boundaries()
    return {
        "status": "installed",
        "version": VERSION,
        "repository_relative_paths": True,
        "finding_identity_includes_tool_rule_path_location_symbol_and_evidence": True,
        "grouped_occurrences_retain_individual_locations": True,
        "canonical_model_precedes_all_renderers": True,
        "cross_format_truth_build_gate": True,
        "language_factual_parity_projection": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonicalize_findings_v2",
    "reconcile_assessment_v2",
    "factual_parity_fingerprint",
    "compare_language_factual_parity",
    "validate_cross_format_truth",
    "install_phase6_canonical_truth_v2",
]
