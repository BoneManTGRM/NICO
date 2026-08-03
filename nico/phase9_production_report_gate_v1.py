from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from nico.comprehensive_client_ready_projection_v1 import APPROVAL_SUFFIX

VERSION = "nico.phase9_production_report_gate.v2"
_TERMINAL = (
    "AUTOMATED-DRAFT-PENDING-APPROVAL",
    "FINAL-PENDING-APPROVAL",
    "DRAFT",
    "FINAL",
    "APPROVED",
)
_PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|PLACEHOLDER|LOREM IPSUM)\b", re.IGNORECASE)
_GENERIC_TITLES = {"high-complexity code hotspot", "technical risk", "security issue", "dependency issue"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _path_line(finding: Mapping[str, Any]) -> tuple[str, str]:
    location = finding.get("location")
    if isinstance(location, Mapping):
        path = location.get("path") or location.get("file") or location.get("file_path")
        line = location.get("line") or location.get("start_line") or location.get("symbol")
        return _text(path).replace("\\", "/").lower(), _text(line).lower()
    raw = _text(location).replace("\\", "/")
    match = re.match(r"^(.*?):(\d+)(?::\d+)?$", raw)
    if match:
        return match.group(1).lower(), match.group(2)
    return raw.lower(), _text(finding.get("line") or "repository").lower()


def finding_semantic_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    path, line = _path_line(finding)
    category = _text(finding.get("category")).lower()
    title = _text(finding.get("decision_title") or finding.get("title") or finding.get("interpretation")).lower()
    return path, line, category, title


def acceptance_key(value: Any) -> str:
    if isinstance(value, Mapping):
        text = value.get("criterion") or value.get("text") or value.get("description") or value
    else:
        text = value
    normalized = _text(text).lower()
    normalized = re.sub(r"\s*\[method:[^\]]+\]", "", normalized)
    normalized = re.sub(r"\s*\[target commit:[^\]]+\]", "", normalized)
    return normalized.strip(" ;")


def normalized_filename(filename: str, approval_state: str) -> str:
    path = Path(filename)
    stem = path.stem
    for token in sorted(_TERMINAL, key=len, reverse=True):
        stem = re.sub(rf"(?:-{re.escape(token)})+$", "", stem, flags=re.IGNORECASE)
    state = _text(approval_state).upper() or APPROVAL_SUFFIX
    return f"{stem}-{state}{path.suffix}"


def _context_subject(path: str) -> str:
    file_path = Path(path)
    stem = file_path.stem.replace("_", " ").replace("-", " ").strip()
    parent = file_path.parent.name.replace("_", " ").replace("-", " ").strip()
    generic_stems = {"page", "index", "main", "app", "route", "handler", "utils", "helpers"}
    if stem.lower() in generic_stems and parent:
        return f"{parent} {stem}".strip()
    return stem or parent or "repository logic"


def contextual_title(finding: Mapping[str, Any]) -> str:
    title = _text(finding.get("decision_title") or finding.get("title") or finding.get("interpretation"))
    if title.lower() not in _GENERIC_TITLES:
        return title
    path, _ = _path_line(finding)
    symbol = _text(finding.get("symbol") or finding.get("function") or finding.get("component"))
    subject = symbol or _context_subject(path)
    if "complex" in title.lower():
        return f"{subject} has concentrated branching and elevated change risk"
    return f"{subject}: {title.lower()}"


def validate_production_report(report: Mapping[str, Any], *, filename: str | None = None) -> dict[str, Any]:
    findings = [item for item in report.get("canonical_findings") or report.get("findings_register") or [] if isinstance(item, Mapping)]
    semantic = [finding_semantic_key(item) for item in findings]
    duplicate_findings = [key for key, count in Counter(semantic).items() if count > 1]

    duplicate_acceptance: list[dict[str, Any]] = []
    generic_titles: list[str] = []
    placeholders: list[str] = []
    for finding in findings:
        criteria = finding.get("acceptance_criteria") or []
        if isinstance(criteria, str):
            criteria = [part for part in criteria.split(";") if part.strip()]
        keys = [acceptance_key(item) for item in criteria if acceptance_key(item)]
        repeated = [key for key, count in Counter(keys).items() if count > 1]
        if repeated:
            duplicate_acceptance.append({"finding_id": finding.get("finding_id") or finding.get("id"), "criteria": repeated})
        title = _text(finding.get("decision_title") or finding.get("title") or finding.get("interpretation"))
        if title.lower() in _GENERIC_TITLES:
            generic_titles.append(str(finding.get("finding_id") or finding.get("id") or title))
        rendered = _text(finding)
        if _PLACEHOLDER.search(rendered):
            placeholders.append(str(finding.get("finding_id") or finding.get("id") or "unknown"))

    surfaces = [report.get(name) for name in ("executive_summary", "limitations", "roadmap", "staffing_plan")]
    if _PLACEHOLDER.search(_text(surfaces)):
        placeholders.append("report-surface")

    approval_state = _text(report.get("approval_state") or APPROVAL_SUFFIX)
    filename_valid = True
    expected_filename = None
    if filename:
        expected_filename = normalized_filename(filename, approval_state)
        filename_valid = filename == expected_filename

    finality = _text(report.get("report_finality")).casefold()
    approval_status = _text(report.get("approval_status")).casefold()
    misleading_finality = approval_status == "pending_human_approval" and finality in {"final", "approved_final"}
    valid = not any((duplicate_findings, duplicate_acceptance, generic_titles, placeholders, misleading_finality)) and filename_valid
    return {
        "version": VERSION,
        "valid": valid,
        "finding_count": len(findings),
        "duplicate_finding_keys": duplicate_findings,
        "duplicate_acceptance": duplicate_acceptance,
        "generic_title_findings": generic_titles,
        "placeholder_findings": sorted(set(placeholders)),
        "misleading_unapproved_finality": misleading_finality,
        "filename_valid": filename_valid,
        "expected_filename": expected_filename,
    }


def assert_production_report(report: Mapping[str, Any], *, filename: str | None = None) -> dict[str, Any]:
    result = validate_production_report(report, filename=filename)
    if not result["valid"]:
        raise RuntimeError(f"Production report gate failed: {result}")
    return result
