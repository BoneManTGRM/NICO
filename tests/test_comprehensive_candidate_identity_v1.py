from __future__ import annotations

from pathlib import Path

from nico.comprehensive_candidate_identity_v1 import (
    MODEL,
    VERSION,
    expand_candidate_identities,
)
from nico.comprehensive_final_artifact_truth_v53 import (
    _canonical_scanner_register_truth,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
COMMIT = "3c4352ae1873c547dd01406da833d2faedb5039b"


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
                "exact_commit_sha": COMMIT,
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
                "exact_commit_sha": COMMIT,
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


def _detailed_duplicate_register() -> dict:
    summary = {
        "static": {
            "raw": 2,
            "material": 0,
            "review_required": 2,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
            "exact_source": 2,
            "source_path": 0,
            "payload_without_source": 0,
            "count_only": 0,
        }
    }
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "exact_commit_sha": COMMIT,
        "findings": [
            {
                "finding_id": "NICO-SCAN-DETAILED",
                "raw_fingerprint": "c" * 64,
                "scanner": "semgrep",
                "category": "static",
                "rule_id": "typescript.review",
                "severity": "medium",
                "confidence": "high",
                "source_path": "apps/web/app/page.tsx",
                "line": 44,
                "column": 3,
                "evidence": "Exact source payload retained for duplicate candidates.",
                "disposition": "review_required",
                "evidence_quality": "exact_source",
                "occurrence_count": 2,
                "source_record_count": 2,
                "exact_commit_sha": COMMIT,
                "human_review_required": True,
            }
        ],
        "summary_by_category": summary,
        "totals": dict(summary["static"]),
        "count_parity_verified": True,
        "discrepancies": [],
        "raw_payload_retention_complete": True,
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
    assert expanded["raw_payload_retention_complete"] is False
    assert expanded["candidate_evidence_quality_totals_match_source"] is True


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
    assert all(item["evidence_quality"] == "count_only" for item in review_records)
    assert all(
        item["raw_payload_retention_state"] == "count_only"
        for item in review_records
    )


def test_detailed_duplicate_expansion_preserves_source_evidence_quality() -> None:
    source = _detailed_duplicate_register()
    expanded = expand_candidate_identities(source)
    records = expanded["findings"]

    assert VERSION == "nico.comprehensive-candidate-identity.v1.2"
    assert len(records) == 2
    assert len({item["candidate_id"] for item in records}) == 2
    assert all(item["occurrence_count"] == 1 for item in records)
    assert all(item["evidence_quality"] == "exact_source" for item in records)
    assert all(item["raw_payload_retention_state"] == "retained" for item in records)
    assert all(
        item["evidence"]
        == "Exact source payload retained for duplicate candidates."
        for item in records
    )
    assert all("raw candidate payload was unavailable" not in item["evidence"] for item in records)
    assert expanded["totals"] == source["totals"]
    assert expanded["candidate_evidence_quality_totals_recomputed"] == source["totals"]
    assert expanded["candidate_evidence_quality_totals_match_source"] is True
    assert expanded["source_evidence_quality_preserved"] is True
    assert expanded["raw_payload_retention_complete"] is True
    assert expanded["status"] == "complete"
    assert expanded["count_parity_verified"] is True


def test_detailed_duplicate_expansion_passes_strict_cross_format_truth() -> None:
    register = expand_candidate_identities(_detailed_duplicate_register())
    canonical = {
        "identity": {"commit_sha": COMMIT},
        "assessment": {
            "score_contract": {
                "canonical_finding_register_required": True,
                "canonical_finding_count_parity_verified": True,
                "candidate_volume_affects_technical_score": False,
                "candidate_volume_affects_evidence_adjusted_score": True,
            },
            "canonical_scanner_finding_register": register,
            "scanner_finding_summary": register["summary_by_category"],
            "evidence_coverage": {
                "canonical_finding_count": 2,
                "canonical_finding_digest_sha256": register[
                    "canonical_digest_sha256"
                ],
                "canonical_finding_register_status": "complete",
                "candidate_volume_affects_technical_score": False,
                "candidate_volume_affects_evidence_adjusted_score": True,
            },
        },
    }

    checks = _canonical_scanner_register_truth(canonical)

    assert checks["canonical_scanner_totals_recompute"] is True
    assert checks["canonical_scanner_payload_retention_truthful"] is True
    assert checks["canonical_scanner_digest_recomputes"] is True
    assert checks["canonical_scanner_commit_matches_report"] is True
    assert checks["canonical_scanner_ids_are_unique"] is True


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


def test_evidence_quality_total_mismatch_fails_closed() -> None:
    register = _detailed_duplicate_register()
    register["totals"]["exact_source"] = 1

    expanded = expand_candidate_identities(register)

    assert expanded["status"] == "blocked"
    assert expanded["count_parity_verified"] is False
    assert expanded["candidate_evidence_quality_totals_match_source"] is False
    assert expanded["discrepancies"][-1]["reason"] == (
        "candidate_identity_evidence_quality_totals_mismatch"
    )
    assert expanded["discrepancies"][-1]["recomputed_totals"]["exact_source"] == 2


def test_runtime_installs_candidate_identity_before_assurance_scoring() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    identity = source.index("install_comprehensive_candidate_identity_v1()")
    assurance = source.index("install_candidate_volume_assurance_v2()")
    assert identity < assurance
    assert 'RUNTIME_REVISION = "v72-exact-digest-approved-delivery"' in source
    assert '"every_raw_candidate_has_stable_identity": True' in source
    assert '"count_only_candidates_are_individually_auditable": True' in source
