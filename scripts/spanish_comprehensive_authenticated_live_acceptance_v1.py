#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any

import spanish_comprehensive_live_acceptance_v3 as proof
from github_actions_nico_proof_auth_v1 import (
    AuthenticatedBrowser,
    acquire_production_proof_session,
    install_authenticated_httpx_client,
)

VERSION = "nico.spanish_comprehensive_authenticated_live_acceptance.v1"


def _frontend_url(argv: list[str] | None) -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--frontend-url", required=True)
    values, _ = parser.parse_known_args(argv)
    return str(values.frontend_url).rstrip("/")


def main(argv: list[str] | None = None) -> int:
    frontend_url = _frontend_url(argv)
    session, retained = acquire_production_proof_session(frontend_url)
    proof.install_spanish_terminal_boundary()
    install_authenticated_httpx_client(proof, session)
    original_run = proof.base.run_proof

    def authenticated_run(browser: Any, args: Any) -> dict[str, Any]:
        result = original_run(
            AuthenticatedBrowser(
                browser,
                session=session,
                frontend_url=args.frontend_url,
            ),
            args,
        )
        result["github_actions_oidc_session_verified"] = True
        result["production_proof_auth_version"] = VERSION
        result["production_proof_session_scope"] = retained["scope"]
        result["production_proof_session_release_sha"] = retained["release_sha"]
        result["production_proof_session_repository"] = retained["repository"]
        result["production_proof_session_workflow_ref"] = retained["workflow_ref"]
        result["production_proof_session_run_id"] = retained["run_id"]
        result["production_proof_session_run_attempt"] = retained["run_attempt"]
        result["production_proof_session_token_retained"] = False
        return result

    proof.base.run_proof = authenticated_run
    try:
        return proof.telemetry.main(argv)
    finally:
        proof.base.run_proof = original_run


if __name__ == "__main__":
    raise SystemExit(main())
