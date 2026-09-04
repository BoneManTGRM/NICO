#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import mobile_restart_live_acceptance_v1 as recovery
import mobile_restart_live_acceptance_v6 as proof
from github_actions_nico_proof_auth_v1 import (
    AuthenticatedBrowser,
    acquire_production_proof_session,
)

VERSION = "nico.ios_webkit_authenticated_live_acceptance.v1"


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    session, retained = acquire_production_proof_session(args.frontend_url)
    original_launch = recovery._launch_webkit

    def authenticated_launch(playwright: Any) -> Any:
        raw = original_launch(playwright)
        return AuthenticatedBrowser(
            raw,
            session=session,
            frontend_url=args.frontend_url,
        )

    recovery._launch_webkit = authenticated_launch
    try:
        return proof.main(argv)
    finally:
        recovery._launch_webkit = original_launch
        session = ""  # noqa: F841 - shorten in-process credential lifetime
        retained.clear()


if __name__ == "__main__":
    raise SystemExit(main())
