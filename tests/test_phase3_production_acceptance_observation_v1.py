from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "docs" / "phase3-production-acceptance-internal-mode-observation.json"


def test_phase3_acceptance_repair_preserves_fail_closed_client_boundary() -> None:
    payload = json.loads(OBSERVATION.read_text(encoding="utf-8"))

    assert payload["phase"] == 3
    assert payload["observed_intake_http_status"] == 422
    assert payload["client_engagement_validation_weakened"] is False
    assert payload["one_public_product"] == "NICO Comprehensive"
    assert payload["one_client_report"] is True
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
