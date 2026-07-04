#!/usr/bin/env python3
"""NICO Assessment Orchestrator (Phase 2 - Narrow Fix)

Only change: Fixed local-path Express findings_count to read from scan_result["scan"]["findings"].
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

# Guarded imports
auditor_audit = None
try:
    from nico.auditor import audit as auditor_audit
except Exception:
    pass

repo_intake = None
try:
    from nico.modules.repo_intake import intake as repo_intake
except Exception:
    pass

generate_reports = None
try:
    from nico.modules.reporting import generate_reports
except Exception:
    pass

run_scan = None
try:
    from nico.cli import run_scan
except Exception:
    pass


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

    # Intake
    intake_result = None
    if repo_intake:
        try:
            intake_result = repo_intake(target)
            result["intake"] = intake_result
            if intake_result.get("limitations"):
                result["limitations"].extend(intake_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"Intake error: {e}")

    is_local_path = bool(intake_result and intake_result.get("is_local_path") and intake_result.get("exists"))

    if tier == "express":
        if is_local_path:
            if run_scan:
                try:
                    scan_result = run_scan(target, kind="assessment_express_local")

                    # CORRECT local-path counting
                    scan_payload = scan_result.get("scan", {})
                    findings = scan_payload.get("findings", [])
                    repairs = scan_result.get("repairs", [])

                    result.update({
                        "status": "completed",
                        "used_local_scan": True,
                        "findings_count": len(findings),
                        "repairs_count": len(repairs),
                    })
                except Exception as e:
                    result.update({"status": "error", "error": str(e)})
            else:
                result.update({"status": "error", "error": "run_scan unavailable"})
        else:
            if auditor_audit:
                try:
                    audit_result = auditor_audit(target, tier="full", mode=mode, use_swarm=use_swarm)
                    if isinstance(audit_result, dict) and audit_result.get("error"):
                        result.update({
                            "status": "completed_with_limitations",
                            "error": audit_result.get("error"),
                            "limitations": result.get("limitations", []) + ["Auditor error"]
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
                result.update({"status": "error", "error": "auditor unavailable"})

    else:
        result["status"] = "not_implemented_yet"
        result["limitations"].append(f"{tier.upper()} tier placeholder")

    if generate_reports and output_dir:
        try:
            report_result = generate_reports(result)
            result["reports"] = report_result
        except Exception as e:
            result["limitations"].append(f"Report error: {e}")

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
