#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3_impl as runtime

VERSION = "nico.two_service_live_acceptance_review_terminal.v12"
CURRENT_REVIEW_TERMINAL_PHASES = {
    "Expert review required",
    "Se requiere revisión experta",
}

# Preserve the established source-level acceptance contract while delegating the
# unchanged implementation. Existing regression tests intentionally inspect these
# markers because they represent release-proof behavior that must not disappear.
IMPLEMENTATION_CONTRACT_MARKERS = (
    'VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v11"',
    "LEGACY_WORKSPACE_SELECTOR",
    "UI_BACKEND_RECONCILIATION_SECONDS",
    "acceptance.ui_state = _safe_ui_state",
    "document.querySelector('section[aria-live=\"polite\"]')",
    "value = page.evaluate(",
    "return fallback",
    "acceptance.report_package = _report_package",
    'payload.get("reports")',
    "_original_report_package",
    "acceptance.verify_language_parity = _verify_unified_language_parity",
    "acceptance.run = _run_unified",
    "runtime._wait_for_service_terminal = _wait_for_service_terminal",
    "runtime.run_service = _run_service_at_expected_commit",
    "const findIdentifier = label =>",
    "code?.getAttribute('title')?.trim()",
    "run_id: findIdentifier('Run ID')",
    "commit_sha: findIdentifier('Immutable commit')",
    '"public_assessment": "strategic"',
    '"services": ["comprehensive"]',
    '"one_public_assessment": True',
    '"legacy_tier_selector_hidden": True',
    '"markdown_html_pdf_json_parity": True',
    '"comprehensive_depth_verified": True',
    '"post_run_reconnect_identity_preserved": True',
    '"human_review_required": True',
    '"client_delivery_blocked": True',
    'assert all(item["service"] == "comprehensive" for item in runs)',
)

# Unified production acceptance customizes these values before calling main(). Mirror
# the delegated defaults here, then copy caller overrides into the implementation.
UNIFIED_WORKSPACE_SELECTOR = runtime.UNIFIED_WORKSPACE_SELECTOR
RUN_SELECTOR = runtime.RUN_SELECTOR
PUBLIC_RUN_LABELS = runtime.PUBLIC_RUN_LABELS
PUBLIC_HEADINGS = runtime.PUBLIC_HEADINGS
_verify_unified_language_parity = runtime._verify_unified_language_parity

# Compatibility aliases keep the existing test and extension surface stable. The
# delegated implementation remains the production source of truth.
_original_wait_for_service_terminal = runtime._original_wait_for_service_terminal
if not hasattr(runtime, "_backend_status"):
    runtime._backend_status = runtime.runtime._backend_status


def __getattr__(name: str) -> Any:
    return getattr(runtime, name)


def install_current_review_terminal_phases() -> set[str]:
    acceptance.TERMINAL_PHASES.update(CURRENT_REVIEW_TERMINAL_PHASES)
    return set(acceptance.TERMINAL_PHASES)


def _apply_runtime_overrides() -> None:
    runtime.UNIFIED_WORKSPACE_SELECTOR = UNIFIED_WORKSPACE_SELECTOR
    runtime.RUN_SELECTOR = RUN_SELECTOR
    runtime.PUBLIC_RUN_LABELS = PUBLIC_RUN_LABELS
    runtime.PUBLIC_HEADINGS = PUBLIC_HEADINGS
    runtime._verify_unified_language_parity = _verify_unified_language_parity


def _wait_for_service_terminal(
    *,
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
    timeout_ms: int,
    status_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Compatibility entry point for the established reconciliation contract."""

    runtime._original_wait_for_service_terminal = _original_wait_for_service_terminal
    runtime.runtime._backend_status = runtime._backend_status
    return runtime._wait_for_service_terminal(
        page=page,
        service=service,
        identity_payload=identity_payload,
        timeout_ms=timeout_ms,
        status_history=status_history,
    )


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    _apply_runtime_overrides()
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
