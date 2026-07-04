#!/usr/bin/env python3
"""NICO Assessment Orchestrator (Phase 2 - Stabilized)

Key improvements:
- Separate guarded imports (failure in one module doesn't break others)
- Proper local path handling for Express tier (uses run_scan instead of auditor)
- Still preserves all existing commands
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

# Guarded imports - each can fail independently

auditor_audit = None
auditor_error = None
try:
    from nico.auditor import audit as auditor_audit
except Exception as e:
    auditor_error = str(e)

repo_intake = None
repo_intake_error = None
try:
    from nico.modules.repo_intake import intake as repo_intake
except Exception as e:
    repo_intake_error = str(e)

generate_reports = None
generate_reports_error = None
try:
    from nico.modules.reporting import generate_reports
except Exception as e:
    generate_reports_error = str(e)

run_scan = None
run_scan_error = None
try:
    from nico.cli import run_scan
except Exception as e:
    run_scan_error = str(e)


def run_assessment(
    target: str,
    tier: str = "express",
    mode: str = "audit",
    use_swarm: bool = False,
    github_token_env: str | None = None,
    client_context: str | None = None,
    output_dir: str | None = None,
) -> dict:
    started_at = datetime.utcnow().isoformat()

    result = {
        "assessment_id": f"assessment_{int(datetime.utcnow().timestamp())}",
        "target": target,
        "tier": tier,
        "mode": mode,
        "started_at": started_at,
        "status": "started",
        "findings_count": 0,
        "repairs_count": 0,
        "limitations": [],
        "evidence_sources": ["static_analysis"],
    }

    # Record import issues as limitations
    if auditor_error:
        result["limitations"].append(f"auditor import issue: {auditor_error}")
    if repo_intake_error:
        result["limitations"].append(f"repo_intake import issue: {repo_intake_error}")
    if generate_reports_error:
        result["limitations"].append(f"reporting import issue: {generate_reports_error}")
    if run_scan_error:
        result["limitations"].append(f"run_scan import issue: {run_scan_error}")

    # Run intake if available
    intake_result = None
    if repo_intake:
        try:
            intake_result = repo_intake(target)
            result["intake"] = intake_result
            if intake_result.get("limitations"):
                result["limitations"].extend(intake_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"Intake failed: {e}")

    is_local_path = False
    if intake_result and intake_result.get("is_local_path") and intake_result.get("exists"):
        is_local_path = True

    if tier == "express":
        if is_local_path:
            # Local path → use run_scan directly
            if run_scan:
                try:
                    scan_result = run_scan(target, kind="assessment_express_local")
                    result.update({
                        "status": "completed",
                        "used_local_scan": True,
                        "findings_count": len(scan_result.get("findings", [])),
                        "repairs_count": len(scan_result.get("repairs", [])),
                    })
                except Exception as e:
                    result.update({"status": "error", "error": str(e)})
            else:
                result.update({"status": "error", "error": "run_scan not available for local path"})
        else:
            # URL or non-existing local → use auditor (clone-based)
            if auditor_audit:
                try:
                    audit_result = auditor_audit(target, tier="full", mode=mode, use_swarm=use_swarm)

                    if isinstance(audit_result, dict) and audit_result.get("error"):
                        result.update({
                            "status": "completed_with_limitations",
                            "error": audit_result["error"],
                            "limitations": result.get("limitations", []) + ["Auditor reported error (likely clone/network)"]
                        })
                    else:
                        result.update({
                            "status": "completed",
                            "delegated_to": "nico.auditor",
                            "findings_count": audit_result.get("findings_count", 0),
                            "repairs_count": audit_result.get("repairs_count", 0),
                        })
                except Exception as e:
                    result.update({"status": "error", "error": str(e)})
            else:
                result.update({"status": "error", "error": "auditor not available"})

    else:
        result["status"] = "not_implemented_yet"
        result["limitations"].append(f"{tier.upper()} tier is placeholder in Phase 2")

    # Generate reports if available
    if generate_reports and output_dir:
        try:
            report_result = generate_reports(result)
            result["reports"] = report_result
        except Exception as e:
            result["limitations"].append(f"Report generation error: {e}")

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / f"assessment_{result.get('assessment_id')}.json"
        report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_written"] = str(report_path)

    return result


def main():
    parser = argparse.ArgumentParser(prog="nico.assessment", description="NICO Technical Health Assessment")
    parser.add_argument("target", help="GitHub repo URL or local path")
    parser.add_argument("--tier", default="express", choices=["express", "mid", "full"])
    parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    parser.add_argument("--swarm", action="store_true")
    parser.add_argument("--github-token-env", default=None)
    parser.add_argument("--client-context", default=None)
    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    result = run_assessment(
        target=args.target,
        tier=args.tier,
        mode=args.mode,
        use_swarm=args.swarm,
        github_token_env=args.github_token_env,
        client_context=args.client_context,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
