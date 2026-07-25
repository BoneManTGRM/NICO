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
    raw = "" if value is None else str(value)
    normalized = " ".join(raw.split())
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
    return path
