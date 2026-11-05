from __future__ import annotations

import sys
from pathlib import Path

# Workflow execution by file path exposes scripts/, not the checkout root.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from nico import production_release_gate  # noqa: E402

SPANISH_PROOF_WORKFLOW = "Spanish Comprehensive Production Proof"

if SPANISH_PROOF_WORKFLOW not in production_release_gate.REQUIRED_WORKFLOWS:
    production_release_gate.REQUIRED_WORKFLOWS = (
        *production_release_gate.REQUIRED_WORKFLOWS,
        SPANISH_PROOF_WORKFLOW,
    )

from check_production_release import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
