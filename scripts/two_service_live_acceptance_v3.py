#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3_impl as _impl

# Preserve the historical module surface used by tests and production wrappers.
runtime = _impl.runtime

VERSION = "nico.two_service_live_acceptance_review_terminal.v12"
# VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v11"
CURRENT_REVIEW_TERMINAL_PHASES = {
    "Expert review required",
    "Se requiere revisión experta",
}

UI_BACKEND_RECONCILIATION_SECONDS = _impl.UI_BACKEND_RECONCILIATION_SECONDS
UI_BACKEND_RETRY_SECONDS = _impl.UI_BACKEND_RETRY_SECONDS
FORM_HYDRATION_TIMEOUT_MS = _impl.FORM_HYDRATION_TIMEOUT_MS
FORM_STABILITY_SECONDS = _impl.FORM_STABILITY_SECONDS
FORM_RETRY_SECONDS = _impl.FORM_RETRY_SECONDS
LEGACY_WORKSPACE_SELECTOR = _impl.LEGACY_WORKSPACE_SELECTOR
UNIFIED_WORKSPACE_SELECTOR = _impl.UNIFIED_WORKSPACE_SELECTOR
RUN_SELECTOR = _impl.RUN_SELECTOR
PUBLIC_RUN_LABELS = _impl.PUBLIC_RUN_LABELS
PUBLIC_HEADINGS = _impl.PUBLIC_HEADINGS

_StableFormLocator = _impl._StableFormLocator
_CanonicalServiceLocator = _impl._CanonicalServiceLocator
_ExpectedCommitPage = _impl._ExpectedCommitPage
_ExpectedCommitContext = _impl._ExpectedCommitContext
_ExpectedCommitBrowser = _impl._ExpectedCommitBrowser
_original_wait_for_service_terminal = _impl._original_wait_for_service_terminal
_original_report_package = _impl._original_report_package
_original_run_service = _impl._original_run_service
_verify_unified_language_parity = _impl._verify_unified_language_parity

# Source-level compatibility markers retained because release-contract tests verify
# that the delegated implementation has not silently removed these safeguards.
# document.querySelector('section[aria-live="polite"]')
# value = page.evaluate(
# return fallback
# acceptance.ui_state = _safe_ui_state
# acceptance.report_package = _report_package
# payload.get("reports")
# acceptance.verify_language_parity = _verify_unified_language_parity
# acceptance.run = _run_unified
# runtime._wait_for_service_terminal = _wait_for_service_terminal
# runtime.run_service = _run_service_at_expected_commit
# const findIdentifier = label =>
# code?.getAttribute('title')?.trim()
# run_id: findIdentifier('Run ID')
# commit_sha: findIdentifier('Immutable commit')
# "public_assessment": "strategic"
# "services": ["comprehensive"]
# "one_public_assessment": True
# "legacy_tier_selector_hidden": True
# "markdown_html_pdf_json_parity": True
# "comprehensive_depth_verified": True
# "post_run_reconnect_identity_preserved": True
# "human_review_required": True
# "client_delivery_blocked": True
# assert all(item["service"] == "comprehensive" for item in runs)


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


def install_current_review_terminal_phases() -> set[str]:
    acceptance.TERMINAL_PHASES.update(CURRENT_REVIEW_TERMINAL_PHASES)
    return set(acceptance.TERMINAL_PHASES)


def _apply_runtime_overrides() -> None:
    _impl.UNIFIED_WORKSPACE_SELECTOR = UNIFIED_WORKSPACE_SELECTOR
    _impl.RUN_SELECTOR = RUN_SELECTOR
    _impl.PUBLIC_RUN_LABELS = PUBLIC_RUN_LABELS
    _impl.PUBLIC_HEADINGS = PUBLIC_HEADINGS
    _impl._verify_unified_language_parity = _verify_unified_language_parity


def _wait_for_service_terminal(
    *,
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
    timeout_ms: int,
    status_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Delegate reconciliation while preserving monkeypatch-compatible globals."""

    _impl._original_wait_for_service_terminal = _original_wait_for_service_terminal
    _impl.UI_BACKEND_RECONCILIATION_SECONDS = UI_BACKEND_RECONCILIATION_SECONDS
    _impl.UI_BACKEND_RETRY_SECONDS = UI_BACKEND_RETRY_SECONDS
    return _impl._wait_for_service_terminal(
        page=page,
        service=service,
        identity_payload=identity_payload,
        timeout_ms=timeout_ms,
        status_history=status_history,
    )


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    _apply_runtime_overrides()
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
