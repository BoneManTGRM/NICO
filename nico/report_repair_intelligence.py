from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from nico.code_repair_suggestions import REPORT_ONLY_CODE_POLICY, build_code_suggestion

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_HIGH_RISK_CATEGORIES = {"secret_exposure", "command_execution", "transport_security", "unsafe_deserialization"}
_CATEGORY_BLAST_RADIUS = {
    "secret_exposure": 95,
    "command_execution": 92,
    "transport_security": 86,
    "unsafe_deserialization": 82,
    "dependency_risk": 72,
    "security_configuration": 62,
    "runtime_patch_surface": 58,
    "repository_hygiene": 52,
    "delivery_reliability": 52,
    "maintainability": 56,
    "architecture_debt": 56,
    "key_person_risk": 48,
    "documentation_drift": 38,
    "code_quality": 55,
    "static_analysis": 64,
}
_CATEGORY_EFFORT = {
    "runtime_patch_surface": "high",
    "maintainability": "high",
    "architecture_debt": "high",
    "dependency_risk": "medium",
    "repository_hygiene": "medium",
    "delivery_reliability": "medium",
    "key_person_risk": "medium",
    "documentation_drift": "low",
    "security_configuration": "low",
    "secret_exposure": "medium",
    "command_execution": "medium",
    "transport_security": "medium",
}
_ADVISORY_MARKERS = (
    "source-file footprint is large",
    "total source loc is high for an express review",
    "repository size is not scored as technical debt by itself",
    "size alone does not reduce maintainability score",
)
_COMPLEXITY_AGGREGATE_MARKERS = (
    "at least one function has very high cyclomatic complexity",
    "function-level complexity risk is concentrated",
    "complexity and high churn overlap",
    "large-file and complexity risk overlap",
)


def _text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"\b(max_function_cyclomatic|density)=None\b", r"\1=unavailable", text)
    return text


