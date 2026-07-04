#!/usr/bin/env python3
"""NICO Assessment Orchestrator (Phase 2)

Current capabilities:
- Argument parsing for new assessment commands
- Express tier delegates to existing working auditor
- Basic JSON report when --output is provided
- Honest placeholders for Mid/Full

Error handling improved in this version.
"""

import argparse
import json
from datetime import datetime
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

    if tier == "express":
        if auditor_audit is None:
            result.update({
                "status": "error",
                "error": "nico.auditor not importable",
                "limitations": ["Existing auditor unavailable"]
            })
            return result

        try:
            audit_result = auditor_audit(
                target,
                tier="full",
                mode=mode,
                use_swarm=use_swarm,
            )

            # Proper error handling for auditor failures (e.g. clone/network error)
            if isinstance(audit_result, dict) and audit_result.get("error"):
                result.update({
                    "status": "completed_with_limitations",
                    "error": audit_result["error"],
                    "limitations": ["Auditor reported error (likely clone/network failure)"]
                })
            else:
                result.update({
                    "status": "completed",
                    "delegated_to": "nico.auditor",
                    "findings_count": audit_result.get("findings_count", 0),
                    "repairs_count": audit_result.get("repairs_count", 0),
                })

        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "limitations": ["Unexpected error during assessment"]
            })

    else:
        result["status"] = "not_implemented_yet"
        result["limitations"].append(f"{tier.upper()} tier is placeholder in current Phase 2")
        result["limitations"].append("Requires client_context, QA artifacts, stakeholder input, and module implementations")

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / f"assessment_{result.get('assessment_id', 'unknown')}.json"
        report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_written"] = str(report_path)

    return result


def main():
    parser = argparse.ArgumentParser(
        prog="nico.assessment",
        description="NICO Technical Health Assessment"
    )
    parser.add_argument("target", help="GitHub repo URL or local path")
    parser.add_argument("--tier", default="express", choices=["express", "mid", "full"])
    parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    parser.add_argument("--swarm", action="store_true")
    parser.add_argument("--github-token-env", default=None)
    parser.add_argument("--client-context", default=None)
    parser.add_argument("--output", default=None, help="Directory to write JSON report")

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
