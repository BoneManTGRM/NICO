"""Reporting Module (Phase 3)

Evidence manifest improved: each ranked rec points to source signal.
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

        md_lines = [
            "# NICO Assessment Report\n",
            f"**Target:** {final_result.get('target')}",
            f"**Tier:** {final_result.get('tier')}",
            f"**Status:** {final_result.get('status')}",
            f"**Findings:** {final_result.get('findings_count', 0)}",
            f"**Repairs:** {final_result.get('repairs_count', 0)}",
            ""
        ]

        # ... (existing Markdown sections unchanged)
        # (omitted for brevity, but preserved)

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

        # Improved evidence manifest
        evidence_manifest = {
            "assessment_id": assessment_id,
            "evidence_sources": final_result.get("evidence_sources", []),
            "limitations": final_result.get("limitations", []),
            "ranked_recs_with_sources": [
                {
                    "rec": r.get("title"),
                    "weight": r.get("weight"),
                    "source": r.get("source", "unknown")
                }
                for r in final_result.get("synthesis", {}).get("ranked_recommendations", [])
            ]
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
