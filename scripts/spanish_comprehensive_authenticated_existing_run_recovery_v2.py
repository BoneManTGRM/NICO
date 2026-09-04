#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import spanish_comprehensive_existing_run_recovery_v1 as recovery
from github_actions_proof_session_v1 import (
    authenticate_browser_context,
    cookie_header,
)

VERSION = "nico.spanish_comprehensive_authenticated_existing_run_recovery.v2"
_ACTIVE_COOKIE_HEADER = ""


class _AuthenticatedBrowser:
    def __init__(self, browser: Any, frontend_origin: str) -> None:
        self._browser = browser
        self._origin = frontend_origin.rstrip("/")
        self.proofs: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    def new_context(self, **kwargs: Any) -> Any:
        global _ACTIVE_COOKIE_HEADER
        context = self._browser.new_context(**kwargs)
        try:
            proof = authenticate_browser_context(context, self._origin)
            _ACTIVE_COOKIE_HEADER = cookie_header(context, self._origin)
        except Exception:
            context.close()
            raise
        self.proofs.append(proof)
        return context


def _authenticated_httpx_client(original_client: type[Any]) -> type[Any]:
    class AuthenticatedClient(original_client):
        def get(self, url: Any, *args: Any, **kwargs: Any) -> Any:
            headers = dict(kwargs.pop("headers", {}) or {})
            if _ACTIVE_COOKIE_HEADER:
                headers["Cookie"] = _ACTIVE_COOKIE_HEADER
            return super().get(url, *args, headers=headers, **kwargs)

    return AuthenticatedClient


def main(argv: list[str] | None = None) -> int:
    global _ACTIVE_COOKIE_HEADER
    original_run = recovery.run_recovery
    original_client = recovery.spanish.httpx.Client

    def authenticated_run(browser: Any, args: Any) -> dict[str, Any]:
        wrapped = _AuthenticatedBrowser(browser, args.frontend_url)
        result = original_run(wrapped, args)
        result["authenticated_production_proof"] = True
        result["github_actions_proof_sessions"] = list(wrapped.proofs)
        result["acceptance_version"] = VERSION
        return result

    recovery.run_recovery = authenticated_run
    recovery.spanish.httpx.Client = _authenticated_httpx_client(original_client)
    try:
        return recovery.main(argv)
    finally:
        recovery.run_recovery = original_run
        recovery.spanish.httpx.Client = original_client
        _ACTIVE_COOKIE_HEADER = ""


if __name__ == "__main__":
    raise SystemExit(main())
