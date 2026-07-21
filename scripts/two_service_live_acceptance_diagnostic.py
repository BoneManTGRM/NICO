#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from typing import Any

import two_service_live_acceptance as acceptance


def main(argv: list[str] | None = None) -> int:
    config = acceptance.parse(argv)
    try:
        result: dict[str, Any] = acceptance.run(config)
    except Exception as exc:
        result = {
            "artifact_schema": "nico.two_service_live_acceptance.v1",
            "status": "failed",
            "live_production_claim": True,
            "authorized_repository": config.repository,
            "expected_deployed_sha": config.expected_sha,
            "error": f"{type(exc).__name__}: {acceptance.text(exc, 1200)}",
            "traceback": traceback.format_exc(limit=20),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Two-service live acceptance: {result['status']}")
    if result.get("traceback"):
        print(result["traceback"], file=sys.stderr)
    print(f"Evidence: {config.output}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
