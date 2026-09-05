#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any

from production_proof_observer_v1 import ProofObserver

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
    original_fetch = proof._fetch_canonical_json

    def checked_canonical_json(*, frontend_origin: str, run_id: str):
        from nico.complete_assessment_gate_v1 import require_complete_assessment

        canonical, header, digest = original_fetch(frontend_origin=frontend_origin, run_id=run_id)
        identity = canonical.get("identity") or {}
        require_complete_assessment(canonical, expected_commit=str(identity.get("commit_sha") or ""), expected_run=run_id)
        return canonical, header, digest

    proof._fetch_canonical_json = checked_canonical_json

    def authenticated_run(browser: Any, args: Any) -> dict[str, Any]:
        original_wait = proof.telemetry._wait_for_terminal_with_telemetry
        original_emit = proof.telemetry._emit
        with ProofObserver(origin=frontend_url, session=session, output=args.output,
                           run_id=lambda: str(getattr(args, "proof_run_id", ""))) as observer:
            def observed_emit(snapshot: dict[str, Any]) -> None:
                original_emit(snapshot)
                observer.pulse()

            def observed_wait(*wait_args: Any, **wait_kwargs: Any) -> Any:
                observer.watch_browser_wait(True)
                try:
                    return original_wait(*wait_args, **wait_kwargs)
                finally:
                    observer.watch_browser_wait(False)

            # telemetry.main has already installed the wait alias before this call.
            previous_wait = proof.base.recovery._wait_for_terminal
            proof.base.recovery._wait_for_terminal = observed_wait
            proof.telemetry._emit = observed_emit
            try:
                result = original_run(
                    AuthenticatedBrowser(browser, session=session, frontend_url=args.frontend_url),
                    args,
                )
            finally:
                proof.base.recovery._wait_for_terminal = previous_wait
                proof.telemetry._emit = original_emit
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
        proof._fetch_canonical_json = original_fetch


if __name__ == "__main__":
    raise SystemExit(main())
