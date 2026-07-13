from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from nico.production_smoke_config import (
    CONFIRMATION_PHRASE,
    DEFAULT_POLL_ATTEMPTS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    EVIDENCE_KIND,
    SCHEMA_VERSION,
    SmokeConfig,
    SmokeFailure,
    _IDENTIFIER,
    _REPOSITORY,
    utc_now,
    validate_config,
)
from nico.production_smoke_run import build_smoke_artifact
from nico.production_smoke_transport import UrlLibTransport, verify_deployment_statuses

def _safe_failed_scope(value: str, pattern: re.Pattern[str]) -> str:
    candidate = str(value or "").strip()
    return candidate if pattern.fullmatch(candidate) else ""

def failed_artifact(config: SmokeConfig | None, code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "live_claim": False,
        "authorization_confirmed": False,
        "status": "failed",
        "generated_at": utc_now(),
        "repository": _safe_failed_scope(config.repository, _REPOSITORY) if config else "",
        "customer_id": _safe_failed_scope(config.customer_id, _IDENTIFIER) if config else "",
        "project_id": _safe_failed_scope(config.project_id, _IDENTIFIER) if config else "",
        "error": {"code": code, "message": message[:300]},
        "proof": {
            "one_start_per_tier": False,
            "exact_run_continuation": False,
            "human_review_boundary_preserved": False,
            "no_client_ready_claim": True,
        },
        "tiers": [],
        "guardrail": "Failed smoke evidence is not completion proof and must not be treated as a passing production claim.",
    }

def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeFailure("browser_evidence_missing", "Production browser evidence file could not be read.") from None
    if not isinstance(value, dict):
        raise SmokeFailure("browser_evidence_missing", "Production browser evidence file must contain a JSON object.")
    return value

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one controlled authorized production assessment per NICO tier.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--browser-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--poll-attempts", type=int, default=DEFAULT_POLL_ATTEMPTS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    raw_config = SmokeConfig(
        frontend_url=args.frontend_url,
        backend_url=args.backend_url,
        repository=args.repository,
        customer_id=args.customer_id,
        project_id=args.project_id,
        authorization_reference=args.authorization_reference,
        github_repository=args.github_repository,
        github_sha=args.github_sha,
        confirmation=args.confirmation,
        poll_attempts=args.poll_attempts,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    config: SmokeConfig | None = None
    try:
        config = validate_config(raw_config, dict(os.environ))
        deployment = verify_deployment_statuses(
            config.github_repository,
            config.github_sha,
            os.environ["GITHUB_TOKEN"],
        )
        browser = validate_browser_evidence(load_json(args.browser_evidence), config.github_sha)
        transport = UrlLibTransport(
            config.backend_url,
            os.environ["NICO_PRODUCTION_SMOKE_ADMIN_TOKEN"],
        )
        artifact = build_smoke_artifact(config, transport, deployment, browser)
        write_json(output, artifact)
        return 0
    except SmokeFailure as exc:
        write_json(output, failed_artifact(config, exc.code, exc.safe_message))
        print(f"Production assessment smoke failed: {exc.code}", file=sys.stderr)
        return 1
    except Exception:
        write_json(
            output,
            failed_artifact(
                config,
                "unexpected_smoke_error",
                "Production smoke stopped on an unexpected internal error; no completion claim was retained.",
            ),
        )
        print("Production assessment smoke failed: unexpected_smoke_error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
