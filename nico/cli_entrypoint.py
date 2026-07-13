from __future__ import annotations

import argparse
import json
from typing import Any

from nico.cli import (
    memory_summary,
    verify_latest,
    verify_repair_by_id,
)
from nico.local_reporting_service import generate_reports, report_text
from nico.local_runtime_config import DB_PATH
from nico.local_scan_service import (
    run_scan,
    scan_drift_demo,
    scan_test_lab,
    scanner_availability,
)
from nico.local_store import LocalStore


CLI_COMMANDS = (
    "scan",
    "scan-test-lab",
    "scan-drift-demo",
    "report",
    "verify",
    "memory",
    "policy",
    "scanner-availability",
    "assessment",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nico")
    parser.add_argument("--swarm", action="store_true", help="Enable RYE swarm bug finding")
    sub = parser.add_subparsers(dest="cmd")

    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("target")
    sub.add_parser("scan-test-lab")
    sub.add_parser("scan-drift-demo")

    report_parser = sub.add_parser("report")
    report_parser.add_argument("which", nargs="?", default="latest")

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("which", nargs="?", default="latest")
    verify_parser.add_argument("--repair-id")

    sub.add_parser("memory")

    policy_parser = sub.add_parser("policy")
    policy_parser.add_argument("action", nargs="?", default="show")

    sub.add_parser("scanner-availability")

    assessment_parser = sub.add_parser("assessment")
    assessment_parser.add_argument("target")
    assessment_parser.add_argument("--tier", default="express", choices=["express", "mid", "full"])
    assessment_parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    assessment_parser.add_argument("--swarm", action="store_true")
    assessment_parser.add_argument("--output", default=None)
    return parser


def _scan_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_id": result["scan"]["id"],
        "findings": len(result["scan"]["findings"]),
        "drift": len(result["drift"]),
        "repairs": len(result["repairs"]),
    }


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.cmd == "scan":
        print(json.dumps(_scan_summary(run_scan(args.target)), indent=2))
        return
    if args.cmd == "scan-test-lab":
        print(json.dumps(_scan_summary(scan_test_lab()), indent=2))
        return
    if args.cmd == "scan-drift-demo":
        print(json.dumps(_scan_summary(scan_drift_demo()), indent=2))
        return
    if args.cmd == "report":
        if args.which in {"owner", "developer", "reparodynamic", "compliance"}:
            print(report_text(args.which))
        else:
            print(json.dumps(generate_reports(), indent=2))
        return
    if args.cmd == "verify":
        result = verify_repair_by_id(args.repair_id) if args.repair_id else verify_latest()
        print(json.dumps(result, indent=2))
        return
    if args.cmd == "memory":
        print(json.dumps(memory_summary(), indent=2))
        return
    if args.cmd == "policy":
        print(json.dumps(LocalStore(DB_PATH).policy(), indent=2))
        return
    if args.cmd == "scanner-availability":
        print(json.dumps(scanner_availability(), indent=2))
        return
    if args.cmd == "assessment":
        try:
            from nico.assessment import run_assessment

            result = run_assessment(
                target=args.target,
                tier=args.tier,
                mode=args.mode,
                use_swarm=args.swarm,
                output_dir=args.output,
            )
            print(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            print({"error": str(exc)})
        return
    parser.print_help()


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    dispatch(parser.parse_args(argv), parser)


if __name__ == "__main__":
    main()
