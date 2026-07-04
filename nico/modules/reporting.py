"""Reporting Module (Phase 2)

Owns assessment report writing.
"""

import json
from pathlib import Path
from datetime import datetime


def write_assessment_reports(result: dict, output_dir: str) -> dict:
    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        assessment_id = result.get("assessment_id", "unknown")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Main files
        json_latest = out_path / "assessment_latest.json"
        json_timestamped = out_path / f"assessment_{assessment_id}.json"
        md_path = out_path / "assessment_latest.md"
        html_path = out_path / "assessment_latest.html"
        evidence_path = out_path / "evidence_manifest.json"

        # Write JSON (with final result including reports metadata)
        json_content = json.dumps(result, indent=2, default=str)
        json_latest.write_text(json_content, encoding="utf-8")
        json_timestamped.write_text(json_content, encoding="utf-8")

        # Simple Markdown
        md_content = f"# NICO Assessment Report\n\n**Target:** {result.get('target')}\n**Tier:** {result.get('tier')}\n**Status:** {result.get('status')}\n\n**Findings:** {result.get('findings_count', 0)}\n**Repairs:** {result.get('repairs_count', 0)}\n"
        md_path.write_text(md_content, encoding="utf-8")

        # Simple HTML
        html_content = f"""<html><body>
<h1>NICO Assessment Report</h1>
<p><b>Target:</b> {result.get('target')}</p>
<p><b>Tier:</b> {result.get('tier')}</p>
<p><b>Status:</b> {result.get('status')}</p>
<p><b>Findings:</b> {result.get('findings_count', 0)}</p>
</body></html>"""
        html_path.write_text(html_content, encoding="utf-8")

        # Evidence manifest (basic)
        evidence_content = json.dumps({
            "assessment_id": assessment_id,
            "evidence_sources": result.get("evidence_sources", []),
            "limitations": result.get("limitations", [])
        }, indent=2)
        evidence_path.write_text(evidence_content, encoding="utf-8")

        return {
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

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "limitations": [f"Report writing failed: {e}"]
        }


def generate_reports(result: dict) -> dict:
    """Compatibility wrapper for existing generate_reports calls."""
    return {
        "status": "delegated",
        "note": "Use write_assessment_reports() for full report generation"
    }
