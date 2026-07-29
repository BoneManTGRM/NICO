from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from nico.phase9_production_report_gate_v1 import contextual_title


class AssessmentState(str, Enum):
    RUNNING = "running"
    ANALYZING = "analyzing"
    GENERATING_REPORT = "generating_report"
    REVIEW_REQUIRED = "review_required"
    CLIENT_READY = "client_ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScannerState(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_FINDINGS = "completed_with_findings"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class ScannerResult:
    scanner_name: str
    commit_sha: str
    state: ScannerState
    completed: bool
    verified: bool
    artifact_hash: str
    findings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    duration_seconds: float | None = None
    stdout: str = ""
    stderr: str = ""
    failure_reason: str = ""
    exit_code: int | None = None

    def validate(self) -> None:
        if not self.scanner_name.strip():
            raise ValueError("scanner_name is required")
        if not self.commit_sha.strip():
            raise ValueError(f"{self.scanner_name}: commit_sha is required")
        if self.completed and self.state not in {ScannerState.COMPLETED, ScannerState.COMPLETED_WITH_FINDINGS}:
            raise ValueError(f"{self.scanner_name}: completed scanner has non-complete state")
        if self.verified and not self.completed:
            raise ValueError(f"{self.scanner_name}: verified scanner must be completed")
        if self.verified and not self.artifact_hash:
            raise ValueError(f"{self.scanner_name}: verified scanner requires artifact_hash")
        if self.state is ScannerState.FAILED and not self.failure_reason:
            raise ValueError(f"{self.scanner_name}: failed scanner requires failure_reason")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }.get(normalized, normalized)


def _normalized_location(value: Any) -> str:
    if isinstance(value, Mapping):
        path = _text(value.get("path") or value.get("file") or value.get("file_path") or value.get("filename"))
        line = _text(value.get("line") or value.get("start_line") or value.get("line_number"))
        value = f"{path}:{line}" if line else path
    normalized = _text(value).casefold().replace("\\", "/")
    normalized = re.sub(r"\s*:\s*", ":", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _normalized_title(value: Any) -> str:
    text = _text(value).casefold().replace("_", " ")
    text = re.sub(r"\brisk(?:-p[0-3])?-[a-z0-9]+\b", "", text)
    return " ".join(text.split()).strip(" -:·")


def _rule_family(finding: Mapping[str, Any]) -> str:
    rule = _text(
        finding.get("rule_id")
        or finding.get("rule")
        or finding.get("check_id")
        or finding.get("test_id")
        or finding.get("code")
    ).casefold()
    if rule:
        return rule
    title = _normalized_title(
        finding.get("interpretation")
        or finding.get("decision_title")
        or finding.get("title")
    )
    if "complexity" in title and ("hotspot" in title or "complex" in title):
        return "complexity-hotspot"
    return title


def _criterion_identity(value: Any) -> str:
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).casefold()
    text = _text(value)
    text = re.sub(r"\s*\[(?:method|target\s+commit)\s*:[^\]]*\]", "", text, flags=re.I)
    text = re.sub(r"\b[0-9a-f]{40,64}\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ;,.\t")
    return text.casefold()


def _criterion_output(value: Any) -> Any:
    if not isinstance(value, str):
        return deepcopy(value)
    cleaned = re.sub(r"\s*\[(?:method|target\s+commit)\s*:[^\]]*\]", "", value, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ;\t")
    return cleaned


def semantic_finding_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _text(finding.get("category")).casefold(),
        _normalized_location(finding.get("location")),
        _text(finding.get("symbol") or finding.get("function") or finding.get("component")).casefold(),
        _rule_family(finding),
    )


def _merge_acceptance_criteria(*values: Any) -> list[Any]:
    selected: dict[str, Any] = {}
    order: list[str] = []
    for value in values:
        if isinstance(value, str):
            items: list[Any] = [part.strip() for part in value.split(";") if part.strip()]
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            items = [value] if value else []
        for item in items:
            key = _criterion_identity(item)
            if not key:
                continue
            cleaned = _criterion_output(item)
            if key not in selected:
                selected[key] = cleaned
                order.append(key)
            elif isinstance(cleaned, str) and isinstance(selected[key], str) and len(cleaned) < len(selected[key]):
                selected[key] = cleaned
    return [selected[key] for key in order]


