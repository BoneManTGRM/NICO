from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_finding_integrity_v1 import (
    attach_finding_integrity_manifest,
    build_finding_integrity_manifest,
    validate_finding_integrity_manifest,
)


FAILED_RELEASE_SHA = "0d3bd4778deb7a1514a93c61c36eee76e44b861e"
FAILED_UNIFIED_RUN = "31050722250"


def _code_finding(identifier: str, family: str) -> dict:
    return {
        "finding_id": identifier,
        "title": f"Exact-source finding for {family}",
        "priority": "P1",
        "finding_family": family,
        "path": "nico/shared_line.py",
        "line": 42,
        "location": "nico/shared_line.py:42",
        "observed_evidence": f"Retained evidence for {family} at the exact immutable source line.",
        "business_impact": "The independently identified condition can affect production behavior.",
        "recommended_correction": f"Correct {family} without changing unrelated behavior.",
        "exit_criteria": [
            f"The exact-SHA rerun no longer reports {family} at nico/shared_line.py:42."
        ],
        "disposition": "human_review_required",
    }


def _package(*findings: dict, operational: list[dict] | None = None) -> tuple[dict, dict]:
    operational = operational or []
    records = [*findings, *operational]
    register = {
        "code_findings": list(findings),
        "operational_findings": operational,
        "summary": {
            "decision_finding_count": len(records),
            "exact_source_code_finding_count": len(findings),
            "operational_or_context_finding_count": len(operational),
        },
    }
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": FAILED_RELEASE_SHA,
            "run_id": FAILED_UNIFIED_RUN,
        },
        "canonical_findings": deepcopy(records),
        "v2_pipeline_contract": {},
    }
    return canonical, register


def test_distinct_finding_families_may_share_one_exact_source_line() -> None:
    canonical, register = _package(
        _code_finding("NICO-FINDING-A", "complexity_hotspot"),
        _code_finding("NICO-FINDING-B", "unsafe_error_boundary"),
    )

    attached = attach_finding_integrity_manifest(canonical, register)
    manifest = attached["finding_integrity_manifest"]

    assert manifest["validation_status"] == "valid"
    assert manifest["decision_finding_count"] == 2
    assert manifest["duplicate_exact_source_identities"] == []
    assert {item["source_anchor"] for item in manifest["records"]} == {
        "nico/shared_line.py:42"
    }
    assert {item["finding_family"] for item in manifest["records"]} == {
        "complexity_hotspot",
        "unsafe_error_boundary",
    }
    assert validate_finding_integrity_manifest(attached)["status"] == "valid"


def test_same_family_and_source_line_still_fails_closed() -> None:
    first = _code_finding("NICO-FINDING-A", "complexity_hotspot")
    second = _code_finding("NICO-FINDING-B", "complexity_hotspot")
    canonical, register = _package(first, second)

    manifest = build_finding_integrity_manifest(canonical, register)

    assert manifest["validation_status"] == "invalid"
    assert (
        "duplicate_exact_source_identity:nico/shared_line.py:42|complexity_hotspot"
        in manifest["validation_errors"]
    )


def test_operational_context_does_not_require_fabricated_technical_priority() -> None:
    operational = {
        "finding_id": "NICO-OPERATIONAL-1",
        "title": "Deployment history requires review",
        "category": "ci_reliability",
        "evidence": "A bounded operational observation was retained.",
        "disposition": "human_review_required",
    }
    canonical, register = _package(operational=[operational])

    attached = attach_finding_integrity_manifest(canonical, register)
    manifest = attached["finding_integrity_manifest"]

    assert manifest["validation_status"] == "valid"
    assert manifest["priority_counts"] == {}
    assert manifest["operational_or_context_finding_count"] == 1
    assert manifest["records"][0]["priority"] == ""
    assert validate_finding_integrity_manifest(attached)["status"] == "valid"
