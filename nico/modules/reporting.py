"""Reporting Module (Phase 3)

Richer evidence objects in manifest (module, signal, weight, limitation).
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

        # Full Markdown (preserved)
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
            if dep.get("risky_dependencies"):
                for r in dep["risky_dependencies"]:
                    md_lines.append(f"- {r.get('dependency')}: {r.get('reason')}")
            md_lines.append("")

        if final_result.get("cicd_audit"):
            cicd = final_result["cicd_audit"]
            md_lines.append("## CI/CD Audit")
            md_lines.append(f"Has CI: {cicd.get('has_ci')}")
            if cicd.get("workflows"):
                for w in cicd["workflows"]:
                    md_lines.append(f"- {w}")
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

        # HTML (headings)
        html_lines = ["<html><body>", "<h1>NICO Assessment Report</h1>"]
        html_lines.append(f"<p><b>Target:</b> {final_result.get('target')}</p>")
        html_lines.append(f"<p><b>Tier:</b> {final_result.get('tier')}</p>")
        html_lines.append(f"<p><b>Status:</b> {final_result.get('status')}</p>")
        html_lines.append(f"<p><b>Findings:</b> {final_result.get('findings_count', 0)}</p>")
        html_lines.append("<h2>Maturity</h2>")
        html_lines.append("<h2>Resourcing</h2>")
        html_lines.append("<h2>Roadmap</h2>")
        html_lines.append("<h2>Ranked Recommendations</h2>")
        html_lines.append("<h2>Limitations</h2>")
        html_lines.append("</body></html>")
        html_path.write_text("\n".join(html_lines), encoding="utf-8")

        # Rich evidence manifest
        ranked_with_evidence = []
        for r in final_result.get("synthesis", {}).get("ranked_recommendations", []):
            src = r.get("source", "unknown")
            evidence_obj = {
                "module": src,
                "signal": r.get("title"),
                "weight": r.get("weight"),
                "limitation": "Heuristic weight" if src in ["scanner", "architecture", "dependency", "cicd"] else "Requires human review"
            }
            ranked_with_evidence.append(evidence_obj)

        evidence_manifest = {
            "assessment_id": assessment_id,
            "evidence_sources": final_result.get("evidence_sources", []),
            "limitations": final_result.get("limitations", []),
            "ranked_recommendations_with_evidence": ranked_with_evidence
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
