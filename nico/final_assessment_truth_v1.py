from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

VERSION = "nico.final_assessment_truth.v2"


class TruthViolation(ValueError):
    """Raised when a report surface attempts to publish contradictory facts."""


class EvidenceLocationType(str, Enum):
    SOURCE_CODE = "source_code"
    WORKFLOW = "workflow"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    REPOSITORY_OBSERVATION = "repository_observation"
    OPERATIONAL_WINDOW = "operational_window"
    ARTIFACT = "artifact"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"


class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    FINAL_PENDING_APPROVAL = "FINAL-PENDING-APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ordered_unique(values: Iterable[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _normalized_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _location_parts(finding: Mapping[str, Any]) -> tuple[str, Any]:
    location = finding.get("location")
    if isinstance(location, Mapping):
        path = location.get("path") or location.get("file") or location.get("file_path")
        line_or_symbol = location.get("symbol") or location.get("line") or location.get("start_line")
        return _normalized_path(path), line_or_symbol or "repository"

    if isinstance(location, str):
        normalized = location.strip().replace("\\", "/")
        match = re.match(r"^(.*?):(\d+)(?::\d+)?$", normalized)
        if match:
            return _normalized_path(match.group(1)), int(match.group(2))
        if normalized:
            return _normalized_path(normalized), finding.get("line") or "repository"

    path = (
        finding.get("canonical_path")
        or finding.get("file_path")
        or finding.get("path")
        or finding.get("filename")
    )
    line_or_symbol = (
        finding.get("canonical_symbol")
        or finding.get("symbol")
        or finding.get("canonical_line")
        or finding.get("line")
        or finding.get("start_line")
        or "repository"
    )
    return _normalized_path(path), line_or_symbol


def _finding_title(finding: Mapping[str, Any]) -> str:
    return _text(
        finding.get("decision_title")
        or finding.get("title")
        or finding.get("interpretation")
        or finding.get("summary")
        or finding.get("description")
    ).casefold()


def canonical_finding_identity(finding: Mapping[str, Any], identity: Mapping[str, Any]) -> str:
    path, line_or_symbol = _location_parts(finding)
    title = _finding_title(finding)
    evidence = finding.get("evidence_fingerprint") or finding.get("source_evidence_fingerprint") or finding.get("fact") or finding.get("evidence")
    key = {
        "provider": identity.get("provider") or "github",
        "repository": identity.get("repository"),
        "revision": identity.get("immutable_revision") or identity.get("commit_sha"),
        "category": _text(finding.get("category")).casefold(),
        "path": path.casefold(),
        "line_or_symbol": str(line_or_symbol).casefold(),
        "title": title,
    }
    # Repository-level findings may legitimately share category/title. Keep their
    # analyzer identity in the key when no durable source location exists.
    if not path or line_or_symbol == "repository":
        key.update(
            {
                "tool": finding.get("tool") or finding.get("source"),
                "rule": finding.get("rule_id") or finding.get("check_id"),
                "evidence": _fingerprint(evidence),
            }
        )
    return "RISK-" + _fingerprint(key)[:12].upper()


def _criterion_key(value: Mapping[str, Any]) -> str:
    return _fingerprint(
        {
            "statement": _text(value.get("statement") or value.get("criterion") or value.get("text")),
            "method": _text(value.get("verification_method") or value.get("method")),
            "required_evidence": _text(value.get("required_evidence")),
            "target_commit": _text(value.get("target_commit") or value.get("commit_sha")),
        }
    )


