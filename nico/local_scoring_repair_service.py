from __future__ import annotations

from typing import Any, Callable

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
        "what_can_be_safely_automated": "Scan, report, score, generate repair prompt, and run local verification.",
        "what_needs_approval": (
            "Production changes, credential rotation, deployments, destructive actions, or broad infrastructure changes."
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
    """Build the existing bounded repair-plan variants without applying changes."""

    repairs: list[dict[str, Any]] = []
    for finding in findings:
        base_score = finding.get("rye", rye_score(finding, memory)).get("score", 0)
        fix = REPAIR_LIBRARY.get(finding["category"], "Apply smallest defensive fix and verify.")
        files = [finding["affected_file"]] if finding.get("affected_file") else []
        prompt = (
            f"Fix only the {finding.get('title', finding['category'])} issue in "
            f"{finding.get('affected_file', 'the affected file')}.\n"
            "Do not rewrite unrelated code.\n"
            f"Apply this targeted defensive repair: {fix}\n"
            "Add the smallest relevant tests.\n"
            "Run local tests or a NICO rescan.\n"
            "Return a short verification summary.\n"
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
                    "exact_issue": finding.get("title", finding["category"]),
                    "affected_files": files,
                    "smallest_safe_change": fix,
                    "tests_to_add": [
                        "Add focused regression test if available.",
                        "Run NICO rescan after repair.",
                    ],
                    "verification_command": "python -m nico verify latest",
                    "rollback_plan": "Revert targeted change if verification fails or new drift appears.",
                    "codex_ready_patch_prompt": prompt,
                    "owner_friendly_explanation": (
                        f"This {repair_type} repair reduces {finding['category']} risk without broad rewrites."
                    ),
                    "developer_ready_explanation": (
                        f"Target {files or ['affected code']}; verify with: {finding.get('verification_method')}"
                    ),
                    "rye_score": max(0, round(base_score + delta, 2)),
                    "autonomy_level": level,
                    "approval_requirement": (
                        "human_review_required_before_production_change"
                        if finding["severity"] in {"high", "critical"}
                        else "safe_for_local_repair_prompt_generation"
                    ),
                    "status": "suggested",
                    "created_at": clock(),
                }
            )
    return sorted(repairs, key=lambda repair: repair["rye_score"], reverse=True)


__all__ = ["REPAIR_LIBRARY", "rye_score", "apply_rye", "repairs_for"]
