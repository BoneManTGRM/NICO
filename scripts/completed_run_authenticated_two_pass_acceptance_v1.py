#!/usr/bin/env python3
"""Run the unchanged two-pass evidence contract with origin-scoped authentication."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import completed_run_two_pass_acceptance_v1 as proof
from github_actions_nico_proof_auth_v1 import (
    AuthenticatedBrowser,
    SESSION_HEADER,
    _https_origin,
    acquire_production_proof_session,
)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Canonical report reads must terminate on the trusted origin. Never
        # forward proof credentials through a same-origin or cross-origin redirect.
        return None


def authenticated_report_opener(frontend_url: str, session: str):
    origin = _https_origin(frontend_url)
    opener = build_opener(_RejectRedirects())

    def open_report(request: Request, *, timeout: float) -> Any:
        parsed = urlsplit(request.full_url)
        observed_origin = _https_origin(f"{parsed.scheme}://{parsed.netloc}")
        if (
            observed_origin != origin
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or request.get_method() != "GET"
            or not parsed.path.startswith("/api/nico/assessment/comprehensive-run/")
            or not parsed.path.endswith("/report/json")
        ):
            raise ValueError("production_proof_report_origin_or_path_rejected")
        protected = Request(
            request.full_url,
            headers={**dict(request.header_items()), SESSION_HEADER: session},
            method="GET",
        )
        return opener.open(protected, timeout=timeout)

    return open_report


def main(argv: list[str] | None = None) -> int:
    args = proof.parse_args(argv)
    session, retained = acquire_production_proof_session(args.frontend_url)
    try:
        return proof.main(
            argv,
            browser_wrapper=lambda raw: AuthenticatedBrowser(
                raw, session=session, frontend_url=args.frontend_url,
            ),
            open_request=authenticated_report_opener(args.frontend_url, session),
        )
    finally:
        retained.clear()
        session = ""


if __name__ == "__main__":
    raise SystemExit(main())
