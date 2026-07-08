from __future__ import annotations

from typing import Any


def _lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _score(count: int, base: int = 35, per_item: int = 6, cap: int = 92) -> int:
    return max(0, min(cap, base + count * per_item))


def _blocker_rows(payload: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for key in ("blockers", "known_risks", "approval_needs", "release_blockers"):
        rows.extend(_lines(payload.get(key)))
    return rows


def build_retainer_modules(payload: dict[str, Any]) -> dict[str, Any]:
    commits = _lines(payload.get("commit_summary"))
    prs = _lines(payload.get("pr_summary"))
    issues = _lines(payload.get("issue_summary"))
    blockers = _blocker_rows(payload)
    releases = _lines(payload.get("release_notes"))
    roadmap = _lines(payload.get("roadmap_notes"))
    client_update = _lines(payload.get("client_update"))
    metrics = _lines(payload.get("retainer_metrics")) + _lines(payload.get("success_metrics"))

    weekly_items = commits + prs + issues + blockers
    weekly_score = _score(len(weekly_items), base=35, per_item=5)
    monthly_score = _score(len(roadmap) + len(metrics) + len(client_update), base=35, per_item=6)
    release_score = _score(len(releases), base=30, per_item=8)
    blocker_score = 90 if not blockers else max(35, 82 - len(blockers) * 7)
    renewal_score = _score(len(metrics) + len(client_update) + len(roadmap), base=30, per_item=5)

    weekly_health = {
        "score": weekly_score,
        "status": "green" if weekly_score >= 75 and not blockers else "yellow" if weekly_score >= 45 else "red",
        "summary": "Weekly health uses commit, PR, issue, and blocker evidence.",
        "what_changed": (commits + prs)[:20],
        "what_needs_attention": (blockers + issues)[:20],
        "next_actions": [
            "Review unresolved blockers before client update.",
            "Confirm whether new issues require approval or roadmap change.",
            "Prepare evidence-backed weekly status summary.",
        ],
    }

    monthly_strategy = {
        "score": monthly_score,
        "status": "green" if monthly_score >= 75 else "yellow" if monthly_score >= 45 else "red",
        "summary": "Monthly strategy uses roadmap notes, client-update notes, and measurable retainer metrics.",
        "roadmap_progress": roadmap[:20],
        "metrics": metrics[:20],
        "client_update_inputs": client_update[:20],
        "next_focus": [
            "Reduce highest-risk blocker or repeated issue class.",
            "Tie next month work to measurable client outcome.",
            "Confirm any roadmap or budget change with client signoff.",
        ],
    }

    release_readiness = {
        "score": release_score,
        "status": "blocked" if blockers else "ready_for_human_release_review" if releases else "needs_release_evidence",
        "summary": "Release readiness requires release notes, test evidence, blocker review, rollback path, and human approval.",
        "release_notes": releases[:20],
        "required_checks": [
            "Tests, lint, build, and dependency checks reviewed.",
            "Known risks and rollback path reviewed.",
            "Client-facing communication prepared if needed.",
            "Human approval recorded before production-impacting deployment.",
        ],
        "blockers": blockers[:20],
    }

    blocker_escalation = {
        "score": blocker_score,
        "status": "clear" if not blockers else "needs_escalation",
        "summary": "Blockers are escalated when they affect delivery, release readiness, client commitments, or approval requirements.",
        "blockers": blockers[:30],
        "escalation_rules": [
            "Escalate production-impacting blockers immediately.",
            "Request client approval for scope, budget, timeline, or release-risk changes.",
            "Do not mark delivery green while unresolved blockers affect client promises.",
        ],
    }

    renewal_signals = {
        "score": renewal_score,
        "status": "strong_signal" if renewal_score >= 75 else "partial_signal" if renewal_score >= 45 else "insufficient_signal",
        "summary": "Renewal signal uses measurable outcomes, roadmap progress, client-update evidence, and unresolved risk trend.",
        "positive_signals": (metrics + roadmap + client_update)[:30],
        "risk_signals": blockers[:20],
        "recommended_talk_track": [
            "Show verified work completed and evidence collected.",
            "Show remaining risk and what continued retainer coverage reduces.",
            "Ask for approval on next-month priorities before making commitments.",
        ],
    }

    approval_gates = [
        {"gate": "production_deployment", "required": True, "reason": "Production-impacting release requires human approval."},
        {"gate": "roadmap_commitment", "required": True, "reason": "Client-facing roadmap commitments require client or authorized representative signoff."},
        {"gate": "scope_budget_timeline_change", "required": True, "reason": "Material delivery changes require approval before commitment."},
        {"gate": "major_dependency_upgrade", "required": True, "reason": "Major dependency or platform changes require rollback and test plan review."},
    ]

    unavailable: list[str] = []
    if not weekly_items:
        unavailable.append("Weekly retainer evidence is missing: add commits, PRs, issues, or blockers.")
    if not roadmap and not client_update and not metrics:
        unavailable.append("Monthly strategy evidence is missing: add roadmap progress, client update notes, or metrics.")
    if not releases:
        unavailable.append("Release readiness evidence is missing: add release notes, test summaries, or deployment notes.")

    readiness_score = round((weekly_score + monthly_score + release_score + blocker_score + renewal_score) / 5)
    if blockers:
        readiness_score = min(readiness_score, 74)
    if unavailable:
        readiness_score = min(readiness_score, 82)

    return {
        "artifact_schema": "nico.retainer_modules.v1",
        "status": "blocked_by_retainer_risk" if blockers else "ready_for_human_retainer_review" if readiness_score >= 70 else "needs_more_retainer_evidence",
        "readiness_score": readiness_score,
        "weekly_health": weekly_health,
        "monthly_strategy": monthly_strategy,
        "release_readiness": release_readiness,
        "blocker_escalation": blocker_escalation,
        "renewal_signals": renewal_signals,
        "approval_gates": approval_gates,
        "source_counts": {
            "commits": len(commits),
            "prs": len(prs),
            "issues": len(issues),
            "blockers": len(blockers),
            "releases": len(releases),
            "roadmap_notes": len(roadmap),
            "client_updates": len(client_update),
            "metrics": len(metrics),
        },
        "unavailable": unavailable,
        "human_review_required": True,
        "summary": "Retainer modules convert ongoing delivery evidence into weekly health, monthly strategy, release readiness, blocker escalation, renewal signals, and approval gates.",
    }
