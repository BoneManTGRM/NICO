from __future__ import annotations

import base64
import csv
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from typing import Any, Iterable


VERSION = "nico.comprehensive_decision_grade.v5"
APPENDIX_HEADING = "## Evidence Appendix"
REVIEW_HEADING = "## Human Review and Acceptance Gate"

_TOOL_CATEGORY = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
}

_SCORE_BANDS = (
    (90, "exceptional", "EXCEPTIONAL", "green"),
    (80, "strong", "STRONG", "green"),
    (70, "moderate", "MODERATE", "yellow"),
    (55, "weak", "WEAK", "red"),
    (0, "critical", "CRITICAL", "red"),
)


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _bounded_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _score_band(score: Any) -> dict[str, Any]:
    if not isinstance(score, (int, float)):
        return {
            "score_band": "not_scored",
            "score_band_label": "NOT SCORED",
            "score_tone": "gray",
        }
    bounded = max(0, min(100, int(score)))
    for threshold, key, label, tone in _SCORE_BANDS:
        if bounded >= threshold:
            return {
                "score_band": key,
                "score_band_label": label,
                "score_tone": tone,
            }
    raise AssertionError("score band table is incomplete")


def _assurance(status: Any, *, scored: bool = True) -> dict[str, str]:
    normalized = _text(status, 40).casefold()
    if normalized == "supplemental":
        return {"assurance_status": "supplemental", "assurance_label": "SUPPLEMENTAL", "assurance_tone": "blue"}
    if not scored or normalized in {"gray", "not_scored", "pending", "review_required"}:
        return {"assurance_status": "human_review_pending", "assurance_label": "HUMAN REVIEW PENDING", "assurance_tone": "gray"}
    if normalized == "green":
        return {"assurance_status": "verified", "assurance_label": "VERIFIED", "assurance_tone": "green"}
    if normalized == "yellow":
        return {"assurance_status": "review_limited", "assurance_label": "REVIEW LIMITED", "assurance_tone": "yellow"}
    return {"assurance_status": "blocked", "assurance_label": "BLOCKED", "assurance_tone": "red"}


def _category_counts(scan: dict[str, Any], category: str) -> dict[str, int]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    by_category = summary.get("by_category") if isinstance(summary.get("by_category"), dict) else {}
    raw = by_category.get(category) if isinstance(by_category.get(category), dict) else {}
    return {
        "raw": _bounded_int(raw.get("raw")),
        "material": _bounded_int(raw.get("material")),
        "review_required": _bounded_int(raw.get("review_required")),
        "approved_or_nonblocking": _bounded_int(raw.get("approved_or_nonblocking")),
        "excluded_test_only": _bounded_int(raw.get("excluded_test_only")),
    }


def _tools_for_category(values: Iterable[Any], category: str) -> list[str]:
    return sorted(
        {
            _text(value, 80).casefold()
            for value in values
            if _TOOL_CATEGORY.get(_text(value, 80).casefold()) == category
        }
    )


def _result_category(item: dict[str, Any]) -> str:
    direct = _text(item.get("category"), 40).casefold()
    return direct or _TOOL_CATEGORY.get(_text(item.get("tool") or item.get("scanner"), 80).casefold(), "unknown")


def _finding_location(finding: dict[str, Any]) -> str:
    path = _text(
        finding.get("file_path")
        or finding.get("filename")
        or finding.get("path")
        or finding.get("filePath"),
        260,
    )
    line = finding.get("line") or finding.get("line_number") or finding.get("start_line")
    if isinstance(line, (int, float)) and path:
        return f"{path}:{int(line)}"
    return path or "Location not retained by the scanner result."


def _finding_message(finding: dict[str, Any], category: str) -> str:
    if category == "secret":
        return "Potential secret candidate requires human triage; raw credential material is intentionally omitted."
    for key in ("title", "message", "description", "check_id", "rule_id", "id", "name"):
        value = _text(finding.get(key), 360)
        if value:
            return value
    package = _text(finding.get("package") or finding.get("dependency"), 160)
    return f"{category.title()} analyzer candidate" + (f" affecting {package}" if package else "")


def _severity(finding: dict[str, Any]) -> str:
    values = [
        finding.get("severity"),
        finding.get("issue_severity"),
        finding.get("level"),
        finding.get("confidence"),
    ]
    extra = finding.get("extra") if isinstance(finding.get("extra"), dict) else {}
    database_specific = finding.get("database_specific") if isinstance(finding.get("database_specific"), dict) else {}
    values.extend((extra.get("severity"), database_specific.get("severity")))
    text = " ".join(_text(value, 80).casefold() for value in values)
    if "critical" in text:
        return "critical"
    if "high" in text or "error" in text:
        return "high"
    if "medium" in text or "moderate" in text or "warning" in text:
        return "medium"
    if "low" in text or "info" in text:
        return "low"
    return "unknown"


