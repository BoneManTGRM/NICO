from __future__ import annotations

from typing import Any


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in result.get("sections", []) or []
            if isinstance(item, dict) and item.get("id") == section_id
        ),
        None,
    )


def _score(result: dict[str, Any]) -> int:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    try:
        return int(maturity.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _section_gap(section: dict[str, Any] | None, target: int) -> int:
    if not section:
        return 0
    try:
        current = int(section.get("score") or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, target - current)


def _section_has_text(section: dict[str, Any] | None, *needles: str) -> bool:
    if not section:
        return False
    text = "\n".join(
        str(item)
        for key in ("summary", "evidence", "findings", "unavailable")
        for item in (section.get(key) if isinstance(section.get(key), list) else [section.get(key)])
        if item
    ).lower()
    return any(needle.lower() in text for needle in needles)


def build_score_lift_plan(result: dict[str, Any], *, target_score: int = 90) -> dict[str, Any]:
    """Return honest, evidence-bound steps to improve score.

    This does not change scoring. It explains exactly which missing evidence or
    unresolved findings are preventing higher report numbers.
    """

    current = _score(result)
    dependency = _section(result, "dependency_health")
    static = _section(result, "static_analysis")
    ci = _section(result, "ci_cd")
    velocity = _section(result, "velocity_complexity")
    client = _section(result, "client_acceptance")

    opportunities: list[dict[str, Any]] = []

    if dependency and int(dependency.get("score") or 0) < 90:
        opportunities.append(
            {
                "area": "Dependency / Library Ecosystem",
                "current_score": int(dependency.get("score") or 0),
                "target_score": 90,
                "possible_section_lift": _section_gap(dependency, 90),
                "required_evidence": [
                    "Attach current-run pip-audit JSON artifact.",
                    "Attach current-run npm audit JSON artifact for detected lockfiles.",
                    "Attach current-run OSV Scanner artifact or OSV API fallback proof using normalized exact package versions.",
                    "Show zero unresolved dependency findings, or mark findings remediated/not-applicable with evidence.",
                ],
                "why_not_higher_now": "Dependency cannot receive green scanner-clean scoring while OSV/malformed OSV evidence or missing dependency scanner artifacts remain.",
            }
        )

    if static and int(static.get("score") or 0) < 90:
        opportunities.append(
            {
                "area": "Static Analysis",
                "current_score": int(static.get("score") or 0),
                "target_score": 90,
                "possible_section_lift": _section_gap(static, 90),
                "required_evidence": [
                    "Attach current-run Bandit artifact.",
                    "Attach current-run Semgrep artifact.",
                    "Attach current-run ESLint artifact when project-command execution is approved for this repository.",
                    "Attach current-run TypeScript noEmit artifact when project-command execution is approved for this repository.",
                    "Approve rule-level triage for all Bandit findings, with blocker_count=0 and review_required_count=0 before green scanner-clean claims.",
                ],
                "why_not_higher_now": "Static cannot receive green scanner-clean scoring while Bandit findings remain untriaged or live scanner-worker proof is missing.",
            }
        )

    if ci and int(ci.get("score") or 0) < 90:
        opportunities.append(
            {
                "area": "CI/CD Analysis",
                "current_score": int(ci.get("score") or 0),
                "target_score": 90,
                "possible_section_lift": _section_gap(ci, 90),
                "required_evidence": [
                    "Review and classify recent non-success workflow runs.",
                    "Attach latest green NICO CI, security audit, CodeQL, frontend build, Docker build, and file-integrity evidence.",
                    "Separate old superseded PR failures from current release-readiness evidence.",
                ],
                "why_not_higher_now": "CI/CD cannot score near-perfect while recent workflow history still includes unreviewed non-success runs.",
            }
        )

    if velocity and int(velocity.get("score") or 0) < 90:
        opportunities.append(
            {
                "area": "Velocity / Complexity",
                "current_score": int(velocity.get("score") or 0),
                "target_score": 88,
                "possible_section_lift": _section_gap(velocity, 88),
                "required_evidence": [
                    "Attach complexity-engine evidence with hotspot risk below high.",
                    "Attach source-footprint and ownership/churn evidence from the scanner worker.",
                    "Provide stakeholder expected-work context or roadmap/scope notes for work-vs-expected scoring.",
                ],
                "why_not_higher_now": "Large source footprint and missing stakeholder context keep velocity/complexity review-limited.",
            }
        )

    if client and client.get("status") == "gray":
        opportunities.append(
            {
                "area": "Client / Human Acceptance",
                "current_score": int(client.get("score") or 0),
                "target_score": "not scored until approved",
                "possible_section_lift": 0,
                "required_evidence": [
                    "Create final-review request.",
                    "Attach report-readiness, smoke-test, delivery-manifest, and acceptance evidence.",
                    "Record approved same-project client/human acceptance before client-facing delivery.",
                ],
                "why_not_higher_now": "Client acceptance is intentionally not included in automated maturity scoring until a human approval record exists.",
            }
        )

    projected_section_lift = sum(int(item.get("possible_section_lift") or 0) for item in opportunities)
    blockers = [item["area"] for item in opportunities if item.get("possible_section_lift")]
    status = "target_reachable_with_evidence" if current < target_score and opportunities else "target_met_or_no_plan_needed"
    return {
        "status": status,
        "current_score": current,
        "target_score": target_score,
        "estimated_score_path": "Score can only rise when missing scanner artifacts, triage approvals, and release-readiness evidence are attached. This plan does not inflate scores.",
        "estimated_section_lift_available": projected_section_lift,
        "primary_blockers": blockers,
        "opportunities": opportunities,
        "not_allowed": [
            "Do not raise scores by hiding unavailable evidence.",
            "Do not call a section scanner-clean without current-run artifacts.",
            "Do not treat malformed OSV extra syntax as confirmed installed-package proof.",
            "Do not claim client-ready delivery without final review and acceptance evidence.",
        ],
    }


def attach_score_lift_plan(result: dict[str, Any], *, target_score: int = 90) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    plan = build_score_lift_plan(result, target_score=target_score)
    result["score_lift_plan"] = plan

    quick_wins = list(result.get("quick_wins") or [])
    medium_term = list(result.get("medium_term_plan") or [])
    _append_unique(
        quick_wins,
        "Improve report numbers only by adding missing proof: run and attach dependency, static-analysis, CI, complexity, and final-review artifacts before claiming higher scores.",
    )
    for opportunity in plan.get("opportunities", [])[:4]:
        required = opportunity.get("required_evidence") or []
        if required:
            _append_unique(medium_term, f"Score lift path for {opportunity.get('area')}: {required[0]}")
    result["quick_wins"] = quick_wins
    result["medium_term_plan"] = medium_term
    return result
