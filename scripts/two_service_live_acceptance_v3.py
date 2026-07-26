#!/usr/bin/env python3
from __future__ import annotations

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3_impl as runtime

VERSION = "nico.two_service_live_acceptance_review_terminal.v12"
CURRENT_REVIEW_TERMINAL_PHASES = {
    "Expert review required",
    "Se requiere revisión experta",
}


def install_current_review_terminal_phases() -> set[str]:
    acceptance.TERMINAL_PHASES.update(CURRENT_REVIEW_TERMINAL_PHASES)
    return set(acceptance.TERMINAL_PHASES)


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