def _priority(severity: str, *, material: bool = False, operational: bool = False) -> str:
    if material or severity in {"critical", "high"}:
        return "P0"
    if operational or severity in {"medium", "unknown"}:
        return "P1"
    return "P2"


def _owner(category: str) -> str:
    return {
        "secret": "Security Engineer",
        "dependency": "Senior Product Engineer",
        "static": "Senior Product Engineer",
        "architecture": "Product Engineering Architect",
        "ci_cd": "Platform Engineer",
        "code": "Senior Product Engineer",
        "evidence": "Product Quality Engineer",
    }.get(category, "Product Engineering Architect")


def _recommendation(category: str) -> tuple[str, str, str]:
    values = {
        "secret": (
            "Validate the candidate against the exact file and revision, revoke any live credential, remove it from history where required, and add a prevention rule.",
            "S-M",
            "Candidate disposition is recorded; any live credential is rotated; the exact-SHA rescan returns no unresolved material secret.",
        ),
        "dependency": (
            "Confirm exploitability and affected version, upgrade or constrain the dependency, regenerate the lockfile, and rerun all dependency analyzers.",
            "S-M",
            "The exact-SHA dependency scan completes with the candidate resolved or explicitly accepted with rationale and expiry.",
        ),
        "static": (
            "Inspect the exact code path, correct the unsafe pattern or document a bounded exception, then rerun the originating analyzer.",
            "S-M",
            "The originating analyzer completes on the exact SHA and the finding is resolved or approved with a traceable rationale.",
        ),
        "architecture": (
            "Decompose the hotspot into bounded modules, add characterization tests, and enforce complexity and change-size thresholds in CI.",
            "M-L",
            "Target functions fall below the approved complexity threshold and behavior remains covered by automated tests.",
        ),
        "ci_cd": (
            "Classify non-success runs by cause, remove recurrent failures, and publish a rolling reliability trend separated from expected cancellations.",
            "M",
            "The last two retained acceptance windows meet the approved CI success threshold with no unexplained recurring failure class.",
        ),
        "code": (
            "Retain exact locations for bounded code-risk hits, triage each hit, remediate unsafe patterns, and rerun against the same immutable revision.",
            "S-M",
            "Every sampled hit has a file/line disposition and the rerun reports no unresolved material code-risk pattern.",
        ),
        "evidence": (
            "Repair the analyzer or worker resource boundary and rerun two consecutive exact-SHA evidence passes.",
            "M",
            "All required analyzers complete twice against the same SHA and retained artifacts contain no raw secrets.",
        ),
    }
    return values.get(category, values["evidence"])


def _record(
    *,
    record_id: str,
    priority: str,
    category: str,
    title: str,
    impact: str,
    confidence: str,
    evidence: str,
    location: str,
    recommendation: str | None = None,
    effort: str | None = None,
    owner_role: str | None = None,
    acceptance: str | None = None,
) -> dict[str, str]:
    default_recommendation, default_effort, default_acceptance = _recommendation(category)
    return {
        "id": record_id,
        "priority": priority,
        "category": category,
        "title": _text(title, 320),
        "impact": _text(impact, 520),
        "confidence": _text(confidence or "moderate", 40).lower(),
        "evidence": _text(evidence, 700),
        "location": _text(location, 320),
        "recommendation": _text(recommendation or default_recommendation, 700),
        "effort": _text(effort or default_effort, 40),
        "owner_role": _text(owner_role or _owner(category), 120),
        "acceptance_criteria": _text(acceptance or default_acceptance, 700),
    }


