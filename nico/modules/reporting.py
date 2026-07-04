"""Reporting Module (Phase 2 - Fixed Metadata Timing)

write_assessment_reports now ensures JSON files contain their own reports metadata.
"""

import json
from pathlib import Path
from datetime import datetime


def write_assessment_reports(result: dict, output_dir: str) -> dict:
    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        assessment_id = result.get("assessment_id", "unknown")

        # Build paths first
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

        # Create final result that includes reports metadata
        final_result = dict(result)
        final_result["reports"] = report_result

        # Write final_result (with reports) to JSON files
        json_content = json.dumps(final_result, indent=2, default=str)
        json_latest.write_text(json_content, encoding="utf-8")
        json_timestamped.write_text(json_content, encoding="utf-8")

        # Simple Markdown
        md_content = f"# NICO Assessment Report\n\n**Target:** {final_result.get('target')}\n**Tier:** {final_result.get('tier')}\n**Status:** {final_result.get('status')}\n**Findings:** {final_result.get('findings_count', 0)}\n**Repairs:** {final_result.get('repairs_count', 0)}\n"
        md_path.write_text(md_content, encoding="utf-8")

        # Simple HTML
        html_content = f"""<html><body>
<h1>NICO Assessment Report</h1>
<p><b>Target:</b> {final_result.get('target')}</p>
<p><b>Tier:</b> {final_result.get('tier')}</p>
<p><b>Status:</b> {final_result.get('status')}</p>
<p><b>Findings:</b> {final_result.get('findings_count', 0)}</p>
</body></html>"""
        html_path.write_text(html_content, encoding="utf-8")

        # Evidence manifest
        evidence_content = json.dumps({
            "assessment_id": assessment_id,
            "evidence_sources": final_result.get("evidence_sources", []),
            "limitations": final_result.get("limitations", [])
        }, indent=2)
        evidence_path.write_text(evidence_content, encoding="utf-8")

        return report_result

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "limitations": [f"Report writing failed: {e}"]
        }


def generate_reports(result: dict) -> dict:
    return {
        "status": "delegated",
        "note": "Use write_assessment_reports() for full output"
    }
