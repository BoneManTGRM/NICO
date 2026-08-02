from __future__ import annotations

from pathlib import Path

from nico.comprehensive_canonical_projection_truth_v55 import (
    final_projection_checks,
    normalize_final_projection,
)
from nico.comprehensive_source_anchor_location_v57 import (
    install_comprehensive_source_anchor_location_v57,
    split_repository_source_location,
)


ROOT = Path(__file__).resolve().parents[1]


def _complexity_finding(
    finding_id: str,
    *,
    path: str,
    location: str,
    fact: str,
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "id": finding_id,
        "priority": "P1",
        "category": "architecture",
        "status": "review_required",
        "title": "Reduce complexity in install_comprehensive_on_production_app",
        "decision_title": "Reduce complexity in install_comprehensive_on_production_app",
        "path": path,
        "location": location,
        "line": 64,
        "end_line": 249,
        "symbol": "install_comprehensive_on_production_app",
        "rule_id": "complexity_hotspot",
        "finding_family": "complexity_hotspot",
        "fact": fact,
        "observed_evidence": fact,
        "interpretation": "Cyclomatic complexity exceeds the approved threshold.",
        "business_impact": "Concentrated branching increases regression risk.",
        "recommendation": "Split orchestration into bounded helpers.",
        "recommended_correction": "Split orchestration into bounded helpers.",
        "acceptance_criteria": ["Complexity is at or below the approved threshold."],
        "verification": ["Complexity is at or below the approved threshold."],
        "client_actionable": True,
        "exact_commit_match": True,
    }


def test_ranged_repository_locations_are_split_from_the_source_path() -> None:
    assert split_repository_source_location(
        "nico/api/comprehensive_production_bootstrap.py:64-249"
    ) == (
        "nico/api/comprehensive_production_bootstrap.py",
        64,
        249,
        None,
    )
    assert split_repository_source_location(
        "nico/api/comprehensive_production_bootstrap.py:64-249:64"
    ) == (
        "nico/api/comprehensive_production_bootstrap.py",
        64,
        249,
        64,
    )
    assert split_repository_source_location(
        "nico/api/comprehensive_production_bootstrap.py"
    ) == (
        "nico/api/comprehensive_production_bootstrap.py",
        None,
        None,
        None,
    )


def test_register_merges_summary_and_ranged_complexity_evidence() -> None:
    installation = install_comprehensive_source_anchor_location_v57()
    assert installation["status"] == "installed"
    assert installation["v3_parser_bound"] is True
    assert installation["v4_parser_bound"] is True
    assert installation["v5_parser_bound"] is True

    from nico import client_finding_remediation_register_v4 as v4
    from nico import client_finding_remediation_register_v5 as v5

    summary = _complexity_finding(
        "NICO-FINDING-SUMMARY",
        path="nico/api/comprehensive_production_bootstrap.py",
        location="nico/api/comprehensive_production_bootstrap.py:64",
        fact="cyclomatic_complexity=68; source=retained exact-SHA architecture evidence",
    )
    detail = _complexity_finding(
        "NICO-FINDING-DETAIL",
        path="nico/api/comprehensive_production_bootstrap.py:64-249",
        location="nico/api/comprehensive_production_bootstrap.py:64-249:64",
        fact="cyclomatic_complexity=68; loc=186; grade=F; method=python_ast",
    )
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "8" * 40,
        },
        "canonical_findings": [summary, detail],
        "findings_register": [summary, detail],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    register = {
        "code_findings": [summary, detail],
        "operational_findings": [],
        "excluded_non_production_findings": [],
        "summary": {
            "raw_observation_count": 2,
            "normalized_candidate_count": 2,
        },
    }

    normalized_v4 = v4.normalize_finding_remediation_register(register, canonical)
    assert len(normalized_v4["code_findings"]) == 1
    retained = normalized_v4["code_findings"][0]
    assert retained["path"] == "nico/api/comprehensive_production_bootstrap.py"
    assert retained["line"] == 64
    assert normalized_v4["summary"]["decision_finding_count"] == 1

    normalized_v5 = v5.normalize_finding_remediation_register(normalized_v4, canonical)
    synchronized = v5.synchronize_canonical_finding_surfaces(
        canonical,
        normalized_v5,
    )
    projected = normalize_final_projection(synchronized)
    checks = final_projection_checks(projected)

    assert len(projected["canonical_findings"]) == 1
    assert len(projected["findings_register"]) == 1
    assert projected["unique_finding_count"] == 1
    assert projected["canonical_finding_count"] == 1
    assert checks["finding_register_has_no_equivalent_duplicates"] is True
    assert checks["stated_unique_finding_count_matches_register"] is True
    assert projected["human_review_required"] is True
    assert projected["client_delivery_allowed"] is False


def test_final_runtime_binds_location_canonicalization_before_publication() -> None:
    source = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")
    install_index = source.index("install_comprehensive_source_anchor_location_v57()")
    scoring_index = source.index("install_comprehensive_scoring_manifest_v54()")

    assert install_index < scoring_index
    assert '"ranged_source_anchor_paths_canonicalized": True' in source