def _scanner_register(scan: dict[str, Any], limit: int = 24) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    results = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    for result_index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        tool = _text(item.get("tool") or item.get("scanner") or "unknown", 80).casefold()
        category = _result_category(item)
        status = _text(item.get("status"), 40).casefold()
        if status in {"failed", "error", "timeout", "unavailable"}:
            reason = _text(item.get("reason") or item.get("error") or f"{tool} did not complete.", 420)
            output.append(
                _record(
                    record_id=f"scanner-operational-{result_index}",
                    priority="P1",
                    category="evidence",
                    title=f"{tool} evidence unavailable",
                    impact="The affected control cannot reach verified assurance because the required analyzer did not complete.",
                    confidence="high",
                    evidence=f"Analyzer status={status or 'unknown'}; {reason}",
                    location="Scanner execution boundary",
                )
            )
        findings = item.get("findings") if isinstance(item.get("findings"), list) else []
        for finding_index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                continue
            severity = _severity(finding)
            verified = bool(finding.get("Verified") or finding.get("verified")) if category == "secret" else severity in {"critical", "high"}
            title = _finding_message(finding, category)
            output.append(
                _record(
                    record_id=f"scanner-{tool}-{result_index}-{finding_index}",
                    priority=_priority(severity, material=verified),
                    category=category,
                    title=title,
                    impact=(
                        "A verified or high-severity scanner result may create direct security or reliability exposure."
                        if verified
                        else "The candidate requires human disposition before the control can be treated as verified."
                    ),
                    confidence="high" if verified else "moderate",
                    evidence=f"tool={tool}; category={category}; severity={severity}; verified={verified}",
                    location=_finding_location(finding),
                )
            )
            if len(output) >= limit:
                return output
    return output


def _complexity_register(complexity: dict[str, Any], limit: int = 8) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    hotspots = complexity.get("hotspots") if isinstance(complexity.get("hotspots"), list) else []
    for index, hotspot in enumerate(hotspots[:limit], start=1):
        if not isinstance(hotspot, dict):
            continue
        path = _text(hotspot.get("path"), 260) or "Sampled source file"
        line = _bounded_int(hotspot.get("line"), 0)
        name = _text(hotspot.get("name"), 160) or "measured code region"
        complexity_value = _bounded_int(hotspot.get("cyclomatic_complexity"), 0)
        loc = _bounded_int(hotspot.get("loc"), 0)
        location = f"{path}:{line}" if line else path
        output.append(
            _record(
                record_id=f"architecture-hotspot-{index}",
                priority="P1" if complexity_value >= 40 else "P2",
                category="architecture",
                title=f"Complexity hotspot: {name}",
                impact="Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.",
                confidence="moderate" if _text(hotspot.get("language"), 80) == "javascript-typescript" else "high",
                evidence=f"cyclomatic_complexity={complexity_value}; loc={loc}; grade={_text(hotspot.get('grade'), 20) or 'unknown'}; method={_text(hotspot.get('method'), 120)}",
                location=location,
            )
        )
    return output


def _dedupe_records(records: Iterable[dict[str, str]], limit: int = 40) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for record in sorted(records, key=lambda item: (order.get(item.get("priority", "P3"), 9), item.get("category", ""), item.get("id", ""))):
        key = (
            _text(record.get("title"), 320).casefold(),
            _text(record.get("location"), 320).casefold(),
            _text(record.get("category"), 80).casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
        if len(output) >= limit:
            break
    return output


def _section(
    section_id: str,
    label: str,
    score: int | None,
    summary: str,
    evidence: list[str],
    findings: list[str] | None = None,
    unavailable: list[str] | None = None,
    *,
    material_count: int = 0,
) -> dict[str, Any]:
    findings = [item for item in (findings or []) if _text(item)]
    unavailable = [item for item in (unavailable or []) if _text(item)]
    if score is None:
        status = "gray"
        band = _score_band(None)
        assurance = _assurance(status, scored=False)
        return {
            "id": section_id,
            "label": label,
            "score": None,
            "source_score": None,
            "presented_score": None,
            "score_value": None,
            "status": status,
            "presented_status": status,
            "exclude_from_maturity": True,
            "summary": summary,
            "evidence": evidence,
            "findings": findings,
            "unavailable": unavailable,
            **band,
            **assurance,
        }
    bounded = max(0, min(100, int(score)))
    status = "red" if material_count else "yellow" if findings or unavailable else "green"
    band = _score_band(bounded)
    assurance = _assurance(status)
    return {
        "id": section_id,
        "label": label,
        "score": bounded,
        "source_score": bounded,
        "presented_score": bounded,
        "score_value": bounded,
        "status": status,
        "presented_status": status,
        "summary": summary,
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
        **band,
        **assurance,
    }



__all__ = ["VERSION", "APPENDIX_HEADING", "REVIEW_HEADING", "_TOOL_CATEGORY", "_text", "_bounded_int", "_score_band", "_assurance", "_category_counts", "_tools_for_category", "_result_category", "_finding_location", "_finding_message", "_severity", "_priority", "_owner", "_recommendation", "_record", "_scanner_register", "_complexity_register", "_dedupe_records", "_section"]
