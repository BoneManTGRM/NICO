from __future__ import annotations

from typing import Any, Callable

from nico.code_repair_suggestions import build_code_suggestion
from nico.local_scan_engine import new_id, now


REPAIR_LIBRARY = {
    "secret_exposure": "Move secret to env/secrets manager, rotate if real, and add scanning.",
    "dependency_risk": "Upgrade dependency and verify tests/build.",
    "insecure_webhook": "Verify signatures, reject missing signatures, and add replay protection where possible.",
    "unsafe_eval": "Replace eval with a safe parser or explicit allowlist.",
    "debug_mode": "Disable debug mode outside local-only fixtures.",
    "missing_rate_limit": "Add rate limiting and abuse detection.",
    "unsafe_file_upload": "Validate upload type, size, name, path, and storage.",
    "log_anomaly": "Add rate limits, MFA review, alerting, and event correlation.",
    "identity_risk": "Require approval and audit logs for admin role changes.",
    "ai_agent_permission_drift": "Apply least-privilege tool access and human approval gates.",
}


def rye_score(
    finding: dict[str, Any],
    memory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the existing local RYE prioritization contract without mutating input."""

    retained_memory = memory or []
    category = finding.get("category", "unknown")
    severity = finding.get("severity", "low")
    recurrence = sum(
        1
        for item in retained_memory
        if item.get("category") == category or item.get("finding_category") == category
    )
    base = {"low": 20, "medium": 45, "high": 72, "critical": 92}.get(severity, 20)
    exploitability = 85 if category in {"secret_exposure", "unsafe_eval", "insecure_webhook", "identity_risk"} else 62
    blast_radius = 86 if category in {"secret_exposure", "identity_risk", "insecure_webhook", "unsafe_eval"} else 48
    verification = 82 if finding.get("verification_method") else 55
    urgency = min(100, base + recurrence * 8)
    denominator = 28 + 18 + 9 + 8 + (9 if finding.get("confidence", 0) >= 0.8 else 25) + 14
    score = round(
        max(
            1,
            min(
                100,
                ((base * exploitability * blast_radius * verification * urgency) / denominator)
                / 85000
                * 100,
            ),
        ),
        2,
    )
    return {
        "score": score,
        "severity": severity,
        "priority": "critical_first" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low",
        "confidence": finding.get("confidence", 0.75),
        "why_this_matters": finding.get("business_impact", "This finding may increase security risk."),
        "why_this_ranks_above_others": (
            f"{severity} severity, {category} category, recurrence {recurrence}, and verification availability."
        ),
        "what_can_be_safely_automated": "Scan, report, score, generate a report-only repair candidate, and run local verification.",
        "what_needs_approval": (
            "Any code change, production change, credential rotation, deployment, destructive action, or broad infrastructure change."
        ),
        "what_can_wait": "Lower-scoring repairs with limited exposure and no recurrence.",
        "what_would_be_overkill": "Broad rewrites before targeted local verification.",
    }


def apply_rye(
    findings: list[dict[str, Any]],
    memory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach RYE scores to copied findings while preserving input ordering."""

    result: list[dict[str, Any]] = []
    for finding in findings:
        updated = dict(finding)
        updated["rye"] = rye_score(updated, memory)
        result.append(updated)
    return result


def repairs_for(
    findings: list[dict[str, Any]],
    memory: list[dict[str, Any]] | None = None,
    *,
    id_factory: Callable[[str], str] = new_id,
    clock: Callable[[], str] = now,
) -> list[dict[str, Any]]:
    """Build bounded report-only repair variants without applying changes."""

    repairs: list[dict[str, Any]] = []
    for finding in findings:
        base_score = finding.get("rye", rye_score(finding, memory)).get("score", 0)
        category = str(finding.get("category") or "unknown")
        fix = REPAIR_LIBRARY.get(category, "Apply smallest defensive fix and verify.")
        files = [finding["affected_file"]] if finding.get("affected_file") else []
        evidence = [
            str(value)
            for value in (
                finding.get("evidence")
                or [finding.get("masked_evidence"), finding.get("technical_impact")]
            )
            if value
        ]
        code_suggestion = build_code_suggestion(
            category=category,
            issue=str(finding.get("title") or category),
            evidence=evidence,
            affected_files=files,
        )
        prompt = (
            f"Prepare a report-only repair proposal for the {finding.get('title', category)} issue in "
            f"{finding.get('affected_file', 'the affected file')}.\n"
            "Do not edit, commit, push, deploy, or open a pull request against the assessed repository.\n"
            f"Use this targeted defensive repair direction: {fix}\n"
            "Include the suggested code only as an unverified candidate.\n"
            "Add the smallest relevant tests and a rollback plan.\n"
            "Never expose raw secrets."
        )
        for repair_type, delta, level in (
            ("minimal", 0, 1),
            ("moderate", -6, 2),
            ("strong", -12, 3),
        ):
            repair_id = id_factory("repair")
            repairs.append(
                {
                    "repair_id": repair_id,
                    "id": repair_id,
                    "finding_id": finding["id"],
                    "repair_type": repair_type,
                    "exact_issue": finding.get("title", category),
                    "affected_files": files,
                    "smallest_safe_change": fix,
                    "code_suggestion": code_suggestion,
                    "tests_to_add": [
                        "Add the smallest focused regression test that fails before the repair and passes after it.",
                        "Run the affected test, full suite, build, and NICO rescan before human approval.",
                    ],
                    "verification_command": "python -m nico verify latest",
                    "rollback_plan": "Revert only the approved targeted change if verification fails or new drift appears.",
                    "codex_ready_patch_prompt": prompt,
                    "owner_friendly_explanation": (
                        f"This {repair_type} report candidate describes how to reduce {category} risk without changing the client repository."
                    ),
                    "developer_ready_explanation": (
                        f"Review {files or ['affected code']}; verify with: {finding.get('verification_method')}"
                    ),
                    "rye_score": max(0, round(base_score + delta, 2)),
                    "autonomy_level": level,
                    "approval_requirement": "human_review_required_before_any_code_change",
                    "status": "suggested",
                    "candidate_status": "report_only_unverified_candidate",
                    "mode": "report_only",
                    "code_change_applied": False,
                    "automatic_application_allowed": False,
                    "automatic_commit_allowed": False,
                    "automatic_pull_request_allowed": False,
                    "created_at": clock(),
                }
            )
    return sorted(repairs, key=lambda repair: repair["rye_score"], reverse=True)


__all__ = ["REPAIR_LIBRARY", "rye_score", "apply_rye", "repairs_for"]
