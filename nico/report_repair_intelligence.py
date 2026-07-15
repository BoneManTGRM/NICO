from __future__ import annotations

import hashlib
from typing import Any

from nico.code_repair_suggestions import REPORT_ONLY_CODE_POLICY, build_code_suggestion
from nico.local_scoring_repair_service import rye_score

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _severity(value: Any, text: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _SEVERITY_ORDER:
        return normalized
    lower = text.lower()
    if any(token in lower for token in ("critical", "credential", "private key", "data loss", "remote code execution")):
        return "critical"
    if any(token in lower for token in ("high", "security", "exposure", "production", "disabled tls", "branch inventory")):
        return "high"
    if any(token in lower for token in ("medium", "risk", "drift", "missing", "fragility", "placeholder")):
        return "medium"
    return "low"


def _confidence_label(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value or "").lower()
        return text if text in {"high", "medium", "low"} else "medium"
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


def _tgrm_level(priority_score: float, category: str) -> dict[str, Any]:
    if priority_score >= 80 or category in {"secret_exposure", "command_execution", "transport_security"}:
        return {
            "level": 3,
            "label": "TGRM-3 strong containment and verified repair",
            "scope": "Contain exposure, apply the bounded repair, run focused and full verification, and preserve rollback evidence.",
        }
    if priority_score >= 55:
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

    normalized = {
        "id": finding.get("code") or title,
        "category": category,
        "severity": severity,
        "confidence": confidence_numeric,
        "business_impact": business_impact,
        "verification_method": verification,
    }
    priority = rye_score(normalized)
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
    severity = _severity("", finding_text)
    category = {
        "dependency_health": "dependency_risk",
        "secrets_review": "secret_exposure",
        "static_analysis": "static_analysis",
        "ci_cd": "delivery_reliability",
        "architecture_debt": "architecture_debt",
        "velocity_complexity": "maintainability",
        "code_audit": "code_quality",
    }.get(section_id, section_id)
    return {
        "code": f"{section_id}_finding",
        "title": finding_text,
        "severity": severity,
        "confidence": 0.72,
        "category": category,
        "evidence": [finding_text],
        "affected_files": [],
        "business_impact": "The finding may increase engineering time, release risk, or incident cost.",
        "technical_impact": finding_text,
        "recommendation": "Collect the exact affected file and failing evidence, then apply the smallest reversible repair.",
        "verification_method": "Run the smallest relevant test, the full suite, and a NICO rescan.",
        "exploitability": "unknown",
    }


def build_report_repair_intelligence(
    payload: dict[str, Any],
    *,
    structured_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build prioritized repair packets without changing the assessed repository."""

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

    candidates = [_candidate_from_structured(item) for item in combined]
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
    return {
        "status": "complete",
        "mode": "report_only",
        "candidate_count": len(candidates),
        "code_suggestion_count": available_code,
        "candidates": candidates[:30],
        "policy": dict(REPORT_ONLY_CODE_POLICY),
        "truth_rules": [
            "NICO does not edit the assessed repository.",
            "Suggested code is not described as verified until the exact repository tests pass.",
            "Unknown or context-sensitive repairs return no code candidate rather than fabricated code.",
            "Every candidate includes human review, tests, and rollback guidance.",
            "Dollar savings are not estimated without client-specific cost evidence.",
        ],
    }


def render_repair_intelligence_markdown(intelligence: dict[str, Any] | None) -> list[str]:
    intelligence = intelligence if isinstance(intelligence, dict) else {}
    candidates = [item for item in intelligence.get("candidates", []) or [] if isinstance(item, dict)]
    lines = [
        "## Prioritized Repair Intelligence",
        "",
        "**Report-only safety boundary:** NICO has not changed, committed, pushed, deployed, or opened a pull request against the assessed repository. Suggested code is an unverified review candidate until the stated tests pass and a human approves it.",
        "",
    ]
    if not candidates:
        lines.extend(["No evidence-supported repair candidate was produced.", ""])
        return lines

    for item in candidates[:15]:
        tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
        lines.extend(
            [
                f"### P{item.get('rank', '?')} — {item.get('title', 'Repair candidate')}",
                "",
                (
                    f"- Severity: **{str(item.get('severity') or 'unknown').upper()}**"
                    f" | Priority score: **{item.get('priority_score', 'N/A')}**"
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
                    f"**Suggested code — {suggestion.get('candidate_kind', 'reviewable candidate')} (not applied):**",
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
            lines.append(f"- Suggested code: unavailable — {suggestion.get('reason') or 'additional context is required.'}")

        lines.append(f"- Rollback: {item.get('rollback_plan')}")
        lines.append("")
    return lines


__all__ = [
    "build_report_repair_intelligence",
    "render_repair_intelligence_markdown",
]
