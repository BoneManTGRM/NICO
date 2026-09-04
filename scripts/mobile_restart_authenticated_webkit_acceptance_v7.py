#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import mobile_restart_live_acceptance_v1 as recovery
import mobile_restart_live_acceptance_v6 as proof
from authenticated_proof_browser_v1 import AuthenticatedProofBrowser

VERSION = "nico.mobile_restart_authenticated_webkit_acceptance.v7"


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    original_launch = recovery._launch_webkit
    original_write = recovery._write
    wrappers: list[AuthenticatedProofBrowser] = []

    def launch(playwright: Any) -> AuthenticatedProofBrowser:
        wrapped = AuthenticatedProofBrowser(
            original_launch(playwright),
            args.frontend_url,
        )
        wrappers.append(wrapped)
        return wrapped

    def write(path: Path, payload: dict[str, Any]) -> None:
        output = dict(payload)
        output["authenticated_production_proof"] = True
        output["authenticated_proof_version"] = VERSION
        output["github_actions_proof_sessions"] = [
            session for wrapper in wrappers for session in wrapper.proofs
        ]
        original_write(path, output)

    recovery._launch_webkit = launch
    recovery._write = write
    try:
        return proof.main(argv)
    finally:
        recovery._launch_webkit = original_launch
        recovery._write = original_write


if __name__ == "__main__":
    raise SystemExit(main())
