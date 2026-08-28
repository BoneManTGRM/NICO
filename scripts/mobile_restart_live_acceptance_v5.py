#!/usr/bin/env python3
from __future__ import annotations

import mobile_restart_live_acceptance_v1 as recovery
import mobile_restart_live_acceptance_v3 as single_dispatch
from mobile_exact_sha_navigation_v1 import install_exact_sha_navigation
from mobile_pdf_download_action_proof_v1 import install_ui_pdf_download_proof
from provider_neutral_repository_locator_contract_v1 import (
    install_provider_neutral_repository_locator,
)

VERSION = "nico.mobile_restart_live_acceptance.single_dispatch_pdf_download.v5"


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    recovery._require_existing_source_args(args)
    install_exact_sha_navigation(single_dispatch, args.expected_sha)
    install_provider_neutral_repository_locator(single_dispatch)
    install_ui_pdf_download_proof(recovery)
    return single_dispatch.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
