from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


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


def _normalized_location(value: Any) -> str:
    return _text(value).lower().replace("\\", "/")


def _normalized_title(value: Any) -> str:
    return " ".join(_text(value).lower().replace("_", " ").split())


def _criterion_identity(value: Any) -> str:
    text = _text(value).lower()
    for marker in ("[method:", "[target commit:"):
        while marker in text:
            start = text.find(marker)
            end = text.find("]", start)
            text = text[:start] + (text[end + 1 :] if end >= 0 else "")
    return " ".join(text.split()).strip(" ;")


def semantic_finding_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    evidence = _text(finding.get("fact") or finding.get("evidence"))
    return (
        _text(finding.get("category")).lower(),
        _normalized_location(finding.get("location")),
        _normalized_title(finding.get("title") or finding.get("decision_title") or finding.get("interpretation")),
        evidence.lower(),
    )


def _merge_acceptance_criteria(*values: Any) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for value in values:
        items = value if isinstance(value, list) else [value] if value else []
        for item in items:
            key = _criterion_identity(item)
            if key and key not in seen:
                seen.add(key)
                merged.append(item)
    return merged


def canonicalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    canonical: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for raw in findings:
        item = deepcopy(dict(raw))
        key = semantic_finding_key(item)
        if not any(key):
            raise ValueError("finding lacks semantic identity")
        item_id = _text(item.get("finding_id") or item.get("id"))
        item["acceptance_criteria"] = _merge_acceptance_criteria(item.get("acceptance_criteria"))
        if key not in canonical:
            aliases = [item_id] if item_id else []
            item["finding_aliases"] = list(dict.fromkeys([*item.get("finding_aliases", []), *aliases]))
            canonical[key] = item
            order.append(key)
            continue
        current = canonical[key]
        aliases = [
            *current.get("finding_aliases", []),
            _text(current.get("finding_id") or current.get("id")),
            *item.get("finding_aliases", []),
            item_id,
        ]
        current["finding_aliases"] = [value for value in dict.fromkeys(aliases) if value]
        current["acceptance_criteria"] = _merge_acceptance_criteria(
            current.get("acceptance_criteria"), item.get("acceptance_criteria")
        )
        for field_name in (
            "business_impact", "impact", "recommendation", "owner_role", "effort",
            "cost_of_inaction", "residual_risk", "supporting_evidence", "roadmap_links",
        ):
            if not current.get(field_name) and item.get(field_name):
                current[field_name] = deepcopy(item[field_name])
    result = [canonical[key] for key in order]
    ids = [_text(item.get("finding_id") or item.get("id")) for item in result]
    if len([value for value in ids if value]) != len(set(value for value in ids if value)):
        raise ValueError("canonical finding IDs are not unique")
    return result


def normalize_scanner_result(raw: Mapping[str, Any], expected_commit_sha: str) -> ScannerResult:
    name = _text(raw.get("scanner_name") or raw.get("scanner") or raw.get("tool"))
    commit_sha = _text(raw.get("commit_sha") or raw.get("snapshot_commit_sha") or expected_commit_sha)
    exact_commit = commit_sha == expected_commit_sha
    findings_raw = raw.get("findings") or []
    findings = tuple(item for item in findings_raw if isinstance(item, Mapping))
    exit_code = raw.get("exit_code") if isinstance(raw.get("exit_code"), int) else None
    artifact_hash = _text(raw.get("artifact_hash") or raw.get("sha256"))
    raw_status = _text(raw.get("status") or raw.get("state")).lower().replace("-", "_")
    failure_reason = _text(raw.get("failure_reason") or raw.get("error") or raw.get("stderr"))

    completed_signal = raw.get("completed") is True or raw_status in {
        "complete", "completed", "success", "passed", "completed_with_findings"
    }
    findings_exit_is_success = exit_code == 1 and name in {"bandit", "eslint", "gitleaks", "trufflehog"}
    completed = bool(completed_signal or (findings_exit_is_success and artifact_hash and exact_commit))
    verified = bool(raw.get("verified") is True or raw.get("verified_complete") is True)
    verified = verified and completed and exact_commit and bool(artifact_hash)

    if completed:
        state = ScannerState.COMPLETED_WITH_FINDINGS if findings else ScannerState.COMPLETED
        failure_reason = ""
    elif raw_status in {"partial", "review_limited"}:
        state = ScannerState.PARTIAL
    elif raw_status in {"missing", "unavailable", "not_installed", "not_available"}:
        state = ScannerState.UNAVAILABLE
    else:
        state = ScannerState.FAILED
        failure_reason = failure_reason or f"{name or 'scanner'} did not produce a valid exact-SHA artifact"

    result = ScannerResult(
        scanner_name=name,
        commit_sha=commit_sha,
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


def build_canonical_assessment(report: Mapping[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(dict(report))
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or canonical.get("commit_sha"))
    if not commit_sha:
        raise ValueError("canonical assessment requires immutable commit_sha")

    source_findings: list[Mapping[str, Any]] = []
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        values = canonical.get(surface) or []
        source_findings.extend(item for item in values if isinstance(item, Mapping))
    findings = canonicalize_findings(source_findings)

    scanner_source = (
        canonical.get("scanner_execution_records")
        or (canonical.get("assessment") or {}).get("scanner_execution_records")
        or []
    )
    scanners = [normalize_scanner_result(item, commit_sha) for item in scanner_source if isinstance(item, Mapping)]
    scanner_dicts = [{**asdict(item), "state": item.state.value, "findings": [dict(value) for value in item.findings]} for item in scanners]

    canonical["canonical_findings"] = deepcopy(findings)
    canonical["findings_register"] = deepcopy(findings)
    canonical["findings"] = deepcopy(findings)
    canonical["decision_grade_findings_register"] = deepcopy(findings)
    canonical["executive_risk_register"] = deepcopy(findings[:7])
    canonical["priority_findings"] = deepcopy(findings[:5])
    canonical["scanner_execution_records"] = scanner_dicts
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["scanner_execution_records"] = deepcopy(scanner_dicts)
    canonical["assessment"] = assessment
    canonical["v2_pipeline_contract"] = {
        "version": "nico.v2.single_source_pipeline.v1",
        "immutable_commit_sha": commit_sha,
        "canonical_finding_count": len(findings),
        "scanner_result_count": len(scanners),
        "single_source_of_truth": True,
        "parallel_report_pipelines_forbidden": True,
        "publish_fails_on_duplicate_findings": True,
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
    "canonicalize_findings", "derive_assessment_state", "build_canonical_assessment",
    "canonical_truth_sha256", "assert_cross_format_identity",
]
