#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import completed_run_two_pass_acceptance_v1 as production
from authenticated_proof_browser_v1 import AuthenticatedProofBrowser
from comprehensive_production_run_handoff_v1 import require_canonical_json_digest
from playwright.sync_api import sync_playwright as real_sync_playwright

VERSION = "nico.completed_run_two_pass_authenticated_acceptance.v2"
GUARD_ENV = "NICO_AUTHENTICATED_PROOF_WRAPPER_ACTIVE"


class _BrowserType:
    def __init__(self, browser_type: Any, origin: str, wrappers: list[AuthenticatedProofBrowser]) -> None:
        self._browser_type = browser_type
        self._origin = origin
        self._wrappers = wrappers

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser_type, name)

    def launch(self, *args: Any, **kwargs: Any) -> AuthenticatedProofBrowser:
        wrapped = AuthenticatedProofBrowser(
            self._browser_type.launch(*args, **kwargs),
            self._origin,
        )
        self._wrappers.append(wrapped)
        return wrapped


class _Playwright:
    def __init__(self, playwright: Any, origin: str, wrappers: list[AuthenticatedProofBrowser]) -> None:
        self._playwright = playwright
        self.chromium = _BrowserType(playwright.chromium, origin, wrappers)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._playwright, name)


class _SyncPlaywright:
    def __init__(self, origin: str, wrappers: list[AuthenticatedProofBrowser]) -> None:
        self._origin = origin
        self._wrappers = wrappers
        self._manager: Any | None = None

    def __enter__(self) -> _Playwright:
        self._manager = real_sync_playwright()
        return _Playwright(self._manager.__enter__(), self._origin, self._wrappers)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        assert self._manager is not None
        return self._manager.__exit__(exc_type, exc, traceback)


def _session_cookie(wrappers: list[AuthenticatedProofBrowser]) -> str:
    for wrapper in reversed(wrappers):
        if wrapper.latest_cookie_header:
            return wrapper.latest_cookie_header
    raise RuntimeError("authenticated_completed_run_cookie_unavailable")


def main(argv: list[str] | None = None) -> int:
    args = production.parse_args(argv)
    wrappers: list[AuthenticatedProofBrowser] = []
    original_sync_playwright = production.sync_playwright
    original_read_final = production._read_final_canonical
    original_write = production._write
    prior_guard = os.environ.get(GUARD_ENV)

    def authenticated_sync_playwright() -> _SyncPlaywright:
        return _SyncPlaywright(args.frontend_url, wrappers)

    def authenticated_read_final(frontend_url: str, run_id: str):
        request = urllib.request.Request(
            f"{frontend_url.rstrip('/')}/api/nico/assessment/comprehensive-run/{run_id}/report/json",
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-store",
                "Cookie": _session_cookie(wrappers),
            },
        )
        with urllib.request.urlopen(
            request,
            timeout=production.FINAL_CANONICAL_READ_TIMEOUT_SECONDS,
        ) as response:
            assert 200 <= response.status < 300
            canonical_digest_header = response.headers.get(
                "x-nico-canonical-truth-sha256"
            )
            canonical = json.loads(response.read().decode("utf-8"))
        assert isinstance(canonical, dict)
        canonical_digest = require_canonical_json_digest(
            canonical,
            canonical_digest_header,
        )
        return canonical, canonical_digest

    def authenticated_write(path: Path, value: Any) -> None:
        output = value
        if isinstance(value, dict) and value.get("artifact_schema") == production.VERSION:
            output = dict(value)
            output["authenticated_production_proof"] = True
            output["authenticated_proof_version"] = VERSION
            output["github_actions_proof_sessions"] = [
                proof for wrapper in wrappers for proof in wrapper.proofs
            ]
        original_write(path, output)

    production.sync_playwright = authenticated_sync_playwright
    production._read_final_canonical = authenticated_read_final
    production._write = authenticated_write
    os.environ[GUARD_ENV] = "1"
    try:
        return production.main(argv)
    finally:
        production.sync_playwright = original_sync_playwright
        production._read_final_canonical = original_read_final
        production._write = original_write
        if prior_guard is None:
            os.environ.pop(GUARD_ENV, None)
        else:
            os.environ[GUARD_ENV] = prior_guard


if __name__ == "__main__":
    raise SystemExit(main())
