#!/usr/bin/env python3
"""NICO Assessment Orchestrator (Phase 2 skeleton)

Supports:
    python -m nico.assessment <repo_url_or_path> --tier express|mid|full

Currently a thin wrapper. Real logic will be added module by module.
"""

import argparse
import sys
from pathlib import Path

try:
    from nico.auditor import audit as auditor_audit
except ImportError:
    auditor_audit = None


def run_assessment(
    target: str,
    tier: str = "express",
    mode: str = "audit",
    use_swarm: bool = False,
    github_token_env: str | None = None,
    client_context: str | None = None,
    output_dir: str | None = None,
) -> dict:
    """
    Main entry point for Technical Health Assessment.
    Currently delegates to existing auditor for Express tier.
    Other tiers return structured placeholder.
    """
    result = {
        "target": target,
        "tier": tier,
        "mode": mode,
        "status": "started",
        "limitations": [],
    }

    if tier == "express":
        if auditor_audit is None:
            result["status"] = "error"
            result["error"] = "nico.auditor not available"
            return result

        # Delegate to existing working auditor for now
        try:
            audit_result = auditor_audit(target, tier="full", mode=mode, use_swarm=use_swarm)
            result.update({
                "status": "completed",
                "delegated_to": "nico.auditor",
                "findings_count": audit_result.get("findings_count", 0),
                "repairs_count": audit_result.get("repairs_count", 0),
            })
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

    else:
        # Placeholder for Mid / Full tiers
        result["status"] = "not_implemented_yet"
        result["limitations"].append(f"{tier} tier not fully implemented in Phase 2")
        result["limitations"].append("Requires client_context, QA artifacts, and stakeholder input for Mid tier")

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        # Future: write JSON/Markdown reports here

    return result


def main():
    parser = argparse.ArgumentParser(
        prog="nico.assessment",
        description="NICO Technical Health Assessment (Express / Mid / Full)"
    )
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

    print(result)
    return result


if __name__ == "__main__":
    main()
