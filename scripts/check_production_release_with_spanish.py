from __future__ import annotations

from nico import production_release_gate

SPANISH_PROOF_WORKFLOW = "Spanish Comprehensive Production Proof"

if SPANISH_PROOF_WORKFLOW not in production_release_gate.REQUIRED_WORKFLOWS:
    production_release_gate.REQUIRED_WORKFLOWS = (
        *production_release_gate.REQUIRED_WORKFLOWS,
        SPANISH_PROOF_WORKFLOW,
    )

from check_production_release import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
