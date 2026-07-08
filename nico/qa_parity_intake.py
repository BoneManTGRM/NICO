from __future__ import annotations

import re
from typing import Any

PLATFORM_KEYWORDS = {
    "ios": ("ios", "iphone", "ipad", "app store"),
    "android": ("android", "pixel", "galaxy", "play store"),
    "web": ("web", "browser", "chrome", "safari", "firefox", "edge"),
    "mobile_web": ("mobile web", "responsive", "viewport"),
}

FLOW_KEYWORDS = {
    "authentication": ("login", "logout", "sign in", "sign out", "password", "account"),
    "onboarding": ("onboarding", "tutorial", "first run", "signup", "registration"),
    "payment_subscription": ("payment", "subscription", "billing", "checkout", "purchase"),
    "notifications": ("notification", "push", "email alert", "sms"),
    "settings_profile": ("settings", "profile", "preferences", "permission"),
    "core_workflow": ("create", "edit", "delete", "search", "upload", "download", "sync"),
    "error_recovery": ("error", "empty state", "offline", "retry", "timeout"),
}

BLOCKER_KEYWORDS = ("blocker", "critical", "crash", "data loss", "security", "payment failed", "cannot login", "release stop")


def _lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _combined_lines(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    rows: list[str] = []
    for key in keys:
        rows.extend(_lines(payload.get(key)))
    return rows


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def _platform_matrix(rows: list[str]) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for platform, words in PLATFORM_KEYWORDS.items():
        matches = [row for row in rows if _contains_any(row, words)]
        matrix[platform] = {
            "evidence_count": len(matches),
            "covered": bool(matches),
            "sample_evidence": matches[:6],
        }
    return matrix


def _flow_matrix(rows: list[str]) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for flow, words in FLOW_KEYWORDS.items():
        matches = [row for row in rows if _contains_any(row, words)]
        matrix[flow] = {
            "evidence_count": len(matches),
            "covered": bool(matches),
            "sample_evidence": matches[:6],
        }
    return matrix


def _explicit_status(row: str) -> str:
    lowered = row.lower()
    if re.search(r"\b(pass|passed|works|ok|green)\b", lowered):
        return "pass"
    if re.search(r"\b(fail|failed|broken|crash|error|red|bug)\b", lowered):
        return "fail"
    if re.search(r"\b(blocked|pending|unknown|untested|todo)\b", lowered):
        return "unknown"
    return "not_labeled"


def _status_counts(rows: list[str]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "unknown": 0, "not_labeled": 0}
    for row in rows:
        counts[_explicit_status(row)] += 1
    return counts


def _blockers(rows: list[str]) -> list[str]:
    return [row for row in rows if _contains_any(row, BLOCKER_KEYWORDS)]


def _acceptance_criteria(payload: dict[str, Any], flows: dict[str, dict[str, Any]]) -> list[str]:
    explicit = _combined_lines(payload, ("acceptance_criteria", "acceptance_notes", "done_definition"))
    if explicit:
        return explicit[:30]
    criteria = []
    for flow, data in flows.items():
        if data.get("covered"):
            criteria.append(f"{flow.replace('_', ' ').title()} has pass/fail evidence and reviewer signoff before client delivery.")
    return criteria[:30]


def build_qa_parity_intake(payload: dict[str, Any]) -> dict[str, Any]:
    qa_rows = _combined_lines(payload, ("qa_evidence", "qa_cases", "qa_notes", "test_results", "test_matrix"))
    parity_rows = _combined_lines(payload, ("parity_notes", "platform_parity", "device_matrix", "platform_matrix"))
    risk_rows = _combined_lines(payload, ("known_risks", "blockers", "release_blockers"))
    all_rows = qa_rows + parity_rows + risk_rows

    platform_matrix = _platform_matrix(parity_rows + qa_rows)
    flow_matrix = _flow_matrix(qa_rows)
    status_counts = _status_counts(qa_rows + parity_rows)
    blockers = _blockers(all_rows)
    acceptance = _acceptance_criteria(payload, flow_matrix)

    covered_platforms = sum(1 for item in platform_matrix.values() if item.get("covered"))
    covered_flows = sum(1 for item in flow_matrix.values() if item.get("covered"))
    qa_item_count = len(qa_rows)
    parity_item_count = len(parity_rows)

    score = 20
    score += min(25, qa_item_count * 3)
    score += min(20, parity_item_count * 4)
    score += min(15, covered_platforms * 4)
    score += min(15, covered_flows * 2)
    score += 5 if acceptance else 0
    score -= min(30, len(blockers) * 6)
    readiness_score = max(0, min(100, score))

    unavailable: list[str] = []
    if not qa_rows:
        unavailable.append("QA evidence is missing. Add pass/fail test cases, screenshots, videos, or reproduction notes.")
    if not parity_rows:
        unavailable.append("Platform parity evidence is missing. Add feature-by-feature iOS, Android, web, or mobile-web comparison notes.")
    if covered_platforms < 2:
        unavailable.append("At least two platform/device categories should have evidence before parity confidence is high.")
    if not acceptance:
        unavailable.append("Explicit acceptance criteria were not supplied; generated criteria require human review.")

    if blockers:
        status = "blocked_by_critical_qa_or_parity_item"
    elif readiness_score >= 75:
        status = "ready_for_human_qa_review"
    elif readiness_score >= 50:
        status = "partial_intake_needs_more_evidence"
    else:
        status = "incomplete_intake"

    return {
        "artifact_schema": "nico.qa_parity_intake.v1",
        "status": status,
        "readiness_score": readiness_score,
        "qa_item_count": qa_item_count,
        "parity_item_count": parity_item_count,
        "platforms_covered": covered_platforms,
        "flows_covered": covered_flows,
        "status_counts": status_counts,
        "platform_matrix": platform_matrix,
        "flow_matrix": flow_matrix,
        "acceptance_criteria": acceptance,
        "blockers": blockers[:30],
        "unavailable": unavailable,
        "summary": "Structured QA and parity intake converts supplied evidence into platform, flow, blocker, and acceptance-criteria signals. Final QA conclusions require human review.",
        "human_review_required": True,
    }
