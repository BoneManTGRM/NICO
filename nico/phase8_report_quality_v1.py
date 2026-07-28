from __future__ import annotations

import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

VERSION = "nico.phase8_report_quality.v1"
_GENERIC_TITLES = {
    "high-complexity code hotspot",
    "code complexity hotspot",
    "complexity hotspot",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _location(finding: Mapping[str, Any]) -> tuple[str, str]:
    location = finding.get("location")
    if isinstance(location, Mapping):
        path = location.get("path") or location.get("file") or location.get("file_path") or ""
        symbol = location.get("symbol") or location.get("line") or location.get("start_line") or ""
        return str(path).replace("\\", "/").lstrip("./"), str(symbol)
    if isinstance(location, str):
        match = re.match(r"^(.*?):(\d+)(?::\d+)?$", location.strip().replace("\\", "/"))
        if match:
            return match.group(1).lstrip("./"), match.group(2)
        return location.strip().replace("\\", "/").lstrip("./"), ""
    path = finding.get("canonical_path") or finding.get("file_path") or finding.get("path") or ""
    symbol = finding.get("canonical_symbol") or finding.get("symbol") or finding.get("canonical_line") or finding.get("line") or ""
    return str(path).replace("\\", "/").lstrip("./"), str(symbol)


def contextual_decision_title(finding: Mapping[str, Any]) -> str:
    current = _text(finding.get("decision_title") or finding.get("title") or finding.get("interpretation"))
    if current.casefold() not in _GENERIC_TITLES:
        return current
    path, symbol = _location(finding)
    if not path:
        return current
    stem = PurePosixPath(path).stem.replace("_", " ").replace("-", " ")
    area = " ".join(word.capitalize() for word in stem.split())
    location = f" at line {symbol}" if symbol.isdigit() else (f" in {symbol}" if symbol else "")
    return f"{area}{location} exceeds the approved complexity threshold"


def _criterion_records(values: Sequence[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        if isinstance(value, Mapping):
            candidates = [dict(value)]
        else:
            raw = _text(value)
            candidates = [{"statement": part.strip()} for part in raw.split(";") if part.strip()]
        for record in candidates:
            statement = _text(record.get("statement") or record.get("criterion") or record.get("text"))
            if not statement:
                continue
            # Renderer strings sometimes contain the same metadata annotation twice.
            statement = re.sub(r"(\s*\[method:[^\]]+\])(?:\s*\1)+", r"\1", statement, flags=re.IGNORECASE)
            method = _text(record.get("verification_method") or record.get("method") or "human_review")
            target = _text(record.get("target_commit") or record.get("commit_sha"))
            key = (statement.casefold(), method.casefold(), target.casefold())
            if key in seen:
                continue
            seen.add(key)
            normalized = dict(record)
            normalized["statement"] = statement
            normalized["verification_method"] = method
            normalized.setdefault("status", "pending")
            records.append(normalized)
    return records


def harden_report_findings(findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in findings:
        finding = deepcopy(dict(raw))
        title = contextual_decision_title(finding)
        finding["decision_title"] = title
        finding["title"] = title
        finding["acceptance_criteria"] = _criterion_records(finding.get("acceptance_criteria") or [])
        output.append(finding)
    return output


__all__ = ["VERSION", "contextual_decision_title", "harden_report_findings"]
