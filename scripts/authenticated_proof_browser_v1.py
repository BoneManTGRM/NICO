from __future__ import annotations

from typing import Any

from github_actions_proof_session_v1 import (
    authenticate_browser_context,
    cookie_header,
)

VERSION = "nico.authenticated_proof_browser.v1"


class AuthenticatedProofBrowser:
    def __init__(self, browser: Any, frontend_origin: str) -> None:
        self._browser = browser
        self._origin = frontend_origin.rstrip("/")
        self.proofs: list[dict[str, Any]] = []
        self._cookie_headers: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    @property
    def latest_cookie_header(self) -> str:
        return self._cookie_headers[-1] if self._cookie_headers else ""

    def new_context(self, **kwargs: Any) -> Any:
        context = self._browser.new_context(**kwargs)
        try:
            proof = authenticate_browser_context(context, self._origin)
            header = cookie_header(context, self._origin)
        except Exception:
            context.close()
            raise
        self.proofs.append(proof)
        self._cookie_headers.append(header)
        return context


__all__ = ["AuthenticatedProofBrowser", "VERSION"]
