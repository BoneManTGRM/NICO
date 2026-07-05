#!/usr/bin/env python3
"""NICO Assessment Orchestrator (Phase 3)

Full Express assessment with Token Health, GitHub Activity, CI/CD run history,
and clean synthesis weighting.
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

write_assessment_reports = None
try:
    from nico.modules.reporting import write_assessment_reports
except Exception:
    pass

write_express_assessment_pack = None
try:
    from nico.modules.express_pack import write_express_assessment_pack
except Exception:
    pass

run_scan = None
try:
    from nico.cli import run_scan
except Exception:
    pass

dependency_audit = None
try:
    from nico.modules.dependency_audit import audit_dependencies as dependency_audit
except Exception:
    pass

cicd_audit = None
try:
    from nico.modules.cicd_audit import audit_cicd as cicd_audit
except Exception:
    pass

architecture_audit = None
try:
    from nico.modules.architecture_audit import audit_architecture as architecture_audit
except Exception:
    pass

maturity = None
try:
    from nico.modules.maturity import assess_maturity as maturity
except Exception:
    pass

resourcing = None
try:
    from nico.modules.resourcing import recommend_resourcing as resourcing
except Exception:
    pass

roadmap = None
try:
    from nico.modules.roadmap import build_roadmap as roadmap
except Exception:
    pass

synthesis = None
try:
    from nico.modules.synthesis import synthesize_recommendations as synthesis
except Exception:
    pass

github_activity = None
try:
    from nico.modules.github_activity import analyze_github_activity as github_activity
except Exception:
    pass

github_token_health = None
try:
    from nico.modules.github_token_health import check_github_token_health as github_token_health
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

    if repo_intake:
        try:
            intake_result = repo_intake(target)
            result["intake"] = intake_result
            if intake_result.get("limitations"):
                result["limitations"].extend(intake_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"Intake error: {e}")

    # GitHub Token Health (early check)
    if github_token_health:
        try:
            token_health = github_token_health(target, github_token_env=github_token_env)
            result["github_token_health"] = token_health
            if token_health.get("limitations"):
                result["limitations"].extend(token_health["limitations"])
            if token_health.get("status") in ("completed", "limited"):
                result["evidence_sources"].append("github_token_health")
        except Exception as e:
            result["limitations"].append(f"GitHub token health error: {e}")

    # GitHub Activity
    if github_activity:
        try:
            gh_result = github_activity(target, months=6, github_token_env=github_token_env)
            result["github_activity"] = gh_result
            if gh_result.get("limitations"):
                result["limitations"].extend(gh_result["limitations"])
            if gh_result.get("status") in ("completed", "limited"):
                result["evidence_sources"].append("github_activity")
        except Exception as e:
            result["limitations"].append(f"GitHub activity error: {e}")

    if dependency_audit:
        try:
            dep_result = dependency_audit(target)
            result["dependency_audit"] = dep_result
            if dep_result.get("limitations"):
                result["limitations"].extend(dep_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"Dependency audit error: {e}")

    if cicd_audit:
        try:
            cicd_result = cicd_audit(target, github_token_env=github_token_env)
            result["cicd_audit"] = cicd_result
            if cicd_result.get("limitations"):
                result["limitations"].extend(cicd_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"CI/CD audit error: {e}")

    if architecture_audit:
        try:
            arch_result = architecture_audit(target)
            result["architecture_audit"] = arch_result
            if arch_result.get("limitations"):
                result["limitations"].extend(arch_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"Architecture audit error: {e}")

    is_local_path = bool(result.get("intake") and result["intake"].get("is_local_path") and result["intake"].get("exists"))

    if tier == "express":
        if is_local_path:
            if run_scan:
                try:
                    scan_result = run_scan(target, kind="assessment_express_local")
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

        # Maturity
        if maturity:
            try:
                maturity_result = maturity(result)
                result["maturity"] = maturity_result
                if maturity_result.get("limitations"):
                    result["limitations"].extend(maturity_result["limitations"])
            except Exception as e:
                result["limitations"].append(f"Maturity error: {e}")

        # Resourcing
        if resourcing:
            try:
                res_result = resourcing(result)
                result["resourcing"] = res_result
                if res_result.get("limitations"):
                    result["limitations"].extend(res_result["limitations"])
            except Exception as e:
                result["limitations"].append(f"Resourcing error: {e}")

        # Roadmap
        if roadmap:
            try:
                roadmap_result = roadmap(result)
                result["roadmap"] = roadmap_result
                if roadmap_result.get("limitations"):
                    result["limitations"].extend(roadmap_result["limitations"])
            except Exception as e:
                result["limitations"].append(f"Roadmap error: {e}")

        # Synthesis (with cicd_static / cicd_history split)
        if synthesis:
            try:
                synthesis_result = synthesis(result)
                result["synthesis"] = synthesis_result
                if synthesis_result.get("limitations"):
                    result["limitations"].extend(synthesis_result["limitations"])
            except Exception as e:
                result["limitations"].append(f"Synthesis error: {e}")

    else:
        result["status"] = "not_implemented_yet"
        result["limitations"].append(f"{tier.upper()} tier placeholder")

    if write_assessment_reports and output_dir:
        try:
            report_result = write_assessment_reports(result, output_dir)
            result["reports"] = report_result
        except Exception as e:
            result["limitations"].append(f"Report error: {e}")

    if write_express_assessment_pack and output_dir:
        try:
            express_pack_result = write_express_assessment_pack(result, output_dir)
            existing_reports = result.get("reports")
            if isinstance(existing_reports, dict):
                result["reports"]["express_pack"] = express_pack_result
            else:
                result["reports"] = {
                    "standard": existing_reports,
                    "express_pack": express_pack_result,
                }
        except Exception as e:
            result["limitations"].append(f"Express pack error: {e}")

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
