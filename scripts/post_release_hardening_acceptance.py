from __future__ import annotations

import argparse
import json
from pathlib import Path

from nico.hardening_acceptance import acceptance_mapping, evaluate_two_pass_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require two production-equivalent post-release hardening passes on one immutable SHA."
    )
    parser.add_argument("--pass-one", type=Path, required=True)
    parser.add_argument("--pass-two", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = evaluate_two_pass_acceptance(
            args.pass_one,
            args.pass_two,
            expected_sha=args.expected_sha,
        )
        payload = acceptance_mapping(result)
    except Exception as exc:
        payload = {
            "artifact_schema": "nico.post_release_hardening_acceptance.v1",
            "status": "failed",
            "expected_sha": args.expected_sha,
            "passes_required": 2,
            "passes_completed": 0,
            "error_type": type(exc).__name__,
            "error_code": str(exc),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