def _finding_quality(item: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    identifier = _text(item.get("finding_id") or item.get("id"))
    priority_id = int(identifier.upper().startswith("RISK-P"))
    populated = sum(
        bool(item.get(field_name))
        for field_name in (
            "business_impact", "impact", "recommendation", "owner_role", "effort",
            "cost_of_inaction", "residual_risk", "roadmap", "roadmap_links", "backlog_id",
        )
    )
    criteria = len(_merge_acceptance_criteria(item.get("acceptance_criteria")))
    evidence = len(_text(item.get("fact") or item.get("evidence")))
    return priority_id, populated, criteria, evidence, identifier


def _normalize_finding(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    title = contextual_title(item)
    if title:
        item["title"] = title
        item["decision_title"] = title
    item["acceptance_criteria"] = _merge_acceptance_criteria(item.get("acceptance_criteria"))
    aliases = [
        *list(item.get("finding_aliases") or []),
        item.get("finding_id") or item.get("id"),
    ]
    item["finding_aliases"] = list(dict.fromkeys(_text(value) for value in aliases if _text(value)))
    return item


def _merge_findings(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _finding_quality(right) > _finding_quality(left) else (left, right)
    merged = deepcopy(dict(preferred))
    for field_name, value in other.items():
        if merged.get(field_name) in (None, "", [], {}):
            merged[field_name] = deepcopy(value)
    aliases = [
        *list(preferred.get("finding_aliases") or []),
        preferred.get("finding_id") or preferred.get("id"),
        *list(other.get("finding_aliases") or []),
        other.get("finding_id") or other.get("id"),
    ]
    merged["finding_aliases"] = list(dict.fromkeys(_text(value) for value in aliases if _text(value)))
    merged["acceptance_criteria"] = _merge_acceptance_criteria(
        preferred.get("acceptance_criteria"), other.get("acceptance_criteria")
    )
    canonical_id = _text(preferred.get("finding_id") or preferred.get("id"))
    if canonical_id:
        merged["finding_id"] = canonical_id
        merged["id"] = canonical_id
    return _normalize_finding(merged)


def canonicalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for raw in findings:
        item = _normalize_finding(raw)
        key = semantic_finding_key(item)
        if not any(key):
            raise ValueError("finding lacks semantic identity")
        if key not in selected:
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge_findings(selected[key], item)
    result = [selected[key] for key in order]
    ids = [_text(item.get("finding_id") or item.get("id")) for item in result]
    populated_ids = [value for value in ids if value]
    if len(populated_ids) != len(set(populated_ids)):
        raise ValueError("canonical finding IDs are not unique")
    keys = [semantic_finding_key(item) for item in result]
    if len(keys) != len(set(keys)):
        raise ValueError("canonical findings contain semantic duplicates")
    for item in result:
        criteria = item.get("acceptance_criteria") or []
        identities = [_criterion_identity(value) for value in criteria]
        if len(identities) != len(set(identities)):
            raise ValueError("canonical finding contains repeated acceptance criteria")
    return result


def normalize_scanner_result(raw: Mapping[str, Any], expected_commit_sha: str) -> ScannerResult:
    name = _scanner_name(raw.get("scanner_name") or raw.get("scanner") or raw.get("tool"))
    commit_sha = _text(
        raw.get("commit_sha")
        or raw.get("snapshot_commit_sha")
        or raw.get("target_commit_sha")
        or expected_commit_sha
    ).casefold()
    expected = _text(expected_commit_sha).casefold()
    exact_commit = bool(commit_sha and expected and commit_sha == expected)
    findings_raw = raw.get("findings") or raw.get("issues") or raw.get("results") or []
    findings = tuple(item for item in findings_raw if isinstance(item, Mapping))
    raw_exit = raw.get("exit_code") if raw.get("exit_code") is not None else raw.get("returncode")
    exit_code = raw_exit if isinstance(raw_exit, int) else None
    artifact_hash = _text(
        raw.get("artifact_hash")
        or raw.get("raw_artifact_sha256")
        or raw.get("sha256")
        or raw.get("deterministic_fingerprint")
    )
    raw_status = _text(raw.get("status") or raw.get("state")).casefold().replace("-", "_")
    failure_reason = _text(
        raw.get("failure_reason")
        or raw.get("failure_or_unavailable_reason")
        or raw.get("reason")
        or raw.get("error")
        or raw.get("stderr")
    )

    completed_signal = raw.get("completed") is True or raw_status in {
        "complete", "completed", "success", "passed", "completed_clean", "completed_with_findings"
    }
    findings_exit_is_success = exit_code == 1 and name in {"bandit", "eslint", "gitleaks"}
    valid_artifact = bool(artifact_hash and exact_commit)
    completed = bool(valid_artifact and (completed_signal or findings_exit_is_success))
    retention_declared = "raw_artifact_retention_complete" in raw
    retention_valid = raw.get("raw_artifact_retention_complete") is True if retention_declared else True
    verified_signal = any(
        raw.get(field_name) is True
        for field_name in ("verified", "verified_complete", "verified_for_this_report", "output_capture_complete")
    )
    verified = bool(completed and verified_signal and retention_valid)

    if completed:
        state = ScannerState.COMPLETED_WITH_FINDINGS if findings else ScannerState.COMPLETED
        failure_reason = ""
    elif raw_status in {"missing", "unavailable", "not_installed", "not_available", "not_applicable"}:
        state = ScannerState.UNAVAILABLE
        failure_reason = failure_reason or f"{name or 'scanner'} was unavailable for this exact commit"
    elif raw_status in {"partial", "review_limited"} or completed_signal:
        state = ScannerState.PARTIAL
        failure_reason = failure_reason or f"{name or 'scanner'} did not retain a complete exact-SHA artifact"
    else:
        state = ScannerState.FAILED
        failure_reason = failure_reason or f"{name or 'scanner'} did not produce a valid exact-SHA artifact"

    result = ScannerResult(
        scanner_name=name,
        commit_sha=commit_sha or expected,
        state=state,
        completed=completed,
        verified=verified,
        artifact_hash=artifact_hash,
        findings=findings,
        duration_seconds=float(raw["duration_seconds"]) if isinstance(raw.get("duration_seconds"), (int, float)) else None,
        stdout=_text(raw.get("stdout")),
        stderr=_text(raw.get("stderr")),
        failure_reason=failure_reason,
        exit_code=exit_code,
    )
    result.validate()
    return result


def derive_assessment_state(*, package_complete: bool, review_required: bool, review_approved: bool,
                            client_delivery_allowed: bool, fatal_error: bool = False,
                            cancelled: bool = False) -> AssessmentState:
    if cancelled:
        return AssessmentState.CANCELLED
    if fatal_error:
        return AssessmentState.FAILED
    if review_approved and client_delivery_allowed:
        return AssessmentState.CLIENT_READY
    if package_complete and review_required:
        return AssessmentState.REVIEW_REQUIRED
    if package_complete:
        return AssessmentState.GENERATING_REPORT
    return AssessmentState.ANALYZING


def _scanner_records(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    candidates = (
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
        canonical.get("analyzer_evidence_report"),
    )
    records: list[Mapping[str, Any]] = []
    for value in candidates:
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, Mapping))
        elif isinstance(value, Mapping):
            nested = value.get("scanner_execution_records") or value.get("records") or value.get("scanners")
            if isinstance(nested, list):
                records.extend(item for item in nested if isinstance(item, Mapping))
    return records


def build_canonical_assessment(report: Mapping[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(dict(report))
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or canonical.get("commit_sha")).casefold()
    if not commit_sha:
        raise ValueError("canonical assessment requires immutable commit_sha")

    source_findings: list[Mapping[str, Any]] = []
    for surface in (
        "canonical_findings", "findings_register", "findings",
        "decision_grade_findings_register", "executive_risk_register", "priority_findings",
    ):
        values = canonical.get(surface) or []
        source_findings.extend(item for item in values if isinstance(item, Mapping))
    findings = canonicalize_findings(source_findings)

    by_scanner: dict[str, ScannerResult] = {}
    for raw in _scanner_records(canonical):
        result = normalize_scanner_result(raw, commit_sha)
        current = by_scanner.get(result.scanner_name)
        quality = lambda item: (
            int(item.verified), int(item.completed), int(bool(item.artifact_hash)),
            len(item.findings), int(item.state is not ScannerState.FAILED),
        )
        if current is None or quality(result) > quality(current):
            by_scanner[result.scanner_name] = result
    scanners = [by_scanner[name] for name in sorted(by_scanner)]
    scanner_dicts = [
        {**asdict(item), "state": item.state.value, "findings": [dict(value) for value in item.findings]}
        for item in scanners
    ]

    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(findings)
    canonical["executive_risk_register"] = deepcopy(findings[:7])
    canonical["priority_findings"] = deepcopy(findings[:5])
    canonical["scanner_execution_records"] = scanner_dicts
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["scanner_execution_records"] = deepcopy(scanner_dicts)
    assessment["completed_scanner_records"] = [item for item in scanner_dicts if item["completed"]]
    assessment["incomplete_scanner_records"] = [item for item in scanner_dicts if not item["completed"]]
    canonical["assessment"] = assessment
    canonical["v2_pipeline_contract"] = {
        "version": "nico.v2.single_source_pipeline.v2",
        "immutable_commit_sha": commit_sha,
        "canonical_finding_count": len(findings),
        "scanner_result_count": len(scanners),
        "single_source_of_truth": True,
        "parallel_report_pipelines_forbidden": True,
        "publish_fails_on_duplicate_findings": True,
        "acceptance_metadata_removed_from_client_criteria": True,
        "prioritized_finding_identity_preferred": True,
        "generic_titles_contextualized_before_rendering": True,
    }
    return canonical


def canonical_truth_sha256(canonical: Mapping[str, Any]) -> str:
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_cross_format_identity(*, canonical_sha256: str, markdown_canonical_sha256: str,
                                 pdf_canonical_sha256: str, ui_canonical_sha256: str) -> None:
    values = {canonical_sha256, markdown_canonical_sha256, pdf_canonical_sha256, ui_canonical_sha256}
    if "" in values or len(values) != 1:
        raise ValueError("JSON, Markdown, PDF, and UI do not share one canonical truth SHA-256")


__all__ = [
    "AssessmentState", "ScannerState", "ScannerResult", "normalize_scanner_result",
    "semantic_finding_key", "canonicalize_findings", "derive_assessment_state",
    "build_canonical_assessment", "canonical_truth_sha256", "assert_cross_format_identity",
]
