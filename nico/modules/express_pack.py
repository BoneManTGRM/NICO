"""Express Assessment Pack writer.

Creates a Malamute-style Express Technical Health Assessment output pack
from real NICO module outputs. The pack records limitations when evidence is
missing and does not claim QA, parity, or stakeholder discovery unless supplied.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PACK_FILENAMES = [
    "executive_summary.md",
    "technical_health_report.md",
    "evidence_manifest.json",
    "dependency_audit.json",
    "cicd_audit.json",
    "architecture_audit.json",
    "github_activity.json",
    "maturity_scorecard.json",
    "roadmap_30_60_90.md",
    "resourcing_plan.md",
    "limitations.md",
]

_SOURCE_TO_MODULE = {
    "dependency": "dependency_audit",
    "cicd": "cicd_audit",
    "architecture": "architecture_audit",
    "github_activity": "github_activity",
    "scanner": "scanner",
}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _join_or_unavailable(value) -> str:
    items = [str(item).strip() for item in _as_list(value) if str(item).strip()]
    return ", ".join(items) if items else "Not available from current evidence"


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def _module_status(payload) -> str:
    if not isinstance(payload, dict):
        return "unavailable"
    return str(payload.get("status", "available"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload or {}, indent=2, default=str), encoding="utf-8")


def _evidence_for(source: str, result: dict) -> dict:
    module_name = _SOURCE_TO_MODULE.get(source, source)
    if source == "scanner":
        return {
            "module": "scanner",
            "status": "available" if result.get("findings_count", 0) else "limited",
            "summary": f"findings_count={result.get('findings_count', 0)}, repairs_count={result.get('repairs_count', 0)}",
        }

    payload = result.get(module_name) or {}
    if module_name == "dependency_audit":
        summary = (
            f"vulnerabilities_found={payload.get('vulnerabilities_found', 0)}, "
            f"critical={payload.get('critical_count', 0)}, high={payload.get('high_count', 0)}"
        )
    elif module_name == "cicd_audit":
        summary = (
            f"has_ci={payload.get('has_ci')}, workflow_runs={payload.get('workflow_runs_count', 0)}, "
            f"recent_failures={payload.get('failed_runs_recent', 0)}, success_rate={payload.get('success_rate')}"
        )
    elif module_name == "architecture_audit":
        summary = f"debt_signals={len(_as_list(payload.get('debt_signals')))}"
    elif module_name == "github_activity":
        summary = (
            f"commits={payload.get('commit_count', 0)}, prs={payload.get('pr_count', 0)}, "
            f"velocity={payload.get('velocity_classification')}, consistency={payload.get('consistency_classification')}"
        )
    else:
        summary = f"status={_module_status(payload)}"

    return {"module": module_name, "status": _module_status(payload), "summary": summary}


def _recommendations_with_evidence(result: dict) -> list[dict]:
    recs = result.get("synthesis", {}).get("ranked_recommendations", [])
    out = []
    for rec in recs:
        source = rec.get("source", "unknown")
        out.append(
            {
                "title": rec.get("title"),
                "weight": rec.get("weight"),
                "source": source,
                "evidence": _evidence_for(source, result),
                "human_review_required": True,
            }
        )
    return out


def _limitations(result: dict) -> list[str]:
    limitations = list(_as_list(result.get("limitations")))
    token = result.get("github_token_health") or {}
    cicd = result.get("cicd_audit") or {}
    activity = result.get("github_activity") or {}

    if not token or token.get("repo_access") is not True:
        limitations.append("GitHub read-only API access was not fully verified; repository, PR, and Actions evidence may be limited.")
    if not cicd:
        limitations.append("CI/CD evidence was not available; pipeline reliability cannot be fully assessed.")
    elif cicd.get("has_ci") is not True:
        limitations.append("CI/CD configuration or run history is missing or limited in the available evidence.")
    if not activity:
        limitations.append("GitHub activity evidence was not available; velocity analysis is limited.")
    if not result.get("client_context"):
        limitations.append("Technical documentation and client-specific product context were not supplied as structured input.")

    tier = str(result.get("tier", "express")).lower()
    if tier == "express":
        limitations.append("QA device testing, iOS/Android parity analysis, and stakeholder discovery are outside Express scope unless separate evidence is provided.")
    else:
        limitations.append("Mid/full tier QA, parity, and stakeholder conclusions require supplied QA artifacts, builds, or interview notes.")

    return _dedupe(limitations)


def build_evidence_manifest(result: dict) -> dict:
    dep = result.get("dependency_audit") or {}
    cicd = result.get("cicd_audit") or {}
    token = result.get("github_token_health") or {}
    return {
        "assessment_id": result.get("assessment_id", "unknown"),
        "target": result.get("target"),
        "tier": result.get("tier"),
        "overall_status": result.get("status"),
        "generated_at": datetime.utcnow().isoformat(),
        "module_statuses": {
            "dependency_audit": _module_status(result.get("dependency_audit")),
            "cicd_audit": _module_status(result.get("cicd_audit")),
            "architecture_audit": _module_status(result.get("architecture_audit")),
            "github_activity": _module_status(result.get("github_activity")),
            "github_token_health": _module_status(result.get("github_token_health")),
            "maturity": _module_status(result.get("maturity")),
            "roadmap": _module_status(result.get("roadmap")),
            "resourcing": _module_status(result.get("resourcing")),
            "synthesis": _module_status(result.get("synthesis")),
        },
        "dependency_details": {
            "vulnerabilities_found": dep.get("vulnerabilities_found", 0),
            "critical_count": dep.get("critical_count", 0),
            "high_count": dep.get("high_count", 0),
        },
        "cicd_details": {
            "has_ci_config": cicd.get("has_ci", False),
            "workflow_runs_analyzed": cicd.get("workflow_runs_count", 0),
            "recent_failures": cicd.get("failed_runs_recent", 0),
            "success_rate": cicd.get("success_rate"),
            "last_run_status": cicd.get("last_run_status"),
        },
        "github_token_health_details": {
            "token_present": token.get("token_present"),
            "repo_access": token.get("repo_access"),
            "contents_access": token.get("contents_access"),
            "pull_requests_access": token.get("pull_requests_access"),
            "actions_access": token.get("actions_access"),
        },
        "ranked_recommendations_with_evidence": _recommendations_with_evidence(result),
        "limitations": result.get("limitations", []),
    }


def _write_executive_summary(path: Path, result: dict, manifest: dict) -> None:
    maturity = result.get("maturity") or {}
    lines = [
        "# Executive Summary",
        "",
        "## Express Technical Health Assessment",
        f"Target: {result.get('target')}",
        f"Status: {result.get('status')}",
        f"Maturity Semaphore: {maturity.get('semaphore', 'unavailable')}",
        f"Maturity Score: {maturity.get('score', 'unavailable')}",
        f"Findings Count: {result.get('findings_count', 0)}",
        f"Repairs Count: {result.get('repairs_count', 0)}",
        "",
        "## Evidence-Backed Recommendations",
    ]
    recs = manifest.get("ranked_recommendations_with_evidence", [])
    if recs:
        for rec in recs:
            evidence = rec.get("evidence", {})
            lines.append(f"- {rec.get('title')} | Source: {rec.get('source')} | Evidence: {evidence.get('summary')}")
    else:
        lines.append("- No ranked recommendations were available from the current evidence set.")
    lines.extend([
        "",
        "## Scope Boundary",
        "This Express pack covers code, dependencies, CI/CD, architecture signals, maturity, roadmap, and resourcing from available evidence.",
        "It does not claim QA device testing, iOS/Android parity, or stakeholder discovery unless those artifacts are supplied.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_technical_health_report(path: Path, result: dict, manifest: dict) -> None:
    dep = result.get("dependency_audit") or {}
    cicd = result.get("cicd_audit") or {}
    arch = result.get("architecture_audit") or {}
    gh = result.get("github_activity") or {}
    mat = result.get("maturity") or {}
    roadmap = result.get("roadmap") or {}
    res = result.get("resourcing") or {}

    lines = [
        "# Technical Health Report",
        "",
        "## Maturity",
        f"Semaphore: {mat.get('semaphore', 'unavailable')}",
        f"Score: {mat.get('score', 'unavailable')}",
        "Drivers:",
    ]
    for item in _as_list(mat.get("drivers")) or ["No specific maturity drivers were available from the current evidence set."]:
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Velocity",
        f"Commits: {gh.get('commit_count', 0)}",
        f"PRs: {gh.get('pr_count', 0)}",
        f"Active Authors: {gh.get('active_authors_count', 0)}",
        f"Velocity Classification: {gh.get('velocity_classification', 'unavailable')}",
        f"Consistency Classification: {gh.get('consistency_classification', 'unavailable')}",
        "",
        "## Dependencies",
        f"Status: {_module_status(dep)}",
        f"Vulnerabilities Found: {dep.get('vulnerabilities_found', 0)}",
        f"Critical: {dep.get('critical_count', 0)}",
        f"High: {dep.get('high_count', 0)}",
        "",
        "## CI/CD",
        f"Status: {_module_status(cicd)}",
        f"Has CI Config: {cicd.get('has_ci')}",
        f"Workflow Runs Analyzed: {cicd.get('workflow_runs_count', 0)}",
        f"Recent Failures: {cicd.get('failed_runs_recent', 0)}",
        f"Success Rate: {cicd.get('success_rate')}",
        "",
        "## Architecture",
        f"Status: {_module_status(arch)}",
        "Debt Signals:",
    ])
    for item in _as_list(arch.get("debt_signals")) or ["No architecture debt signals were identified in the current static evidence."]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## Roadmap")
    phases = roadmap.get("phases", {}) if isinstance(roadmap, dict) else {}
    for phase in ["30_days", "60_days", "90_days"]:
        lines.append(f"### {phase.replace('_', ' ').title()}")
        for item in _as_list(phases.get(phase)) or ["No roadmap items were available for this phase from the current assessment evidence."]:
            lines.append(f"- {item}")

    lines.extend([
        "",
        "## Resourcing",
        f"Minimum Team: {_join_or_unavailable(res.get('minimum_team'))}",
        f"Recommended Team: {_join_or_unavailable(res.get('recommended_team'))}",
        f"Aggressive Team: {_join_or_unavailable(res.get('aggressive_team'))}",
        "Rationale:",
    ])
    for item in _as_list(res.get("rationale")) or ["No resourcing rationale was available from the current assessment evidence."]:
        lines.append(f"- {item}")

    lines.extend(["", "## Evidence-Backed Recommendations"])
    recs = manifest.get("ranked_recommendations_with_evidence", [])
    if recs:
        for rec in recs:
            evidence = rec.get("evidence", {})
            lines.append(f"- {rec.get('title')} | Evidence: {evidence.get('module')} / {evidence.get('summary')}")
    else:
        lines.append("- No ranked recommendations were available from the current synthesis evidence.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_roadmap(path: Path, result: dict) -> None:
    roadmap = result.get("roadmap") or {}
    phases = roadmap.get("phases", {}) if isinstance(roadmap, dict) else {}
    lines = ["# Roadmap 30/60/90", ""]
    for phase in ["30_days", "60_days", "90_days"]:
        lines.append(f"## {phase.replace('_', ' ').title()}")
        for item in _as_list(phases.get(phase)) or ["No roadmap items were available for this phase from the current assessment evidence."]:
            lines.append(f"- {item}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_resourcing(path: Path, result: dict) -> None:
    res = result.get("resourcing") or {}
    lines = [
        "# Resourcing Plan",
        "",
        f"Minimum Team: {_join_or_unavailable(res.get('minimum_team'))}",
        f"Recommended Team: {_join_or_unavailable(res.get('recommended_team'))}",
        f"Aggressive Team: {_join_or_unavailable(res.get('aggressive_team'))}",
        "",
        "## Rationale",
    ]
    for item in _as_list(res.get("rationale")) or ["No resourcing rationale was available from the current assessment evidence."]:
        lines.append(f"- {item}")
    if res.get("when_retainer_makes_sense"):
        lines.extend(["", "## Retainer Signal", str(res.get("when_retainer_makes_sense"))])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_limitations(path: Path, result: dict) -> None:
    lines = ["# Limitations", ""]
    for item in _as_list(result.get("limitations")) or ["No limitations were identified from the current evidence set."]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_express_assessment_pack(result: dict, output_dir: str) -> dict:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    final = dict(result)
    final["limitations"] = _limitations(final)
    manifest = build_evidence_manifest(final)

    _write_executive_summary(out_path / "executive_summary.md", final, manifest)
    _write_technical_health_report(out_path / "technical_health_report.md", final, manifest)
    _write_json(out_path / "evidence_manifest.json", manifest)
    _write_json(out_path / "dependency_audit.json", final.get("dependency_audit", {}))
    _write_json(out_path / "cicd_audit.json", final.get("cicd_audit", {}))
    _write_json(out_path / "architecture_audit.json", final.get("architecture_audit", {}))
    _write_json(out_path / "github_activity.json", final.get("github_activity", {}))
    _write_json(out_path / "maturity_scorecard.json", final.get("maturity", {}))
    _write_roadmap(out_path / "roadmap_30_60_90.md", final)
    _write_resourcing(out_path / "resourcing_plan.md", final)
    _write_limitations(out_path / "limitations.md", final)

    return {
        "status": "completed",
        "output_dir": str(out_path),
        "files": {name: str(out_path / name) for name in PACK_FILENAMES},
        "limitations": final["limitations"],
    }
