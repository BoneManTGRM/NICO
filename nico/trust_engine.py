from __future__ import annotations

import re
from typing import Any

BANDIT_COUNT_RE = re.compile(r"Bandit(?: artifact)? reported\s+(?P<count>\d+)\s+finding", re.IGNORECASE)
OSV_RECORD_RE = re.compile(r"OSV returned\s+(?P<count>\d+)\s+vulnerability record", re.IGNORECASE)
MALFORMED_PYTHON_EXTRA_RE = re.compile(r"[A-Za-z0-9_.-]+@\[[^\]]+\]==[^\s:]+")


SECTION_CAPS = {
    "missing_required_scanner_artifacts": 74,
    "unresolved_dependency_findings": 74,
    "confirmed_dependency_vulnerabilities": 68,
    "untriaged_static_findings": 74,
    "secret_history_not_verified": 74,
    "release_readiness_blocked": 74,
}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section_text(section: dict[str, Any]) -> str:
    return "\n".join(_text(section.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _section_key(section: dict[str, Any]) -> str:
    return f"{section.get('id', '')} {section.get('label', '')}".lower()


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _cap_section(section: dict[str, Any], cap: int, reason: str, finding: str) -> dict[str, Any]:
    original_score = int(section.get("score") or 0)
    new_score = min(original_score, cap)
    section["score"] = new_score
    section["status"] = _status_from_score(new_score)
    section.setdefault("findings", [])
    section.setdefault("unavailable", [])
    _append_unique(section["findings"], finding)
    section.setdefault("trust_engine", {})["cap_applied"] = {
        "reason": reason,
        "previous_score": original_score,
        "max_allowed_score": cap,
        "new_score": new_score,
    }
    return section


def _remove_green_claims(text: str) -> str:
    value = str(text or "")
    replacements = [
        (r"\bcannot be GREEN\b", "cannot be VERIFIED"),
        (r"\bcannot receive GREEN\b", "cannot receive verified"),
        (r"\bis green\b", "requires verified evidence"),
        (r"\bgreen from\b", "review-limited from"),
        (r"\bthe green score\b", "the review-limited score"),
        (r"\bgreen score\b", "review-limited score"),
        (r"\bGREEN\b", "VERIFIED"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


def _has_any(text: str, *needles: str) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def _dependency_rule(section: dict[str, Any]) -> dict[str, Any] | None:
    text = _section_text(section)
    lower = text.lower()
    if not _has_any(_section_key(section), "dependency", "library"):
        return None
    has_osv_records = bool(OSV_RECORD_RE.search(text)) or "completed_with_findings" in lower
    has_malformed_extra = bool(MALFORMED_PYTHON_EXTRA_RE.search(text)) or "osv query normalization required" in lower
    missing_scanners = _has_any(text, "pip-audit", "npm-audit", "npm audit", "osv-scanner", "osv scanner") and _has_any(
        text,
        "unavailable",
        "not attached",
        "not verified",
        "still required",
        "missing",
    )
    if has_osv_records or has_malformed_extra or missing_scanners:
        confirmed_exact = has_osv_records and not has_malformed_extra and "pyjwt@[" not in lower
        reason = "confirmed_dependency_vulnerabilities" if confirmed_exact else "unresolved_dependency_findings"
        section["summary"] = (
            "Dependency review is review-limited: dependency scanner proof is missing, malformed OSV evidence exists, or unresolved OSV findings remain. "
            "This section cannot be GREEN until current-run pip-audit, npm audit, and OSV evidence are attached and clean or formally triaged."
        )
        return _cap_section(
            section,
            SECTION_CAPS[reason],
            reason,
            "Strict trust engine: Dependency cannot be GREEN while OSV findings, malformed OSV evidence, or missing dependency scanner artifacts remain.",
        )
    return None


def _static_rule(section: dict[str, Any]) -> dict[str, Any] | None:
    text = _section_text(section)
    if "static" not in _section_key(section):
        return None
    match = BANDIT_COUNT_RE.search(text)
    bandit_count = int(match.group("count")) if match else 0
    untriaged = bandit_count > 0 and _has_any(text, "review_required_count", "requires explicit triage", "needs_human_review", "untriaged")
    missing_scanners = _has_any(text, "bandit", "semgrep", "eslint", "typescript") and _has_any(
        text,
        "unavailable",
        "not attached",
        "not verified",
        "missing",
    )
    if untriaged or missing_scanners:
        count_text = f" Bandit reported {bandit_count} finding(s)." if bandit_count else ""
        section["summary"] = (
            "Static analysis is review-limited: required scanner-worker proof or approved rule-level triage is missing."
            f"{count_text} This section cannot be GREEN until Bandit/Semgrep/ESLint/TypeScript evidence is attached and clean or formally triaged."
        )
        return _cap_section(
            section,
            SECTION_CAPS["untriaged_static_findings"],
            "untriaged_static_findings",
            "Strict trust engine: Static Analysis cannot be GREEN while scanner-worker artifacts are missing or Bandit findings require review.",
        )
    return None


def _secrets_rule(section: dict[str, Any]) -> dict[str, Any] | None:
    text = _section_text(section)
    if "secret" not in _section_key(section):
        return None
    history_not_verified = _has_any(text, "full git-history secret coverage is not verified", "full-history coverage", "gitleaks", "trufflehog") and _has_any(
        text,
        "unavailable",
        "not verified",
        "separate evidence sources",
        "not attached",
    )
    if history_not_verified:
        section["summary"] = (
            "Secrets review is review-limited: attached clean credential evidence is useful, but full-history live gitleaks/trufflehog proof is missing. "
            "This section cannot be GREEN until full-history secret scanning is attached for this report run."
        )
        return _cap_section(
            section,
            SECTION_CAPS["secret_history_not_verified"],
            "secret_history_not_verified",
            "Strict trust engine: Secrets cannot be GREEN while full-history secret coverage is unavailable or unverified.",
        )
    return None


def _velocity_rule(section: dict[str, Any]) -> dict[str, Any] | None:
    text = _section_text(section)
    if "velocity" not in _section_key(section) and "complexity" not in _section_key(section):
        return None
    release_blocked = _has_any(text, "release-readiness lift not applied", "final-clean evidence is incomplete")
    missing_complexity = _has_any(text, "deeper complexity analysis", "missing runtime artifacts")
    if release_blocked or missing_complexity:
        section["summary"] = (
            "Velocity / Complexity is review-limited: traceability and velocity evidence are useful, but release-readiness or deeper complexity proof is incomplete. "
            "This section cannot be GREEN until final-clean dependency/static evidence and complexity evidence are attached."
        )
        return _cap_section(
            section,
            SECTION_CAPS["release_readiness_blocked"],
            "release_readiness_blocked",
            "Strict trust engine: Velocity / Complexity cannot be GREEN while release-readiness blockers or missing complexity evidence remain.",
        )
    return None


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [
        item
        for item in result.get("sections", []) or []
        if isinstance(item, dict)
        and item.get("status") != "gray"
        and item.get("supplemental") is not True
        and int(item.get("scoring_weight", 1) or 0) != 0
    ]
    if not sections:
        return
    score = round(sum(int(section.get("score") or 0) for section in sections) / len(sections))
    level = "Senior" if score >= 82 else ("Mid" if score >= 58 else "Junior")
    result["maturity_signal"] = {
        "level": level,
        "score": score,
        "summary": "Trust-engine adjusted maturity score computed after strict section proof caps.",
    }
    result["maturity_semaphore"] = {section.get("label", section.get("id", "Section")): section.get("status") for section in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level
    if isinstance(result.get("project_trend_evidence"), dict):
        result["project_trend_evidence"]["current_score"] = score


def apply_strict_trust_engine(result: dict[str, Any]) -> dict[str, Any]:
    """Apply strict no-green-without-proof rules to the final report state.

    This is not a scoring booster. It is a trust boundary. It downgrades sections
    that look green while the same section discloses missing scanner proof,
    unresolved findings, or unverified coverage.
    """

    if result.get("status") != "complete":
        return result
    violations: list[dict[str, Any]] = []
    rules = (_dependency_rule, _static_rule, _secrets_rule, _velocity_rule)
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        before_score = int(section.get("score") or 0)
        before_status = str(section.get("status") or "")
        for rule in rules:
            rule(section)
        if int(section.get("score") or 0) != before_score or str(section.get("status") or "") != before_status:
            cap = section.get("trust_engine", {}).get("cap_applied", {}) if isinstance(section.get("trust_engine"), dict) else {}
            violations.append(
                {
                    "section": section.get("label") or section.get("id"),
                    "reason": cap.get("reason", "strict_trust_rule"),
                    "previous_score": before_score,
                    "new_score": int(section.get("score") or 0),
                    "previous_status": before_status,
                    "new_status": section.get("status"),
                }
            )
        if section.get("status") != "green":
            section["summary"] = _remove_green_claims(str(section.get("summary") or ""))

    _recompute_maturity(result)
    trust_level = "Review-limited" if violations else "Evidence-bound"
    result["trust_engine"] = {
        "version": "strict-trust-engine-v1",
        "status": "applied",
        "trust_level": trust_level,
        "violations": violations,
        "rules": [
            "dependency_not_green_without_current_dependency_scanner_proof",
            "static_not_green_without_scanner_artifacts_and_triage",
            "secrets_not_green_without_full_history_secret_scan",
            "velocity_not_green_with_release_readiness_or_complexity_blockers",
            "maturity_recomputed_after_trust_caps",
        ],
    }
    result["trust_level"] = trust_level
    if violations:
        result["delivery_verdict"] = "human_review_required"
        warnings = list(result.get("warnings") or [])
        _append_unique(
            warnings,
            "Strict trust engine downgraded one or more green sections because required proof was missing or findings were unresolved.",
        )
        result["warnings"] = warnings
    return result
