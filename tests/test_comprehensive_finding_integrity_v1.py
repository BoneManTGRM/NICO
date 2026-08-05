from __future__ import annotations

from copy import deepcopy

import pytest

from nico.comprehensive_finding_integrity_v1 import (
    EXECUTIVE_DETAIL_LIMIT,
    MANIFEST_KEY,
    attach_finding_integrity_manifest,
    build_finding_integrity_manifest,
    validate_finding_integrity_manifest,
)


def _finding(index: int, *, priority: str | None = None) -> dict:
    complexity = 60 - (index % 20)
    return {
        "finding_id": f"NICO-FINDING-{index:04d}",
        "title": f"Reduce complexity in function_{index}",
        "priority": priority or ("P1" if index < 17 else "P2"),
        "path": f"nico/module_{index}.py",
        "line": 10 + index,
        "location": f"nico/module_{index}.py:{10 + index}",
        "evidence": f"cyclomatic_complexity={complexity}; method=python_ast",
        "impact": "Concentrated branch logic increases regression risk.",
        "recommendation": f"Decompose function_{index} and preserve behavior.",
        "verification": [
            f"Exact-SHA rerun no longer reports complexity above 30 at nico/module_{index}.py:{10 + index}.",
            "Targeted characterization tests pass.",
        ],
        "cyclomatic_complexity": complexity,
        "disposition": "human_review_required",
    }


def _register() -> dict:
    findings = [_finding(index) for index in range(50)]
    return {
        "code_findings": findings,
        "operational_findings": [],
        "summary": {
            "decision_finding_count": 50,
            "exact_source_code_finding_count": 50,
            "operational_or_context_finding_count": 0,
        },
    }


def _canonical(register: dict | None = None) -> dict:
    register = register or _register()
    return {
        "canonical_findings": deepcopy(register["code_findings"]),
        "v2_pipeline_contract": {},
    }


def test_reference_population_retains_all_50_findings_and_17_p1() -> None:
    register = _register()
    manifest = build_finding_integrity_manifest(_canonical(register), register)

    assert manifest["validation_status"] == "valid"
    assert manifest["decision_finding_count"] == 50
    assert manifest["exact_source_code_finding_count"] == 50
    assert manifest["priority_counts"] == {"P1": 17, "P2": 33}
    assert manifest["executive_detail_policy"] == {
        "expanded_detail_limit": EXECUTIVE_DETAIL_LIMIT,
        "all_findings_remain_in_exact_source_index": True,
        "bounded_expansion_does_not_change_priority": True,
    }
    assert EXECUTIVE_DETAIL_LIMIT == 7


def test_bounded_executive_detail_does_not_lower_or_omit_priority_findings() -> None:
    register = _register()
    attached = attach_finding_integrity_manifest(_canonical(register), register)

    records = attached[MANIFEST_KEY]["records"]
    assert len(records) == 50
    assert sum(item["priority"] == "P1" for item in records) == 17
    assert validate_finding_integrity_manifest(attached)["status"] == "valid"


def test_missing_exact_source_field_fails_with_finding_specific_diagnostic() -> None:
    register = _register()
    register["code_findings"][3].pop("line")
    register["code_findings"][3]["location"] = "nico/module_3.py"
    canonical = _canonical(register)

    manifest = build_finding_integrity_manifest(canonical, register)

    assert manifest["validation_status"] == "invalid"
    assert "NICO-FINDING-0003.source.line:required_positive_integer" in manifest[
        "validation_errors"
    ]
    with pytest.raises(ValueError, match="finding_integrity_invalid"):
        attach_finding_integrity_manifest(canonical, register)


def test_duplicate_id_and_source_anchor_fail_closed() -> None:
    register = _register()
    register["code_findings"][1]["finding_id"] = register["code_findings"][0][
        "finding_id"
    ]
    register["code_findings"][2]["path"] = register["code_findings"][0]["path"]
    register["code_findings"][2]["line"] = register["code_findings"][0]["line"]
    register["code_findings"][2]["location"] = register["code_findings"][0][
        "location"
    ]

    manifest = build_finding_integrity_manifest(_canonical(register), register)

    assert manifest["validation_status"] == "invalid"
    assert "duplicate_finding_id:NICO-FINDING-0000" in manifest[
        "validation_errors"
    ]
    assert "duplicate_exact_source_anchor:nico/module_0.py:10" in manifest[
        "validation_errors"
    ]


def test_canonical_surface_id_and_location_mismatch_fail_closed() -> None:
    register = _register()
    canonical = _canonical(register)
    canonical["canonical_findings"][0]["location"] = "nico/other.py:999"
    canonical["canonical_findings"][1]["finding_id"] = "NICO-FINDING-EXTRA"

    manifest = build_finding_integrity_manifest(canonical, register)

    assert manifest["validation_status"] == "invalid"
    assert any(
        error.startswith("canonical_surface_finding_ids:mismatch")
        for error in manifest["validation_errors"]
    )
    assert any(
        error.startswith("NICO-FINDING-0000.canonical_surface_location:mismatch")
        for error in manifest["validation_errors"]
    )


def test_manifest_digest_detects_record_mutation() -> None:
    register = _register()
    attached = attach_finding_integrity_manifest(_canonical(register), register)
    attached[MANIFEST_KEY]["records"][0]["impact"] = "changed after validation"

    validation = validate_finding_integrity_manifest(attached)

    assert validation["status"] == "invalid"
    assert "NICO-FINDING-0000.record_sha256:mismatch" in validation[
        "validation_errors"
    ]


def test_summary_population_mismatch_fails_closed() -> None:
    register = _register()
    register["summary"]["decision_finding_count"] = 49

    manifest = build_finding_integrity_manifest(_canonical(register), register)

    assert manifest["validation_status"] == "invalid"
    assert "decision_finding_count:mismatch;summary=49;records=50" in manifest[
        "validation_errors"
    ]
