from __future__ import annotations

import json
from pathlib import Path


def test_accurate_green_release_contract_is_fail_closed() -> None:
    contract = json.loads(Path("audit-results/accurate-green-release-contract.json").read_text(encoding="utf-8"))

    assert contract["technical_green_threshold"] == 80
    assert contract["verified_green_requires"] == [
        "technical_score_at_least_80",
        "evidence_assurance_verified",
        "canonical_risk_disposition_green",
    ]
    assert contract["score_and_assurance_separate"] is True
    assert contract["missing_evidence_never_green"] is True
    assert contract["human_review_required"] is True
    assert contract["client_delivery_allowed"] is False
