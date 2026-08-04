from __future__ import annotations

from pathlib import Path

from nico.comprehensive_candidate_identity_v1 import (
    MODEL,
    expand_candidate_identities,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"


def _aggregate_register() -> dict:
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "findings": [
            {
                "finding_id": "NICO-SCAN-SECRET",
                "raw_fingerprint": "a" * 64,
                "scanner": "gitleaks",
                "category": "secret",
                "rule_id": "count-only",
                "severity": "unknown",
                "confidence": "unknown",
                "source_path": "",
                "line": None,
                "evidence": "16 review-required candidates retained by count.",
                "disposition": "review_required",
                "evidence_quality": "count_only",
                "occurrence_count": 16,
                "exact_commit_sha": "3c4352ae1873c547dd01406da833d2faedb5039b",
                "human_review_required": True,
            },
            {
                "finding_id": "NICO-SCAN-APPROVED",
                "raw_fingerprint": "b" * 64,
                "scanner": "gitleaks",
                "category": "secret",
                "rule_id": "count-only",
                "severity": "unknown",
                "confidence": "unknown",
                "source_path": "",
                "line": None,
                "evidence": "1 approved candidate retained by count.",
                "disposition": "approved_or_nonblocking",
                "evidence_quality": "count_only",
                "occurrence_count": 1,
                "exact_commit_sha": "3c4352ae1873c547dd01406da833d2faedb5039b",
                "human_review_required": False,
            },
        ],
        "totals": {
            "raw": 17,
            "material": 0,
            "review_required": 16,
            "approved_or_nonblocking": 1,
            "excluded_test_only": 0,
            "count_only": 17,
        },
        "count_parity_verified": True,
        "discrepancies": [],
    }


def test_every_raw_candidate_receives_one_stable_identity() -> None:
    expanded = expand_candidate_identities(_aggregate_register())
    records = expanded["findings"]

    assert len(records) == 17
    assert expanded["candidate_record_count"] == 17
    assert expanded["candidate_record_count_matches_raw"] is True
    assert expanded["every_raw_candidate_has_stable_identity"] is True
    assert expanded["candidate_identity_model"] == MODEL
    assert len({item["candidate_id"] for item in records}) == 17
    assert all(item["occurrence_count"] == 1 for item in records)
    assert sum(item["human_review_required"] is True for item in records) == 16
    assert sum(item["disposition"] == "approved_or_nonblocking" for item in records) == 1


def test_count_only_candidate_identity_is_deterministic() -> None:
    first = expand_candidate_identities(_aggregate_register())
    second = expand_candidate_identities(_aggregate_register())
    review_records = [
        item for item in first["findings"] if item["disposition"] == "review_required"
    ]

    assert first["findings"] == second["findings"]
    assert first["canonical_digest_sha256"] == second["canonical_digest_sha256"]
    assert len(review_records) == 16
    assert all(
        item["candidate_id"].startswith("NICO-CANDIDATE-")
        for item in review_records
    )
    assert sorted(item["aggregate_candidate_ordinal"] for item in review_records) == list(
        range(1, 17)
    )


def test_candidate_identity_population_mismatch_fails_closed() -> None:
    register = _aggregate_register()
    register["totals"]["raw"] = 18

    expanded = expand_candidate_identities(register)

    assert expanded["status"] == "blocked"
    assert expanded["count_parity_verified"] is False
    assert expanded["candidate_record_count_matches_raw"] is False
    assert expanded["discrepancies"][-1] == {
        "reason": "candidate_identity_population_mismatch",
        "raw_total": 18,
        "candidate_record_count": 17,
    }


def test_runtime_installs_candidate_identity_before_assurance_scoring() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    identity = source.index("install_comprehensive_candidate_identity_v1()")
    assurance = source.index("install_candidate_volume_assurance_v2()")
    assert identity < assurance
    assert 'RUNTIME_REVISION = "v71-digest-bound-auditable-candidates"' in source
    assert '"every_raw_candidate_has_stable_identity": True' in source
    assert '"count_only_candidates_are_individually_auditable": True' in source
