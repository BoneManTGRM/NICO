#!/usr/bin/env python3
"""Run an authorized deployed smoke check for NICO assessment tiers.

This command is intentionally fail-closed. It starts each requested tier exactly
once, requires the returned run identity, and only polls that same identity.
It does not retry start requests and does not claim production proof unless the
remote deployment itself returns successful evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


TERMINAL_STATUSES = {"complete", "completed", "blocked", "failed", "error", "timed_out"}
SUCCESS_STATUSES = {"complete", "completed"}


@dataclass(frozen=True)
class TierContract:
    name: str
    start_path: str
    status_path: str | None


TIERS = {
    "express": TierContract("express", "/assessment/github", None),
    "mid": TierContract("mid", "/assessment/mid-run", "/assessment/mid-run/{run_id}/status"),
    "full": TierContract("full", "/assessment/full-run", "/assessment/full-run/{run_id}/status"),
}


class SmokeFailure(RuntimeError):
    pass


def _json_request(base_url: str, path: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SmokeFailure(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SmokeFailure(f"{path} could not be reached: {exc.reason}") from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{path} returned non-JSON content") from exc
    if not isinstance(decoded, dict):
        raise SmokeFailure(f"{path} returned a non-object JSON payload")
    return decoded


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or payload.get("run_status") or "unknown").lower()


def _run_id(payload: dict[str, Any]) -> str:
    return str(payload.get("run_id") or payload.get("assessment_run_id") or "").strip()


def run_tier(
    base_url: str,
    contract: TierContract,
    common_payload: dict[str, Any],
    token: str,
    poll_seconds: float,
    max_polls: int,
) -> dict[str, Any]:
    payload = dict(common_payload)
    if contract.name == "express":
        payload["assessment_mode"] = "express"
    elif contract.name == "full":
        payload.update({
            "mode": "full",
            "build_reports": True,
            "create_final_review_request": True,
        })

    # Canonical start request: exactly one call. Never retry this request.
    current = _json_request(base_url, contract.start_path, payload, token)
    run_id = _run_id(current)
    status = _status(current)

    if not run_id:
        raise SmokeFailure(f"{contract.name} start response omitted run_id")

    if contract.status_path is None:
        if status not in SUCCESS_STATUSES:
            raise SmokeFailure(f"{contract.name} run {run_id} ended with status={status}")
        return {"tier": contract.name, "run_id": run_id, "status": status, "polls": 0}

    polls = 0
    while status not in TERMINAL_STATUSES and polls < max_polls:
        polls += 1
        time.sleep(poll_seconds)
        path = contract.status_path.format(run_id=run_id)
        current = _json_request(base_url, path, payload, token)
        returned_id = _run_id(current)
        if returned_id and returned_id != run_id:
            raise SmokeFailure(
                f"{contract.name} status changed run identity from {run_id} to {returned_id}"
            )
        status = _status(current)

    if status not in SUCCESS_STATUSES:
        raise SmokeFailure(
            f"{contract.name} run {run_id} did not complete successfully; status={status}, polls={polls}"
        )
    return {"tier": contract.name, "run_id": run_id, "status": status, "polls": polls}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--customer-id", default="smoke_customer")
    parser.add_argument("--project-id", default="smoke_project")
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorization-scope", required=True)
    parser.add_argument("--tiers", nargs="+", choices=sorted(TIERS), default=sorted(TIERS))
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = os.getenv("NICO_SMOKE_TOKEN", "")
    common_payload = {
        "repository": args.repository,
        "customer_id": args.customer_id,
        "project_id": args.project_id,
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": args.authorized_by,
        "authorization_scope": args.authorization_scope,
        "auto_continue": True,
    }

    results: list[dict[str, Any]] = []
    try:
        for tier in args.tiers:
            results.append(
                run_tier(
                    args.base_url,
                    TIERS[tier],
                    common_payload,
                    token,
                    args.poll_seconds,
                    args.max_polls,
                )
            )
    except SmokeFailure as exc:
        print(json.dumps({"status": "failed", "message": str(exc), "results": results}, indent=2))
        return 1

    print(json.dumps({"status": "complete", "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