def normalize_acceptance_criteria(values: Sequence[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        record = dict(value) if isinstance(value, Mapping) else {"statement": _text(value)}
        statement = _text(record.get("statement") or record.get("criterion") or record.get("text"))
        if not statement:
            continue
        record["statement"] = statement
        record.setdefault("verification_method", record.pop("method", "human_review"))
        record.setdefault("status", "pending")
        key = _criterion_key(record)
        if key in seen:
            continue
        seen.add(key)
        record["criterion_id"] = record.get("criterion_id") or "AC-" + key[:12].upper()
        normalized.append(record)
    return normalized


def canonicalize_findings(findings: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    aliases: dict[str, list[str]] = {}
    for raw in findings:
        item = deepcopy(dict(raw))
        path, line_or_symbol = _location_parts(item)
        item["canonical_path"] = path
        if isinstance(line_or_symbol, int) or str(line_or_symbol).isdigit():
            item["canonical_line"] = int(line_or_symbol)
        elif line_or_symbol != "repository":
            item["canonical_symbol"] = str(line_or_symbol)
        finding_id = canonical_finding_identity(item, identity)
        legacy_id = _text(item.get("finding_id") or item.get("id"))
        item["finding_id"] = finding_id
        item["id"] = finding_id
        item["acceptance_criteria"] = normalize_acceptance_criteria(item.get("acceptance_criteria") or [])
        for key in ("roadmap_mappings", "backlog_mappings", "related_locations", "evidence_sources"):
            item[key] = _ordered_unique(item.get(key) or [])
        if finding_id not in merged:
            merged[finding_id] = item
            aliases[finding_id] = []
        else:
            target = merged[finding_id]
            for key in ("acceptance_criteria", "roadmap_mappings", "backlog_mappings", "related_locations", "evidence_sources"):
                target[key] = _ordered_unique([*(target.get(key) or []), *(item.get(key) or [])])
            target["occurrences"] = _ordered_unique(
                [
                    *(target.get("occurrences") or []),
                    *(item.get("occurrences") or []),
                    item.get("location") or item.get("canonical_location"),
                ]
            )
            # Prefer the richer record while retaining one stable identity.
            for key, value in item.items():
                if target.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    target[key] = value
        if legacy_id and legacy_id != finding_id:
            aliases[finding_id].append(legacy_id)
    output: list[dict[str, Any]] = []
    for finding_id in sorted(merged):
        item = merged[finding_id]
        item["legacy_finding_ids"] = sorted(set(aliases[finding_id]))
        output.append(item)
    return output


def build_report_filename(base_stem: str, *, language: str | None, status: ReportStatus, extension: str) -> str:
    clean = _text(base_stem).replace(" ", "-")
    clean = re.sub(r"\.(pdf|html?|md|json|csv)$", "", clean, flags=re.IGNORECASE)
    status_pattern = "|".join(re.escape(token.value) for token in sorted(ReportStatus, key=lambda item: len(item.value), reverse=True))
    clean = re.sub(rf"(?:[-_.]*(?:{status_pattern}))+(?=$|[-_.])", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[-_.]+", "-", clean).strip("-")
    language_token = f"-{language}" if language and not clean.casefold().endswith(f"-{language}".casefold()) else ""
    filename = f"{clean}{language_token}-{status.value}.{extension.lstrip('.')}"
    terminal_count = sum(filename.upper().count(token.value) for token in ReportStatus)
    if terminal_count != 1:
        raise TruthViolation(f"Report filename has invalid terminal state: {filename}")
    return filename


@dataclass(frozen=True)
class FinalAssessmentTruthV1:
    payload: Mapping[str, Any]

    @classmethod
    def freeze(cls, source: Mapping[str, Any]) -> "FinalAssessmentTruthV1":
        payload = deepcopy(dict(source))
        identity = payload.get("assessment_identity") if isinstance(payload.get("assessment_identity"), Mapping) else payload.get("identity") or {}
        findings = payload.get("canonical_findings") or payload.get("decision_grade_findings_register") or payload.get("findings_register") or []
        payload["canonical_findings"] = canonicalize_findings(findings, identity)
        payload["ranked_risks"] = [item["finding_id"] for item in payload["canonical_findings"]]
        payload["limitations"] = _ordered_unique(payload.get("limitations") or [])
        payload["schema_version"] = VERSION
        payload["truth_sha256"] = _fingerprint({key: value for key, value in payload.items() if key != "truth_sha256"})
        cls._validate(payload)
        return cls(payload=payload)

    @staticmethod
    def _validate(payload: Mapping[str, Any]) -> None:
        findings = payload.get("canonical_findings") or []
        ids = [item.get("finding_id") for item in findings if isinstance(item, Mapping)]
        if len(ids) != len(set(ids)):
            raise TruthViolation("Canonical finding IDs are not unique")
        locations: set[tuple[str, Any, str, str]] = set()
        for item in findings:
            if not isinstance(item, Mapping):
                continue
            location = (
                _normalized_path(item.get("canonical_path")),
                item.get("canonical_symbol") or item.get("canonical_line") or item.get("line"),
                _text(item.get("category")).casefold(),
                _finding_title(item),
            )
            if location in locations and any(location[:2]):
                raise TruthViolation(f"Duplicate actionable finding location: {location}")
            locations.add(location)
            criteria = item.get("acceptance_criteria") or []
            keys = [_criterion_key(value) for value in criteria if isinstance(value, Mapping)]
            if len(keys) != len(set(keys)):
                raise TruthViolation(f"Duplicate acceptance criteria: {item.get('finding_id')}")
        technical = payload.get("technical_score")
        adjusted = payload.get("evidence_adjusted_score")
        if technical is not None and not 0 <= float(technical) <= 100:
            raise TruthViolation("Technical score is outside 0-100")
        if adjusted is not None and not 0 <= float(adjusted) <= 100:
            raise TruthViolation("Evidence-adjusted score is outside 0-100")

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self.payload))

    def assert_surface(self, surface: Mapping[str, Any]) -> None:
        expected = self.payload
        checks = {
            "technical_score": expected.get("technical_score"),
            "evidence_adjusted_score": expected.get("evidence_adjusted_score"),
            "limitation_count": len(expected.get("limitations") or []),
            "ranked_risks": expected.get("ranked_risks"),
            "approval_state": expected.get("approval_state"),
        }
        observed = {
            "technical_score": surface.get("technical_score"),
            "evidence_adjusted_score": surface.get("evidence_adjusted_score"),
            "limitation_count": surface.get("limitation_count"),
            "ranked_risks": surface.get("ranked_risks"),
            "approval_state": surface.get("approval_state"),
        }
        mismatches = {key: {"expected": checks[key], "observed": observed[key]} for key in checks if observed[key] != checks[key]}
        if mismatches:
            raise TruthViolation(f"Report surface contradicts frozen assessment truth: {mismatches}")


__all__ = [
    "EvidenceLocationType",
    "FinalAssessmentTruthV1",
    "ReportStatus",
    "TruthViolation",
    "build_report_filename",
    "canonical_finding_identity",
    "canonicalize_findings",
    "normalize_acceptance_criteria",
]
