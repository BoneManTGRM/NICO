from __future__ import annotations

from typing import Any

TECHNICAL_SOURCES = (
    "repository",
    "head_commit",
    "commits",
    "pull_requests",
    "issues",
    "open_issues",
    "workflow_runs",
    "latest_workflow_state",
    "codeql_runs",
    "releases",
    "deployments",
)
WEEKLY_SOURCES = ("commits", "pull_requests", "issues", "workflow_runs")
RELEASE_SOURCES = ("workflow_runs", "codeql_runs", "releases", "deployments")


def _lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _integer(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _status(score: int, *, calculated: bool, blocker: bool = False) -> str:
    if not calculated:
        return "unverified"
    if blocker:
        return "red"
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def _sources(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("retainer_evidence_sources")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def _verified(sources: dict[str, dict[str, Any]], source_id: str) -> bool:
    return str(sources.get(source_id, {}).get("status") or "") == "verified"


def _source_note(sources: dict[str, dict[str, Any]], source_id: str) -> str:
    source = sources.get(source_id) or {}
    status = str(source.get("status") or "unavailable")
    checked_at = str(source.get("checked_at") or "time unavailable")
    item_count = source.get("item_count")
    count_text = "count unavailable" if item_count is None else f"count={item_count}"
    note = str(source.get("note") or "").strip()
    return f"{source_id}: {status} · {count_text} · checked={checked_at}" + (f" · {note}" if note else "")


def _manual_source_notes(payload: dict[str, Any]) -> list[str]:
    binding = payload.get("source_binding") if isinstance(payload.get("source_binding"), dict) else {}
    checked_at = str(payload.get("manual_context_checked_at") or binding.get("checked_at") or "")
    notes: list[str] = []
    for field in ("roadmap_notes", "client_update", "retainer_metrics", "success_metrics", "budget_priorities"):
        count = len(_lines(payload.get(field)))
        if count:
            notes.append(
                f"operator_context:{field} · supplied · count={count}"
                + (f" · checked={checked_at}" if checked_at else "")
            )
    return notes


def _blockers(payload: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for key in ("blockers", "known_risks", "approval_needs", "release_blockers"):
        rows.extend(_lines(payload.get(key)))
    return rows


def _module(
    *,
    score: int,
    calculated: bool,
    status: str,
    summary: str,
    evidence: list[str],
    unavailable: list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "score": max(0, min(100, int(score))) if calculated else 0,
        "score_calculated": calculated,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "unavailable": unavailable,
        **extra,
    }


def build_retainer_modules(payload: dict[str, Any]) -> dict[str, Any]:
    commits = _lines(payload.get("commit_summary"))
    prs = _lines(payload.get("pr_summary"))
    issues = _lines(payload.get("issue_summary"))
    workflows = _lines(payload.get("workflow_summary"))
    codeql = _lines(payload.get("codeql_summary"))
    blockers = _blockers(payload)
    releases = _lines(payload.get("release_notes"))
    deployments = _lines(payload.get("deployment_summary"))
    roadmap = _lines(payload.get("roadmap_notes"))
    client_update = _lines(payload.get("client_update"))
    metrics = _lines(payload.get("retainer_metrics")) + _lines(payload.get("success_metrics"))
    budget_priorities = _lines(payload.get("budget_priorities"))

    sources = _sources(payload)
    binding = payload.get("source_binding") if isinstance(payload.get("source_binding"), dict) else {}
    repository_bound = str(binding.get("status") or "") == "bound"
    technical_metrics = payload.get("retainer_evidence_metrics") if isinstance(payload.get("retainer_evidence_metrics"), dict) else {}
    failed_workflows = _integer(technical_metrics.get("failed_workflow_runs"))
    failed_codeql = _integer(technical_metrics.get("failed_codeql_runs"))
    open_issue_count = _integer(technical_metrics.get("open_issues"), len(issues))

    weekly_verified = [name for name in WEEKLY_SOURCES if _verified(sources, name)]
    weekly_calculated = repository_bound and bool(weekly_verified)
    weekly_score = 25 + round((len(weekly_verified) / len(WEEKLY_SOURCES)) * 20)
    weekly_score += min(45, len(commits) + len(workflows) + len(prs) * 3)
    weekly_score -= min(30, failed_workflows * 4)
    weekly_score = max(0, min(92, weekly_score))
    weekly_unavailable = [
        f"{name} evidence is unavailable for weekly delivery scoring."
        for name in WEEKLY_SOURCES
        if not _verified(sources, name)
    ]
    if not repository_bound:
        weekly_unavailable.insert(0, "No authorized repository evidence source is bound to this Retainer run.")
    weekly_health = _module(
        score=weekly_score,
        calculated=weekly_calculated,
        status=_status(weekly_score, calculated=weekly_calculated, blocker=bool(blockers)),
        summary="Weekly delivery uses verified commit, pull-request, issue, and workflow-run evidence from the bound repository.",
        evidence=[_source_note(sources, name) for name in weekly_verified],
        unavailable=weekly_unavailable,
        what_changed=(commits + prs + workflows)[:30],
        what_needs_attention=(blockers + issues)[:30],
        next_actions=[
            "Review current non-success workflow states and labeled blockers before the client update.",
            "Confirm whether newly opened issues change the approved roadmap.",
            "Prepare a human-reviewed weekly status from the verified source ledger.",
        ],
    )

    backlog_source = "open_issues" if "open_issues" in sources else "issues"
    backlog_calculated = repository_bound and _verified(sources, backlog_source)
    if backlog_calculated and open_issue_count == 0:
        backlog_score = 85
    elif backlog_calculated:
        backlog_score = max(35, 72 - min(30, open_issue_count * 2) - min(25, len(blockers) * 7))
    else:
        backlog_score = 0
    backlog_health = _module(
        score=backlog_score,
        calculated=backlog_calculated,
        status=_status(backlog_score, calculated=backlog_calculated, blocker=bool(blockers)),
        summary="Backlog health uses the current open-issue source without a timeframe cutoff and discloses open-issue and blocker counts.",
        evidence=[_source_note(sources, backlog_source)] if backlog_calculated else [],
        unavailable=[] if backlog_calculated else [
            "The current open-issue source was not verified; backlog health is unavailable rather than assumed clean."
        ],
        issue_items=issues[:30],
        open_issue_count=open_issue_count if backlog_calculated else None,
    )

    release_verified = [name for name in RELEASE_SOURCES if _verified(sources, name)]
    release_calculated = repository_bound and bool(release_verified)
    release_score = 25 + len(release_verified) * 10
    release_score += 10 if releases else 0
    release_score += 5 if deployments else 0
    release_score += 5 if codeql else 0
    release_score -= min(35, failed_workflows * 4 + failed_codeql * 6)
    if not releases and not deployments:
        release_score = min(release_score, 59)
    release_score = max(0, min(92, release_score))

    verification = payload.get("blocker_verification") if isinstance(payload.get("blocker_verification"), dict) else {}
    verification_status = str(verification.get("status") or "unverified")
    verified_blockers = verification_status == "verified_blockers" or bool(blockers)
    release_status = (
        "unverified"
        if not release_calculated
        else "blocked"
        if verified_blockers
        else "ready_for_human_release_review"
        if releases or deployments
        else "needs_release_evidence"
    )
    release_unavailable = [
        f"{name} evidence is unavailable for release-readiness scoring."
        for name in RELEASE_SOURCES
        if not _verified(sources, name)
    ]
    if release_calculated and not releases and not deployments:
        release_unavailable.append("No release or deployment record was observed in the selected timeframe.")
    release_readiness = _module(
        score=release_score,
        calculated=release_calculated,
        status=release_status,
        summary="Release readiness uses verified workflow, CodeQL, release, deployment, and blocker-verification evidence.",
        evidence=[_source_note(sources, name) for name in release_verified],
        unavailable=release_unavailable,
        release_notes=releases[:30],
        deployment_evidence=deployments[:30],
        required_checks=[
            "Tests, lint, build, dependency, and CodeQL evidence reviewed.",
            "Known risks and rollback path reviewed.",
            "Release and deployment records bound to the reviewed repository identity.",
            "Human approval recorded before production-impacting deployment.",
        ],
        blockers=blockers[:30],
    )

    manual_context = roadmap + metrics + client_update + budget_priorities
    monthly_calculated = bool(manual_context)
    monthly_score = max(0, min(92, 35 + min(50, len(manual_context) * 6)))
    monthly_strategy = _module(
        score=monthly_score,
        calculated=monthly_calculated,
        status=_status(monthly_score, calculated=monthly_calculated),
        summary="Monthly strategy uses operator-supplied roadmap decisions, client-update context, business metrics, budget, and priorities that GitHub cannot prove.",
        evidence=_manual_source_notes(payload),
        unavailable=[] if monthly_calculated else [
            "Monthly strategy context is missing: add roadmap decisions, client-update notes, business metrics, budget, or priorities."
        ],
        roadmap_progress=roadmap[:30],
        metrics=metrics[:30],
        client_update_inputs=client_update[:30],
        budget_priorities=budget_priorities[:30],
        next_focus=[
            "Tie the next-month roadmap to a measurable client outcome.",
            "Confirm budget, priority, scope, and timeline changes with the authorized decision maker.",
            "Use verified repository evidence to explain delivery movement and risk.",
        ],
    )

    blocker_calculated = verification_status in {"verified_clear", "verified_blockers"}
    if verification_status == "verified_clear":
        blocker_score, blocker_status = 90, "clear"
    elif verification_status == "verified_blockers":
        blocker_score, blocker_status = max(35, 82 - len(blockers) * 7), "needs_escalation"
    else:
        blocker_score, blocker_status = 0, "unverified"
    checked_blocker_sources = [
        str(name)
        for name in verification.get("checked_sources") or []
        if _verified(sources, str(name))
    ]
    blocker_escalation = _module(
        score=blocker_score,
        calculated=blocker_calculated,
        status=blocker_status,
        summary="Blocker status is clear only when all current open issues and the latest observed state of each workflow were checked and produced no blocker evidence.",
        evidence=[_source_note(sources, name) for name in checked_blocker_sources],
        unavailable=[] if blocker_calculated else [
            "Blocker state is unverified because all required current-state sources were not successfully checked."
        ],
        blockers=blockers[:30],
        verification=verification,
        escalation_rules=[
            "Escalate production-impacting blockers immediately.",
            "Request approval for scope, budget, timeline, or release-risk changes.",
            "Do not mark blocker state clear from an empty operator input field.",
        ],
    )

    renewal_context = metrics + client_update + roadmap
    renewal_calculated = bool(renewal_context)
    renewal_score = 30 + min(55, len(renewal_context) * 5)
    renewal_signals = _module(
        score=renewal_score,
        calculated=renewal_calculated,
        status=(
            "unverified"
            if not renewal_calculated
            else "strong_signal"
            if renewal_score >= 75
            else "partial_signal"
            if renewal_score >= 45
            else "insufficient_signal"
        ),
        summary="Renewal signal uses measurable outcomes, roadmap progress, client-update evidence, and verified risk trends.",
        evidence=_manual_source_notes(payload),
        unavailable=[] if renewal_calculated else [
            "Renewal evidence is unavailable until measurable outcomes, roadmap progress, or client-update context is supplied."
        ],
        positive_signals=renewal_context[:30],
        risk_signals=blockers[:20],
        recommended_talk_track=[
            "Show verified work completed and the exact source ledger.",
            "Show remaining risk and what continued retainer coverage reduces.",
            "Request approval on next-month priorities before making commitments.",
        ],
    )

    approval_gates = [
        {"gate": "production_deployment", "required": True, "reason": "Production-impacting release requires human approval."},
        {"gate": "roadmap_commitment", "required": True, "reason": "Client-facing roadmap commitments require authorized signoff."},
        {"gate": "scope_budget_timeline_change", "required": True, "reason": "Material delivery changes require approval before commitment."},
        {"gate": "major_dependency_upgrade", "required": True, "reason": "Major dependency or platform changes require rollback and test-plan review."},
    ]

    calculated_modules = [
        item
        for item in (weekly_health, backlog_health, release_readiness, monthly_strategy, blocker_escalation, renewal_signals)
        if item.get("score_calculated")
    ]
    readiness_calculated = repository_bound and len(calculated_modules) >= 3
    readiness_score = (
        round(sum(int(item.get("score") or 0) for item in calculated_modules) / len(calculated_modules))
        if readiness_calculated and calculated_modules
        else 0
    )
    if verified_blockers and readiness_calculated:
        readiness_score = min(readiness_score, 74)

    unavailable: list[str] = []
    if not repository_bound:
        unavailable.append("Retainer technical evidence is unbound: provide an authorized repository or matching Express/Mid baseline.")
    for module in (weekly_health, release_readiness, monthly_strategy, blocker_escalation):
        unavailable.extend(module["unavailable"])
    unavailable = list(dict.fromkeys(str(item) for item in unavailable if str(item).strip()))

    if verified_blockers:
        overall_status = "blocked_by_retainer_risk"
    elif not repository_bound:
        overall_status = "needs_repository_evidence"
    elif readiness_calculated and readiness_score >= 70:
        overall_status = "ready_for_human_retainer_review"
    else:
        overall_status = "needs_more_retainer_evidence"

    verified_sources = [name for name in TECHNICAL_SOURCES if _verified(sources, name)]
    return {
        "artifact_schema": "nico.retainer_modules.v2",
        "status": overall_status,
        "readiness_score": readiness_score,
        "readiness_score_calculated": readiness_calculated,
        "repository_evidence_bound": repository_bound,
        "source_binding": binding,
        "source_ledger": sources,
        "weekly_health": weekly_health,
        "backlog_health": backlog_health,
        "monthly_strategy": monthly_strategy,
        "release_readiness": release_readiness,
        "blocker_escalation": blocker_escalation,
        "renewal_signals": renewal_signals,
        "approval_gates": approval_gates,
        "source_counts": {
            "verified_sources": len(verified_sources),
            "commits": len(commits),
            "prs": len(prs),
            "issues": len(issues),
            "open_issues": open_issue_count if backlog_calculated else None,
            "workflow_runs": len(workflows),
            "codeql_runs": len(codeql),
            "blockers": len(blockers) if blocker_calculated else None,
            "releases": len(releases),
            "deployments": len(deployments),
            "roadmap_notes": len(roadmap),
            "client_updates": len(client_update),
            "metrics": len(metrics),
        },
        "unavailable": unavailable,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "summary": "Retainer modules reconcile verified repository activity with operator-supplied business context. Missing sources remain unavailable and cannot produce a clean result.",
    }
