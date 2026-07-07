from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionCheck:
    id: str
    label: str
    complete: bool
    evidence: str
    remaining: str


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next((item for item in result.get("sections", []) or [] if isinstance(item, dict) and item.get("id") == section_id), None)


def _score(result: dict[str, Any], section_id: str) -> int:
    item = _section(result, section_id)
    return int(item.get("score") or 0) if item else 0


def _text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_text(item)}" for key, item in value.items())
    return str(value or "")


def _all_text(result: dict[str, Any]) -> str:
    parts = [
        _text(result.get("executive_summary")),
        _text(result.get("next_steps")),
        _text(result.get("findings")),
        _text(result.get("repairs")),
        _text(result.get("reports")),
    ]
    for item in result.get("sections", []) or []:
        parts.append(_text(item))
    return "\n".join(parts).lower()


def _has_report_package(result: dict[str, Any]) -> bool:
    reports = result.get("reports") or {}
    return any(reports.get(key) for key in ("markdown", "html", "pdf_base64"))


def _completion_status(score: int) -> str:
    if score >= 90:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def express_service_completion(result: dict[str, Any]) -> dict[str, Any]:
    text = _all_text(result)
    readiness = result.get("release_readiness") or {}
    acceptance = result.get("client_acceptance") or {}
    final_review = result.get("final_review") or {}
    checks = [
        CompletionCheck(
            "repository_access_verified",
            "Repository access verified",
            bool(result.get("repository") or result.get("source_scope")),
            "Authorized repository scope is present in the assessment payload.",
            "Connect an authorized repository before running Express.",
        ),
        CompletionCheck(
            "code_audit_complete",
            "Code audit complete",
            _score(result, "code_audit") >= 75,
            "Code Audit section is present and green/yellow with repository evidence.",
            "Run repository code-pattern and commit/PR analysis.",
        ),
        CompletionCheck(
            "dependency_security_verified",
            "Dependency and security evidence verified",
            _score(result, "dependency_health") >= 75 and _score(result, "secrets_review") >= 75,
            "Dependency and credential-review sections returned usable evidence.",
            "Provide dependency and credential-scan artifacts or rerun hosted evidence collection.",
        ),
        CompletionCheck(
            "ci_cd_verified",
            "CI/CD evidence verified",
            _score(result, "ci_cd") >= 75,
            "CI/CD section returned pipeline or workflow evidence.",
            "Provide CI/CD logs, workflow files, or artifact access.",
        ),
        CompletionCheck(
            "architecture_debt_reviewed",
            "Architecture and technical debt reviewed",
            _score(result, "architecture_debt") >= 75,
            "Architecture / Technical Debt section is present and scored.",
            "Provide enough repository structure or architecture documentation for review.",
        ),
        CompletionCheck(
            "maturity_semaphore_generated",
            "Maturity semaphore generated",
            bool(result.get("maturity_signal") and result.get("maturity_semaphore")),
            "Final Junior/Mid/Senior maturity signal and semaphore are present.",
            "Finalize technical evidence before report generation.",
        ),
        CompletionCheck(
            "work_vs_expected_generated",
            "Work vs Expected generated",
            _score(result, "velocity_complexity") >= 75,
            "Velocity / Complexity section is present and scored.",
            "Provide commit/PR metadata and enough delivery context for velocity analysis.",
        ),
        CompletionCheck(
            "release_readiness_generated",
            "Release-readiness signal generated",
            bool(readiness.get("status")),
            "Release-readiness object is present with passed and missing evidence signals.",
            "Run final consistency scoring after scanner evidence is attached.",
        ),
        CompletionCheck(
            "strategic_action_plan_generated",
            "Strategic action plan generated",
            bool(result.get("next_steps")) or "quick win" in text or "action plan" in text,
            "Next steps or action-plan language is present in the assessment output.",
            "Generate quick wins and medium-term recommendations from the final findings.",
        ),
        CompletionCheck(
            "resourcing_plan_generated",
            "Resourcing plan generated",
            bool(result.get("resourcing_plan")) or "resourcing" in text or "product engineering" in text,
            "Resourcing-plan language or object is present in the output.",
            "Generate Product Engineering Architect, Product Engineer, and Product Quality recommendations.",
        ),
        CompletionCheck(
            "final_review_target_generated",
            "Final-review target generated",
            bool(final_review.get("run_id") and final_review.get("url")),
            "Final-review run ID and URL are present for human approval workflow.",
            "Attach stable run/customer/project scope before final report delivery.",
        ),
        CompletionCheck(
            "final_report_package_ready",
            "Final report package ready",
            _has_report_package(result),
            "At least one final report export format is present.",
            "Rebuild report exports after final scoring.",
        ),
        CompletionCheck(
            "human_review_completed",
            "Human final review completed",
            acceptance.get("status") == "accepted",
            "Approved same-project final-review acceptance record is present.",
            "Request and approve final review after a human checks the report.",
        ),
        CompletionCheck(
            "client_acceptance_complete",
            "Client / human acceptance complete",
            acceptance.get("status") == "accepted",
            "Client/human acceptance is approved and tied to the same project.",
            "Keep this incomplete until a real approved acceptance record exists.",
        ),
    ]
    completed = [check for check in checks if check.complete]
    missing = [check for check in checks if not check.complete]
    score = round(len(completed) / len(checks) * 100) if checks else 0
    return {
        "status": _completion_status(score),
        "score": score,
        "completed_count": len(completed),
        "total_count": len(checks),
        "completed": [check.id for check in completed],
        "remaining": [check.id for check in missing],
        "checks": [
            {
                "id": check.id,
                "label": check.label,
                "complete": check.complete,
                "evidence": check.evidence if check.complete else "",
                "remaining": "" if check.complete else check.remaining,
            }
            for check in checks
        ],
        "rule": "Express Service Completion measures quoted-service completion separately from technical maturity. Human review and client acceptance are never auto-completed.",
    }


def apply_express_service_completion(result: dict[str, Any]) -> dict[str, Any]:
    completion = express_service_completion(result)
    result["express_service_completion"] = completion
    sections = result.setdefault("sections", [])
    existing = _section(result, "express_service_completion")
    evidence = [
        f"Express Service Completion: {completion['completed_count']}/{completion['total_count']} checks complete ({completion['score']}/100).",
        "This metric is separate from technical maturity and does not change the Senior/Mid/Junior score.",
    ]
    unavailable = [
        f"{item['label']}: {item['remaining']}"
        for item in completion["checks"]
        if not item.get("complete")
    ]
    section = {
        "id": "express_service_completion",
        "label": "Express Service Completion",
        "score": completion["score"],
        "status": completion["status"],
        "exclude_from_maturity": True,
        "summary": "Measures completion of the quoted Express Technical Health Assessment job, including technical audit, reporting, action planning, review target, and human acceptance gates.",
        "evidence": evidence,
        "findings": [],
        "unavailable": unavailable,
    }
    if existing:
        existing.update(section)
    else:
        sections.append(section)
    return result
