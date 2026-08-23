#!/usr/bin/env python3
from __future__ import annotations

from functools import wraps
from typing import Any

import spanish_comprehensive_live_acceptance_v1 as base
import spanish_comprehensive_live_acceptance_v2 as telemetry
from provider_neutral_repository_locator_contract_v1 import SPANISH_REPOSITORY_LABEL

VERSION = "nico.spanish_comprehensive_live_acceptance.v3"
SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"
SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"
SPANISH_TERMINAL_REPORT = "Completa"
_MARKER = "__nico_spanish_terminal_boundary_v3__"


def install_spanish_terminal_boundary() -> None:
    """Bind current localized repository and terminal semantics to exact proof."""

    base.SPANISH_REPO_LABEL = SPANISH_REPOSITORY_LABEL
    base.SPANISH_TERMINAL_PHASE = SPANISH_TERMINAL_PHASE
    current = base.recovery._wait_for_terminal_ui_ready
    if getattr(current, _MARKER, False):
        return

    @wraps(current)
    def wait_for_terminal_ui_ready(*args: Any, **kwargs: Any) -> dict[str, Any]:
        terminal = current(*args, **kwargs)
        assert terminal.get("phase") == SPANISH_TERMINAL_PHASE, terminal
        assert terminal.get("review") == SPANISH_TERMINAL_REVIEW, terminal
        assert terminal.get("report") == SPANISH_TERMINAL_REPORT, terminal
        return terminal

    setattr(wait_for_terminal_ui_ready, _MARKER, True)
    setattr(wait_for_terminal_ui_ready, "_nico_previous", current)
    base.recovery._wait_for_terminal_ui_ready = wait_for_terminal_ui_ready
    telemetry.recovery._wait_for_terminal_ui_ready = wait_for_terminal_ui_ready


def main(argv: list[str] | None = None) -> int:
    install_spanish_terminal_boundary()
    return telemetry.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
