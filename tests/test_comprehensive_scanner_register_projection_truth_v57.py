from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from nico import comprehensive_scanner_register_projection_truth_v57 as projection


COMMIT = "a" * 40


def _digest(findings: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(findings, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _canonical_digest(canonical: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _record(*, evidence: str, fingerprint: str, count: int = 1) -> dict:
    return {
        "finding_id": f"NICO-SCAN-{fingerprint[:16].upper()}",
        "raw_fingerprint": fingerprint,
        "scanner": "semgrep",
        "category": "static",
        "rule_id": "typescript.review",
        "severity": "low",
        "confidence": "unknown",
        "source_path": "src/module.ts",
        "line": 10,
        "column": 1,
        "evidence": evidence,
        "disposition": "review_required",
        "evidence_quality": "exact_source",
        "occurrence_count": count,
        "source_record_count": count,
        "exact_commit_sha": COMMIT,
        "human_review_required": True,
    }


def _canonical() -> dict:
    source_record = _record(
        evidence="Original scanner message with repository evidence",
        fingerprint="1" * 64,
        count=657,
    )
    source_digest = _digest([source_record])
    rendered_record = deepcopy(source_record)
    rendered_record["evidence"] = "Client-safe redacted scanner evidence"
    return {
        "identity": {"commit_sha": COMMIT},
        "canonical_finding_count": 50,
        "assessment": {
            "canonical_finding_count": 50,
            "score_contract": {
                "canonical_finding_register_required": True,
            },
            "evidence_coverage": {
                "canonical_finding_count": 50,
                "canonical_finding_digest_sha256": source_digest,
                "canonical_finding_register_status": "complete",
            },
            "canonical_scanner_finding_register": {
                "artifact_schema": "nico.canonical-scanner-findings.v1",
                "status": "complete",
                "exact_commit_sha": COMMIT,
                "findings": [rendered_record],
                "totals": {
                    "raw": 657,
                    "material": 0,
                    "review_required": 657,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                    "exact_source": 657,
                    "source_path": 0,
                    "payload_without_source": 0,
                    "count_only": 0,
                },
                "count_parity_verified": True,
                "discrepancies": [],
                "canonical_digest_sha256": source_digest,
                "raw_payload_retention_complete": True,
            },
        },
    }


def test_normalizer_separates_scanner_candidates_from_decision_findings() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    assessment = normalized["assessment"]
    register = assessment["canonical_scanner_finding_register"]
    coverage = assessment["evidence_coverage"]

    assert normalized["canonical_finding_count"] == 50
    assert assessment["canonical_finding_count"] == 50
    assert coverage["canonical_finding_count"] == 50
    assert coverage["canonical_scanner_finding_count"] == 657
    assert coverage["decision_finding_count_is_separate"] is True
    assert register["source_canonical_digest_sha256"] == register["canonical_digest_sha256"]
    assert register["rendered_projection_digest_sha256"] == _digest(register["findings"])
    assert coverage["canonical_scanner_source_digest_sha256"] == register["canonical_digest_sha256"]
    assert coverage["canonical_scanner_rendered_digest_sha256"] == register["rendered_projection_digest_sha256"]
    assert register["findings"][0]["raw_fingerprint"] == "1" * 64
    assert register["projection_redaction_preserves_source_fingerprints"] is True


def test_projection_checks_verify_both_source_and_rendered_truth() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())

    checks = projection.scanner_register_projection_checks(normalized)

    assert checks == {
        "canonical_scanner_digest_recomputes": True,
        "canonical_scanner_coverage_reference_matches": True,
    }


def test_rendered_evidence_tamper_fails_rendered_digest_before_final_binding() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    normalized["assessment"]["canonical_scanner_finding_register"]["findings"][0][
        "evidence"
    ] = "Changed by a later client-safe redaction layer"

    checks = projection.scanner_register_projection_checks(normalized)

    assert checks["canonical_scanner_digest_recomputes"] is False
    assert checks["canonical_scanner_coverage_reference_matches"] is True


def test_scanner_count_reference_tamper_fails_coverage_truth() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    normalized["assessment"]["evidence_coverage"]["canonical_scanner_finding_count"] = 50

    checks = projection.scanner_register_projection_checks(normalized)

    assert checks["canonical_scanner_digest_recomputes"] is True
    assert checks["canonical_scanner_coverage_reference_matches"] is False


def test_final_binding_uses_exact_post_redaction_projection_and_refreshes_hash() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    source_register = normalized["assessment"]["canonical_scanner_finding_register"]
    source_digest = source_register["source_canonical_digest_sha256"]
    source_fingerprint = source_register["findings"][0]["raw_fingerprint"]
    normalized["assessment"]["canonical_scanner_finding_register"]["findings"][0][
        "evidence"
    ] = "Final client-safe redacted evidence"
    package = {"json": normalized, "canonical_truth_sha256": "stale"}

    bound = projection.bind_final_scanner_register_projection(package)
    register = bound["json"]["assessment"]["canonical_scanner_finding_register"]
    coverage = bound["json"]["assessment"]["evidence_coverage"]

    assert register["source_canonical_digest_sha256"] == source_digest
    assert register["canonical_digest_sha256"] == source_digest
    assert register["findings"][0]["raw_fingerprint"] == source_fingerprint
    assert register["rendered_projection_digest_sha256"] == _digest(register["findings"])
    assert coverage["canonical_scanner_rendered_digest_sha256"] == register[
        "rendered_projection_digest_sha256"
    ]
    assert bound["canonical_truth_sha256"] == _canonical_digest(bound["json"])
    assert package["json"] == bound["json"]
    assert package["canonical_truth_sha256"] == bound["canonical_truth_sha256"]
    assert projection.scanner_register_projection_checks(bound["json"]) == {
        "canonical_scanner_digest_recomputes": True,
        "canonical_scanner_coverage_reference_matches": True,
    }


def test_validator_binds_after_late_redaction_before_delegating() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    normalized["assessment"]["canonical_scanner_finding_register"]["findings"][0][
        "evidence"
    ] = "Late final-report redaction"
    package = {"json": normalized, "canonical_truth_sha256": "stale"}
    delegated: dict = {}

    def delegate(final_package: dict) -> dict:
        delegated.update(final_package)
        assert projection.scanner_register_projection_checks(final_package["json"]) == {
            "canonical_scanner_digest_recomputes": True,
            "canonical_scanner_coverage_reference_matches": True,
        }
        assert final_package["canonical_truth_sha256"] == _canonical_digest(
            final_package["json"]
        )
        return {
            "status": "blocked",
            "checks": {
                "canonical_scanner_digest_recomputes": False,
                "canonical_scanner_coverage_reference_matches": False,
                "canonical_scanner_totals_recompute": True,
                "canonical_scanner_count_parity_verified": True,
                "automated_package_remains_human_review_gated": True,
            },
            "failed_checks": [
                "canonical_scanner_digest_recomputes",
                "canonical_scanner_coverage_reference_matches",
            ],
        }

    result = projection.validate_scanner_register_projection(package, delegate)

    assert delegated
    assert result["status"] == "verified"
    assert result["failed_checks"] == []
    assert result["rendered_scanner_digest_bound_at_final_validation"] is True
    assert result["canonical_truth_sha256"] == package["canonical_truth_sha256"]
    assert result["checks"]["canonical_scanner_totals_recompute"] is True
    assert result["checks"]["canonical_scanner_count_parity_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_validator_replaces_only_obsolete_ambiguous_checks() -> None:
    normalized = projection.normalize_scanner_register_projection(_canonical())
    package = {"json": normalized}

    def delegate(_package: dict) -> dict:
        return {
            "status": "blocked",
            "checks": {
                "canonical_scanner_digest_recomputes": False,
                "canonical_scanner_coverage_reference_matches": False,
                "canonical_scanner_totals_recompute": True,
                "canonical_scanner_count_parity_verified": True,
                "automated_package_remains_human_review_gated": True,
            },
            "failed_checks": [
                "canonical_scanner_digest_recomputes",
                "canonical_scanner_coverage_reference_matches",
            ],
        }

    result = projection.validate_scanner_register_projection(package, delegate)

    assert result["status"] == "verified"
    assert result["failed_checks"] == []
    assert result["checks"]["canonical_scanner_totals_recompute"] is True
    assert result["checks"]["canonical_scanner_count_parity_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_missing_register_remains_non_applicable_for_legacy_package() -> None:
    assert projection.scanner_register_projection_checks({"assessment": {}}) == {
        "canonical_scanner_digest_recomputes": True,
        "canonical_scanner_coverage_reference_matches": True,
    }


def test_v54_compat_installs_v57_after_v56() -> None:
    source = Path("nico/comprehensive_final_artifact_truth_v54_compat.py").read_text(
        encoding="utf-8"
    )

    v55 = source.index("canonical_projection = install_comprehensive_canonical_projection_truth_v55()")
    v56 = source.index("scanner_completion = install_comprehensive_scanner_completion_projection_v56()")
    v57 = source.index("install_comprehensive_scanner_register_projection_truth_v57()")
    assert v55 < v56 < v57
    assert '"scanner_register_projection_truth": scanner_register_projection' in source
