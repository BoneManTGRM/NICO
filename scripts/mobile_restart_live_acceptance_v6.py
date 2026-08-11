#!/usr/bin/env python3
from __future__ import annotations

import mobile_restart_live_acceptance_v1 as recovery
import mobile_restart_live_acceptance_v3 as single_dispatch
import mobile_restart_live_acceptance_v4 as webkit_single_dispatch
from mobile_exact_sha_navigation_v1 import install_exact_sha_navigation
from mobile_pdf_download_action_proof_v1 import install_ui_pdf_download_proof

VERSION = "nico.mobile_restart_live_acceptance.webkit_pdf_download.v6"


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    install_exact_sha_navigation(single_dispatch, args.expected_sha)
    install_ui_pdf_download_proof(recovery)
    return webkit_single_dispatch.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
