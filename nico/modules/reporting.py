"""Reporting Module (Phase 3)

Full reporting with Dependency Audit, CI/CD, GitHub Activity, Token Health, and rich evidence manifest.
"""

import json
from pathlib import Path
from datetime import datetime


def write_assessment_reports(result: dict, output_dir: str) -> dict:
    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        assessment_id = result.get("assessment_id", "unknown")

        json_latest = out_path / "assessment_latest.json"
        json_timestamped = out_path / f"assessment_{assessment_id}.json"
        md_path = out_path / "assessment_latest.md"
        html_path = out_path / "assessment_latest.html"
        evidence_path = out_path / "evidence_manifest.json"

        report_result = {
            "status": "completed",
            "paths": {
                "json_latest": str(json_latest),
                "json_timestamped": str(json_timestamped),
                "markdown": str(md_path),
                "html": str(html_path),
                "evidence_manifest": str(evidence_path),
            },
            "limitations": []
        }

        final_result = dict(result)
        final_result["reports"] = report_result

        json_content = json.dumps(final_result, indent=2, default=str)
        json_latest.write_text(json_content, encoding="utf-8")
        json_timestamped.write_text(json_content, encoding="utf-8")

        # Markdown
        md_lines = [
            "# NICO Assessment Report\n",
            f"**Target:** {final_result.get('target')}",
            f"**Tier:** {final_result.get('tier')}",
            f"**Status:** {final_result.get('status')}",
            f"**Findings:** {final_result.get('findings_count', 0)}",
            f"**Repairs:** {final_result.get('repairs_count', 0)}",
            ""
        ]

        if final_result.get("dependency_audit"):
            dep = final_result["dependency_audit"]
            md_lines.append("## Dependency Audit")
            md_lines.append(f"Status: {dep.get('status')}")
            if dep.get("vulnerabilities_found", 0) > 0:
                md_lines.append(f"Vulnerabilities Found: {dep.get('vulnerabilities_found')}")
                md_lines.append(f"Critical: {dep.get('critical_count', 0)} | High: {dep.get('high_count', 0)}")
            if dep.get("risky_dependencies"):
                for r in dep["risky_dependencies"]:
                    sev = r.get("severity", "")
                    sev_str = f" [{sev}]" if sev else ""
                    md_lines.append(f"- {r.get('dependency')}{sev_str}: {r.get('reason')}")
            md_lines.append("")

        if final_result.get("cicd_audit"):
            cicd = final_result["cicd_audit"]
            md_lines.append("## CI/CD Audit")
            md_lines.append(f"Status: {cicd.get('status')}")
            if cicd.get("has_ci"):
                md_lines.append("Has CI config: Yes")
            else:
                md_lines.append("Has CI config: No")
            if cicd.get("workflow_runs_count", 0) > 0:
                md_lines.append(f"Workflow Runs (recent): {cicd.get('workflow_runs_count')}")
                md_lines.append(f"Recent Failures: {cicd.get('failed_runs_recent', 0)}")
                if cicd.get("success_rate") is not None:
                    md_lines.append(f"Approx Success Rate: {cicd.get('success_rate')}%")
                if cicd.get("last_run_status"):
                    md_lines.append(f"Last Run Status: {cicd.get('last_run_status')}")
            else:
                md_lines.append("Workflow run history: Not available (no token or local path)")
            md_lines.append("")

        if final_result.get("architecture_audit"):
            arch = final_result["architecture_audit"]
            md_lines.append("## Architecture & Debt")
            if arch.get("debt_signals"):
                for s in arch["debt_signals"]:
                    md_lines.append(f"- {s}")
            md_lines.append("")

        if final_result.get("maturity"):
            mat = final_result["maturity"]
            md_lines.append("## Maturity")
            md_lines.append(f"Semaphore: {mat.get('semaphore')} (Score: {mat.get('score')})")
            if mat.get("quick_wins"):
                md_lines.append("Quick Wins:")
                for q in mat["quick_wins"]:
                    md_lines.append(f"- {q}")
            md_lines.append("")

        if final_result.get("resourcing"):
            res = final_result["resourcing"]
            md_lines.append("## Resourcing Recommendation")
            md_lines.append(f"Minimum: {', '.join(res.get('minimum_team', []))}")
            md_lines.append(f"Recommended: {', '.join(res.get('recommended_team', []))}")
            if res.get("rationale"):
                for r in res["rationale"]:
                    md_lines.append(f"- {r}")
            md_lines.append("")

        if final_result.get("roadmap"):
            road = final_result["roadmap"]
            md_lines.append("## Roadmap")
            phases = road.get("phases", {})
            for phase_name in ["30_days", "60_days", "90_days"]:
                if phases.get(phase_name):
                    md_lines.append(f"### {phase_name.replace('_', ' ').title()}")
                    for item in phases[phase_name]:
                        md_lines.append(f"- {item}")
            md_lines.append("")

        if final_result.get("github_activity"):
            gh = final_result["github_activity"]
            md_lines.append("## GitHub Activity")
            md_lines.append(f"Status: {gh.get('status')}")
            md_lines.append(f"Lookback Months: {gh.get('lookback_months')}")
            md_lines.append(f"Commits: {gh.get('commit_count', 0)}")
            md_lines.append(f"PRs: {gh.get('pr_count', 0)}")
            md_lines.append(f"Active Authors: {gh.get('active_authors_count', 0)}")
            md_lines.append(f"Velocity: {gh.get('velocity_classification')}")
            md_lines.append(f"Consistency: {gh.get('consistency_classification')}")
            if gh.get("signals"):
                for s in gh["signals"]:
                    md_lines.append(f"- {s}")
            md_lines.append("")

        if final_result.get("github_token_health"):
            th = final_result["github_token_health"]
            md_lines.append("## GitHub Token Health")
            md_lines.append(f"Status: {th.get('status')}")
            md_lines.append(f"GitHub Target: {th.get('is_github_target')}")
            md_lines.append(f"Token Present: {th.get('token_present')}")
            md_lines.append(f"Repo Access: {th.get('repo_access')}")
            md_lines.append(f"Contents Access: {th.get('contents_access')}")
            md_lines.append(f"Pull Requests Access: {th.get('pull_requests_access')}")
            md_lines.append(f"Actions Access: {th.get('actions_access')}")
            if th.get("rate_limit_remaining") is not None:
                md_lines.append(f"Rate Limit Remaining: {th.get('rate_limit_remaining')}")
            if th.get("limitations"):
                for lim in th["limitations"]:
                    md_lines.append(f"- {lim}")
            md_lines.append("")

        if final_result.get("synthesis"):
            syn = final_result["synthesis"]
            md_lines.append("## Ranked Recommendations")
            for r in syn.get("ranked_recommendations", []):
                md_lines.append(f"- {r.get('title')} ({r.get('weight')} weight) ← {r.get('source', 'unknown')}")
            md_lines.append("")

        if final_result.get("limitations"):
            md_lines.append("## Limitations")
            for lim in final_result["limitations"]:
                md_lines.append(f"- {lim}")

        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        # HTML
        html_lines = ["<html><body>", "<h1>NICO Assessment Report</h1>"]
        html_lines.append(f"<p><b>Target:</b> {final_result.get('target')}</p>")
        html_lines.append(f"<p><b>Tier:</b> {final_result.get('tier')}</p>")
        html_lines.append(f"<p><b>Status:</b> {final_result.get('status')}</p>")
        html_lines.append(f"<p><b>Findings:</b> {final_result.get('findings_count', 0)}</p>")
        html_lines.append("<h2>Maturity</h2>")
        html_lines.append("<h2>Resourcing</h2>")
        html_lines.append("<h2>Roadmap</h2>")
        html_lines.append("<h2>GitHub Activity</h2>")
        html_lines.append("<h2>GitHub Token Health</h2>")
        html_lines.append("<h2>Ranked Recommendations</h2>")
        html_lines.append("<h2>Limitations</h2>")
        html_lines.append("</body></html>")
        html_path.write_text("\n".join(html_lines), encoding="utf-8")

        # Evidence Manifest
        ranked_with_evidence = []
        for r in final_result.get("synthesis", {}).get("ranked_recommendations", []):
            src = r.get("source", "unknown")
            evidence_obj = {
                "module": src,
                "signal": r.get("title"),
                "weight": r.get("weight"),
                "limitation": "Heuristic weight" if src in ["scanner", "architecture", "dependency", "cicd", "github_activity"] else "Requires human review"
            }
            ranked_with_evidence.append(evidence_obj)

        cicd = final_result.get("cicd_audit", {})
        th = final_result.get("github_token_health", {})
        dep = final_result.get("dependency_audit", {})

        evidence_manifest = {
            "assessment_id": assessment_id,
            "target": final_result.get("target"),
            "tier": final_result.get("tier"),
            "overall_status": final_result.get("status"),
            "total_evidence_weight": final_result.get("synthesis", {}).get("overall_evidence_weight", 0),
            "module_statuses": {
                "dependency_audit": dep.get("status", "unknown"),
                "cicd_audit": cicd.get("status", "unknown"),
                "architecture_audit": final_result.get("architecture_audit", {}).get("status", "unknown"),
                "maturity": final_result.get("maturity", {}).get("semaphore", "unknown"),
                "github_activity": final_result.get("github_activity", {}).get("status", "unknown"),
                "github_token_health": th.get("status", "unknown"),
            },
            "cicd_details": {
                "has_ci_config": cicd.get("has_ci", False),
                "workflow_runs_analyzed": cicd.get("workflow_runs_count", 0),
                "recent_failures": cicd.get("failed_runs_recent", 0),
                "success_rate": cicd.get("success_rate"),
                "last_run_status": cicd.get("last_run_status"),
            },
            "github_token_health_details": {
                "token_present": th.get("token_present"),
                "repo_access": th.get("repo_access"),
                "contents_access": th.get("contents_access"),
                "pull_requests_access": th.get("pull_requests_access"),
                "actions_access": th.get("actions_access"),
                "rate_limit_remaining": th.get("rate_limit_remaining"),
            },
            "dependency_details": {
                "vulnerabilities_found": dep.get("vulnerabilities_found", 0),
                "critical_count": dep.get("critical_count", 0),
                "high_count": dep.get("high_count", 0),
            },
            "ranked_recommendations_with_evidence": ranked_with_evidence,
            "limitations": final_result.get("limitations", [])
        }
        evidence_content = json.dumps(evidence_manifest, indent=2)
        evidence_path.write_text(evidence_content, encoding="utf-8")

        return report_result

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "limitations": [f"Report writing failed: {e}"]
        }


def generate_reports(result: dict) -> dict:
    return {"status": "delegated"}