def _severity(value: Any, text: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _SEVERITY_ORDER:
        return normalized
    lower = text.lower()
    if any(token in lower for token in ("credential exposure", "private key", "data loss", "remote code execution", "command injection")):
        return "critical"
    if any(token in lower for token in (
        "confirmed vulnerability",
        "vulnerability record",
        "disabled tls",
        "branch inventory",
        "runtime patch",
        "import-order fragility",
        "security exposure",
    )):
        return "high"
    if any(token in lower for token in (
        "dependabot",
        "documentation",
        "drift",
        "missing",
        "fragility",
        "complexity",
        "hotspot",
        "churn",
        "ownership",
        "key-person",
        "risk",
    )):
        return "medium"
    return "low"


def _confidence_label(value: Any) -> str:
    numeric = _confidence_numeric(value)
    if numeric >= 0.85:
        return "high"
    if numeric >= 0.6:
        return "medium"
    return "low"


def _confidence_numeric(value: Any) -> float:
    if isinstance(value, str):
        return {"high": 0.9, "medium": 0.72, "low": 0.45}.get(value.lower(), 0.72)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.72


def _id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"repair_candidate_{digest}"


def _exploitability_score(value: Any) -> float:
    normalized = str(value or "unknown").strip().lower()
    return {
        "none": 5.0,
        "low": 20.0,
        "unknown": 35.0,
        "medium": 60.0,
        "high": 85.0,
        "critical": 95.0,
    }.get(normalized, 35.0)


def _priority_score(
    *,
    category: str,
    severity: str,
    confidence: float,
    exploitability: str,
    verification_available: bool,
    recurrence: int = 0,
) -> dict[str, Any]:
    severity_score = {"info": 10.0, "low": 25.0, "medium": 50.0, "high": 75.0, "critical": 95.0}.get(severity, 25.0)
    blast_radius = float(_CATEGORY_BLAST_RADIUS.get(category, 48))
    verification_score = 72.0 if verification_available else 38.0
    recurrence_bonus = min(8.0, max(0, recurrence) * 2.0)
    score = round(
        min(
            100.0,
            severity_score * 0.42
            + _exploitability_score(exploitability) * 0.18
            + blast_radius * 0.18
            + confidence * 100.0 * 0.12
            + verification_score * 0.10
            + recurrence_bonus,
        ),
        1,
    )
    priority = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low"
    return {
        "score": score,
        "priority": priority,
        "why_this_ranks_above_others": (
            f"Weighted evidence: severity={severity}, exploitability={exploitability}, blast radius={int(blast_radius)}, "
            f"confidence={round(confidence, 2)}, verification={'available' if verification_available else 'limited'}, recurrence={recurrence}."
        ),
    }


def _tgrm_level(priority_score: float, category: str) -> dict[str, Any]:
    if priority_score >= 78 or category in _HIGH_RISK_CATEGORIES:
        return {
            "level": 3,
            "label": "TGRM-3 strong containment and verified repair",
            "scope": "Contain exposure, apply the bounded repair, run focused and full verification, and preserve rollback evidence.",
        }
    if priority_score >= 48:
        return {
            "level": 2,
            "label": "TGRM-2 bounded structural repair",
            "scope": "Apply a reviewable multi-step repair with regression coverage and explicit rollback.",
        }
    return {
        "level": 1,
        "label": "TGRM-1 minimal targeted repair",
        "scope": "Use the smallest reversible change that resolves the verified issue.",
    }


def _effort(category: str, finding: dict[str, Any]) -> str:
    explicit = str(finding.get("effort") or "").strip().lower()
    if explicit in {"low", "medium", "high"}:
        return explicit
    return _CATEGORY_EFFORT.get(category, "medium")


def _repair_options(recommendation: str, verification: str) -> list[dict[str, str]]:
    recommendation = _text(recommendation) or "Apply the smallest evidence-supported defensive repair."
    verification = _text(verification) or "Run focused tests and rescan the affected area."
    return [
        {
            "type": "minimal",
            "goal": "Stop the verified failure or exposure with the smallest reversible change.",
            "action": recommendation,
            "verification": verification,
        },
        {
            "type": "moderate",
            "goal": "Repair the issue and add focused regression, observability, or policy coverage.",
            "action": recommendation + " Add the smallest relevant regression test and evidence capture.",
            "verification": verification + " Confirm the finding does not recur in the next bounded scan.",
        },
        {
            "type": "strong",
            "goal": "Repair the issue and reduce recurrence across the affected capability family.",
            "action": recommendation + " Review adjacent call sites or configurations that share the same root cause.",
            "verification": verification + " Run the full suite, production build, and authorized smoke verification before approval.",
        },
    ]


def _candidate_from_structured(finding: dict[str, Any]) -> dict[str, Any]:
    title = _text(finding.get("title") or finding.get("code") or "Repair candidate")
    category = _text(finding.get("category") or finding.get("code") or "technical_risk").lower()
    severity = _severity(finding.get("severity"), title)
    confidence_numeric = _confidence_numeric(finding.get("confidence"))
    evidence = [_text(item) for item in finding.get("evidence", []) or [] if _text(item)]
    affected_files = [_text(item) for item in finding.get("affected_files", []) or [] if _text(item)]
    business_impact = _text(finding.get("business_impact")) or "The finding may increase delivery, incident, or maintenance cost."
    technical_impact = _text(finding.get("technical_impact")) or "The finding indicates a bounded technical risk requiring review."
    recommendation = _text(finding.get("recommendation")) or "Apply the smallest evidence-supported repair."
    verification = _text(finding.get("verification_method")) or "Run focused tests and rescan the affected area."
    exploitability = _text(finding.get("exploitability") or "low").lower()
    priority = _priority_score(
        category=category,
        severity=severity,
        confidence=confidence_numeric,
        exploitability=exploitability,
        verification_available=bool(verification),
        recurrence=int(finding.get("recurrence") or 0),
    )
    score = float(priority.get("score") or 0)
    tgrm = _tgrm_level(score, category)
    code_suggestion = build_code_suggestion(
        category=category,
        issue=title,
        evidence=evidence,
        affected_files=affected_files,
    )
    return {
        "candidate_id": _id(category, title, "|".join(affected_files)),
        "title": title,
        "category": category,
        "severity": severity,
        "impact": business_impact,
        "technical_impact": technical_impact,
        "exploitability": exploitability,
        "confidence": _confidence_label(confidence_numeric),
        "confidence_numeric": confidence_numeric,
        "priority_score": score,
        "priority": priority.get("priority"),
        "priority_explanation": priority.get("why_this_ranks_above_others"),
        "effort": _effort(category, finding),
        "tgrm": tgrm,
        "evidence": evidence,
        "affected_files": affected_files,
        "root_cause_hypothesis": _text(finding.get("root_cause_hypothesis")) or technical_impact,
        "recommended_action": recommendation,
        "repair_options": _repair_options(recommendation, verification),
        "code_suggestion": code_suggestion,
        "test_plan": [verification],
        "rollback_plan": (
            "Revert only the approved repair change if focused or full verification fails, preserve the failing evidence, "
            "and return the candidate to human review."
        ),
        "cost_avoidance": (
            "Qualitative only: resolving this finding may reduce incident response, repeated debugging, review, or "
            "maintenance effort. NICO does not fabricate a dollar savings estimate without client cost data."
        ),
        "status": "report_only_unverified_candidate",
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
        "verified_fix": False,
    }


def _generic_finding(section: dict[str, Any], finding_text: str) -> dict[str, Any]:
    section_id = str(section.get("id") or "technical_risk")
    lower = finding_text.lower()
    category = {
        "dependency_health": "dependency_risk",
        "secrets_review": "secret_exposure",
        "static_analysis": "static_analysis",
        "ci_cd": "delivery_reliability",
        "architecture_debt": "architecture_debt",
        "velocity_complexity": "maintainability",
        "code_audit": "code_quality",
    }.get(section_id, section_id)
    severity = _severity("", finding_text)
    impact = "The finding may increase engineering time, release risk, or incident cost."
    recommendation = "Collect the exact affected file and failing evidence, then apply the smallest reversible repair."
    verification = "Run the smallest relevant test, the full suite, and a NICO rescan."
    exploitability = "unknown"
    effort = "medium"

    if "historical workflow reliability" in lower:
        category = "delivery_reliability"
        severity = "low"
        impact = "Repeated CI failures and avoidable retries consume engineering time and weaken release confidence."
        recommendation = "Classify non-success runs by root cause, ignore superseded cancellations, and eliminate repeat failure classes before changing release policy."
        verification = "Compare the next 20 relevant workflow runs and confirm repeat failure classes decline without weakening required checks."
        exploitability = "low"
        effort = "medium"
    elif "ownership is concentrated" in lower:
        category = "key_person_risk"
        severity = "medium"
        impact = "Single-person ownership can delay review, incident response, and knowledge transfer."
        recommendation = "Add backup reviewers, bounded CODEOWNERS coverage, and operational runbooks for the highest-risk modules."
        verification = "Confirm critical paths have at least two qualified reviewers and that a second engineer can execute the documented release and recovery steps."
        exploitability = "low"
        effort = "medium"
    elif "vulnerability record" in lower or "dependency tools reported" in lower:
        category = "dependency_risk"
        severity = "high" if "vulnerability record" in lower else "medium"
        impact = "An unresolved dependency advisory can expose production behavior or block client-clean release claims."
        recommendation = "Resolve the exact affected package and installed version, upgrade or formally triage non-applicability, then rerun all dependency scanners."
        verification = "Require current-run pip-audit, npm audit, and OSV evidence to agree that the advisory is cleared or formally non-applicable."
        exploitability = "medium"
        effort = "medium"

    return {
        "code": f"{section_id}_finding",
        "title": finding_text,
        "severity": severity,
        "confidence": 0.72,
        "category": category,
        "evidence": [finding_text],
        "affected_files": [],
        "business_impact": impact,
        "technical_impact": finding_text,
        "recommendation": recommendation,
        "verification_method": verification,
        "exploitability": exploitability,
        "effort": effort,
    }


def _is_advisory(title: str) -> bool:
    lower = title.lower()
    return any(marker in lower for marker in _ADVISORY_MARKERS)


def _complexity_group(findings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not findings:
        return None
    evidence: list[str] = []
    affected_files: list[str] = []
    has_churn_overlap = False
    for item in findings:
        title = _text(item.get("title"))
        if title and title not in evidence:
            evidence.append(title)
        if "churn overlap" in title.lower():
            has_churn_overlap = True
        match = re.search(r"Complexity hotspot:\s*([^\s,]+)", title, flags=re.IGNORECASE)
        if match and match.group(1) not in affected_files:
            affected_files.append(match.group(1))
    return {
        "code": "complexity_concentration",
        "title": "Complexity concentration and churn create elevated change risk",
        "severity": "high" if has_churn_overlap else "medium",
        "confidence": 0.88,
        "category": "maintainability",
        "evidence": evidence[:10],
        "affected_files": affected_files[:12],
        "business_impact": "Concentrated complexity in frequently changed code increases regression risk, review time, and the cost of future features.",
        "technical_impact": "Multiple complexity, large-file, and churn signals point to a small set of modules where changes are difficult to reason about safely.",
        "recommendation": "Rank the affected functions by measured function-level complexity and churn, add characterization tests, then decompose one bounded hotspot per release.",
        "verification_method": "Require function-level complexity measurements, focused regression tests, full-suite success, and a lower hotspot score before closing each slice.",
        "exploitability": "low",
        "effort": "high",
    }


def _consolidate_findings(combined: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    retained: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    complexity: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in combined:
        title = _text(item.get("title") or item.get("code"))
        if not title:
            continue
        normalized = title.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        if _is_advisory(title):
            advisories.append({
                "title": title,
                "reason": "Scope or size signal retained for planning context; it is not ranked as a defect by itself.",
                "evidence": [_text(value) for value in item.get("evidence", []) or [] if _text(value)] or [title],
            })
            continue
        if normalized.startswith("complexity hotspot:") or any(marker in normalized for marker in _COMPLEXITY_AGGREGATE_MARKERS):
            complexity.append(item)
            continue
        retained.append(item)
    grouped = _complexity_group(complexity)
    if grouped:
        retained.append(grouped)
    return retained, advisories


def _portfolio(candidates: list[dict[str, Any]], advisories: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = Counter(str(item.get("severity") or "unknown") for item in candidates)
    effort_counts = Counter(str(item.get("effort") or "unknown") for item in candidates)
    tgrm_counts = Counter(str((item.get("tgrm") or {}).get("level") or "unknown") for item in candidates)
    return {
        "severity_counts": {key: severity_counts.get(key, 0) for key in ("critical", "high", "medium", "low", "info")},
        "effort_counts": {key: effort_counts.get(key, 0) for key in ("low", "medium", "high")},
        "tgrm_counts": {f"level_{key}": tgrm_counts.get(str(key), 0) for key in (1, 2, 3)},
        "advisory_count": len(advisories),
    }


def build_report_repair_intelligence(
    payload: dict[str, Any],
    *,
    structured_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build calibrated, consolidated repair packets without changing the assessed repository."""

    combined: list[dict[str, Any]] = [
        dict(item)
        for item in (structured_findings or [])
        if isinstance(item, dict)
    ]
    seen_titles = {_text(item.get("title")).lower() for item in combined}
    for section in payload.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for item in section.get("findings", []) or []:
            text = _text(item)
            if not text or text.lower() in seen_titles:
                continue
            combined.append(_generic_finding(section, text))
            seen_titles.add(text.lower())

    consolidated, advisories = _consolidate_findings(combined)
    candidates = [_candidate_from_structured(item) for item in consolidated]
    candidates.sort(
        key=lambda item: (
            float(item.get("priority_score") or 0),
            _SEVERITY_ORDER.get(str(item.get("severity") or "low"), 0),
            float(item.get("confidence_numeric") or 0),
        ),
        reverse=True,
    )
    for index, item in enumerate(candidates, 1):
        item["rank"] = index

    available_code = sum(
        1
        for item in candidates
        if isinstance(item.get("code_suggestion"), dict)
        and item["code_suggestion"].get("status") == "available"
    )
    portfolio = _portfolio(candidates, advisories)
    portfolio["code_suggestion_count"] = available_code
    portfolio["candidate_count"] = len(candidates)
    return {
        "status": "complete",
        "mode": "report_only",
        "priority_model": "calibrated_weighted_v2",
        "candidate_count": len(candidates),
        "code_suggestion_count": available_code,
        "candidates": candidates[:30],
        "advisories": advisories[:20],
        "portfolio": portfolio,
        "policy": dict(REPORT_ONLY_CODE_POLICY),
        "truth_rules": [
            "NICO does not edit the assessed repository.",
            "Suggested code is not described as verified until the exact repository tests pass.",
            "Unknown or context-sensitive repairs return no code candidate rather than fabricated code.",
            "Every candidate includes human review, tests, rollback guidance, and a calibrated effort estimate.",
            "Repository size and source footprint are planning advisories, not defects by themselves.",
            "Dollar savings are not estimated without client-specific cost evidence.",
        ],
    }


def render_repair_intelligence_markdown(intelligence: dict[str, Any] | None) -> list[str]:
    intelligence = intelligence if isinstance(intelligence, dict) else {}
    candidates = [item for item in intelligence.get("candidates", []) or [] if isinstance(item, dict)]
    advisories = [item for item in intelligence.get("advisories", []) or [] if isinstance(item, dict)]
    lines = [
        "## Prioritized Repair Intelligence",
        "",
        "**Report-only safety boundary:** NICO has not changed, committed, pushed, deployed, or opened a pull request against the assessed repository. Suggested code is an unverified review candidate until the stated tests pass and a human approves it.",
        "",
    ]
    if not candidates:
        lines.extend(["No evidence-supported repair candidate was produced.", ""])
    for item in candidates[:12]:
        tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
        lines.extend(
            [
                f"### P{item.get('rank', '?')} - {item.get('title', 'Repair candidate')}",
                "",
                (
                    f"- Severity: **{str(item.get('severity') or 'unknown').upper()}**"
                    f" | Priority score: **{item.get('priority_score', 'N/A')}**"
                    f" | Effort: **{item.get('effort', 'unknown')}**"
                    f" | Confidence: **{item.get('confidence', 'unknown')}**"
                    f" | Exploitability: **{item.get('exploitability', 'unknown')}**"
                ),
                f"- TGRM: **{tgrm.get('label', 'Not assigned')}**",
                f"- Impact: {item.get('impact')}",
                f"- Technical impact: {item.get('technical_impact')}",
                f"- Recommended action: {item.get('recommended_action')}",
            ]
        )
        if item.get("affected_files"):
            lines.append(f"- Affected files/systems: {', '.join(str(value) for value in item['affected_files'])}")
        if item.get("evidence"):
            lines.append("- Evidence:")
            for evidence in item["evidence"][:6]:
                lines.append(f"  - {_text(evidence)}")

        suggestion = item.get("code_suggestion") if isinstance(item.get("code_suggestion"), dict) else {}
        if suggestion.get("status") == "available":
            lines.extend(
                [
                    "",
                    f"**Suggested code - {suggestion.get('candidate_kind', 'reviewable candidate')} (not applied):**",
                    f"```{suggestion.get('language') or 'text'}",
                    str(suggestion.get("suggested_code") or "").rstrip(),
                    "```",
                    "Applicability conditions:",
                ]
            )
            for condition in suggestion.get("applicability_conditions", []) or []:
                lines.append(f"- {condition}")
            lines.append("Verification required:")
            for step in suggestion.get("verification_steps", []) or []:
                lines.append(f"- {step}")
        else:
            lines.append(f"- Suggested code: unavailable - {suggestion.get('reason') or 'additional context is required.'}")

        lines.append(f"- Rollback: {item.get('rollback_plan')}")
        lines.append("")

    if advisories:
        lines.extend(["## Planning Advisories - Not Ranked as Defects", ""])
        for item in advisories[:10]:
            lines.append(f"- {item.get('title')}: {item.get('reason')}")
        lines.append("")
    return lines


__all__ = [
    "build_report_repair_intelligence",
    "render_repair_intelligence_markdown",
]
