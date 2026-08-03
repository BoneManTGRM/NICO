#!/usr/bin/env python3
from __future__ import annotations

import mobile_restart_live_acceptance_v1 as recovery
import mobile_restart_live_acceptance_v4 as webkit_single_dispatch
from mobile_pdf_download_action_proof_v1 import install_ui_pdf_download_proof

VERSION = "nico.mobile_restart_live_acceptance.webkit_pdf_download.v6"


def main(argv: list[str] | None = None) -> int:
    install_ui_pdf_download_proof(recovery)
    return webkit_single_dispatch.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
