from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

TERMINAL_STATES = (
    "FINAL-PENDING-APPROVAL",
    "FINAL-APPROVED",
    "DRAFT",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _location(value: Any) -> str:
    if isinstance(value, Mapping):
        path = value.get("path") or value.get("file") or value.get("file_path") or ""
        line = value.get("line") or value.get("start_line") or value.get("symbol") or ""
        return f"{path}:{line}".strip(":").replace("\\", "/").casefold()
    return _text(value).replace("\\", "/").casefold()


def _identity(finding: Mapping[str, Any]) -> tuple[str, str, str]:
    location = _location(
        finding.get("location")
        or finding.get("canonical_location")
        or finding.get("file_path")
        or finding.get("path")
    )
    title = _text(
        finding.get("decision_title")
        or finding.get("title")
        or finding.get("interpretation")
        or finding.get("summary")
    ).casefold()
    category = _text(finding.get("category")).casefold()
    return location, title, category


def _criterion_key(value: Any) -> str:
    if isinstance(value, Mapping):
        text = _text(
            value.get("criterion")
            or value.get("text")
            or value.get("description")
            or value.get("acceptance_criterion")
        )
        method = _text(value.get("method")).casefold()
        return f"{text.casefold()}|{method}"
    text = _text(value)
    # Remove duplicated trailing method annotations before comparison.
    text = re.sub(r"(?:\s*\[method:[^\]]+\])+\s*$", "", text, flags=re.I)
    return text.casefold()


def dedupe_acceptance_criteria(values: Any) -> Any:
    if not isinstance(values, list):
        return values
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = _criterion_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def normalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source in findings:
        finding = deepcopy(dict(source))
        for key in ("acceptance_criteria", "acceptance_tests", "verification_criteria"):
            if key in finding:
                finding[key] = dedupe_acceptance_criteria(finding.get(key))
        identity = _identity(finding)
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = finding
            result.append(finding)
            continue

        # Prefer the richer record while preserving a single stable identity.
        if len(str(finding)) > len(str(existing)):
            index = result.index(existing)
            stable_id = existing.get("finding_id") or existing.get("id")
            if stable_id:
                finding["finding_id"] = stable_id
            result[index] = finding
            by_identity[identity] = finding
    return result


def normalize_terminal_filename(filename: str, state: str = "FINAL-PENDING-APPROVAL") -> str:
    path = Path(filename)
    stem = path.stem
    terminal_pattern = "(?:" + "|".join(re.escape(item) for item in TERMINAL_STATES) + ")"
    stem = re.sub(rf"(?:-{terminal_pattern})+$", "", stem, flags=re.I)
    return f"{stem}-{state}{path.suffix}"


def contextual_decision_title(finding: Mapping[str, Any]) -> str:
    title = _text(finding.get("decision_title") or finding.get("title") or finding.get("interpretation"))
    if title.casefold() != "high-complexity code hotspot":
        return title
    location = _location(finding.get("location") or finding.get("file_path") or finding.get("path"))
    if "operations/page.tsx" in location:
        return "Operations interface complexity threatens safe product changes"
    if "spanish" in location and "report" in location:
        return "Spanish report-generation complexity threatens delivery reliability"
    if "retainer_evidence_ingestion" in location:
        return "Retainer evidence-ingestion complexity threatens traceability"
    if location:
        return f"Complexity hotspot in {location.split(':', 1)[0]}"
    return title


def normalize_report_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(payload))
    candidates = (
        normalized.get("canonical_findings")
        or normalized.get("findings_register")
        or normalized.get("decision_grade_findings_register")
        or []
    )
    findings = normalize_findings(item for item in candidates if isinstance(item, Mapping))
    for finding in findings:
        finding["decision_title"] = contextual_decision_title(finding)
    for key in (
        "canonical_findings",
        "findings_register",
        "decision_grade_findings_register",
        "executive_risk_register",
    ):
        normalized[key] = deepcopy(findings)
    normalized["ranked_risks"] = [item.get("finding_id") or item.get("id") for item in findings]
    return normalized
