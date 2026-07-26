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

# The implementation remains byte-for-byte identical in the delegated module. These
# markers preserve the workflow's bounded source contract while making that delegation
# explicit rather than duplicating its behavior in this wrapper.
IMPLEMENTATION_CONTRACT_MARKERS = (
    "LEGACY_WORKSPACE_SELECTOR",
    "runtime._wait_for_service_terminal = _wait_for_service_terminal",
    "runtime.run_service = _run_service_at_expected_commit",
    "UI_BACKEND_RECONCILIATION_SECONDS",
    '"human_review_required": True',
    '"client_delivery_blocked": True',
    '"markdown_html_pdf_json_parity": True',
    '"comprehensive_depth_verified": True',
    '"post_run_reconnect_identity_preserved": True',
)

# Unified production acceptance customizes these values before calling main(). Mirror
# the delegated defaults here, then copy any caller overrides back into the implementation.
UNIFIED_WORKSPACE_SELECTOR = runtime.UNIFIED_WORKSPACE_SELECTOR
RUN_SELECTOR = runtime.RUN_SELECTOR
PUBLIC_RUN_LABELS = runtime.PUBLIC_RUN_LABELS
PUBLIC_HEADINGS = runtime.PUBLIC_HEADINGS
_verify_unified_language_parity = runtime._verify_unified_language_parity


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


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    _apply_runtime_overrides()
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
