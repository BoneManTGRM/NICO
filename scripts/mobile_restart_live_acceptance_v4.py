#!/usr/bin/env python3
from __future__ import annotations

import mobile_restart_live_acceptance_v2 as webkit
import mobile_restart_live_acceptance_v3 as single_dispatch

VERSION = "nico.mobile_restart_live_acceptance.webkit_single_dispatch.v4"


def main(argv: list[str] | None = None) -> int:
    # v2 imports the v1 module object. Replace only its run entry point; v3 retains
    # the original v1 function privately and wraps the supplied WebKit browser.
    webkit.recovery.run_proof = single_dispatch.run_proof
    return webkit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
