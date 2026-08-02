from __future__ import annotations

from pathlib import Path
from typing import Any

from nico.comprehensive_final_publication_truth_v58 import (
    install_comprehensive_final_publication_truth_v58,
    synchronize_final_publication_truth,
)


ROOT = Path(__file__).resolve().parents[1]
_COUNT_KEYS = {
    "unique_finding_count",
    "decision_finding_count",
    "finding_register_count",
    "canonical_finding_count",
}


def _finding(identifier: str, path: str, line: int, symbol: str) -> dict[str, Any]:
    return {
        "finding_id": identifier,
        "id": identifier,
        "category": "architecture",
        "priority": "P1",
        "status": "review_required",
        "path": path,
        "location": f"{path}:{line}",
        "line": line,
        "symbol": symbol,
        "finding_family": "complexity_hotspot",
        "rule_id": "complexity_hotspot",
        "title": f"Reduce complexity in {symbol}",
        "decision_title": f"Reduce complexity in {symbol}",
        "fact": "Retained exact-SHA complexity evidence exceeded the threshold.",
        "recommendation": "Split the function into bounded helpers.",
        "acceptance_criteria": ["Complexity is at or below the approved threshold."],
        "client_actionable": True,
        "exact_commit_match": True,
    }


def _count_values(value: Any) -> list[int]:
    values: list[int] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _COUNT_KEYS and isinstance(child, int) and not isinstance(child, bool):
                values.append(child)
            values.extend(_count_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_count_values(child))
    return values


def test_final_publication_reconciles_count_and_legacy_score_contract_before_render() -> None:
    findings = [
        _finding("NICO-FINDING-A", "nico/a.py", 10, "alpha"),
        _finding("NICO-FINDING-B", "nico/b.py", 20, "beta"),
    ]
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "c" * 40,
        },
        "assessment": {
            "technical_score": 92,
            "canonical_evidence_adjusted_score": 90,
            "score_reconciliation": {
                "technical_score": 92,
                "canonical_evidence_adjusted_score": 90,
            },
            "canonical_score_contract": {
                "technical_score": 92,
                "evidence_adjusted_score": 90,
            },
            "score_contract": {
                "technical_score": 92,
                "evidence_adjusted_score": 86,
                "assurance_penalty": 6,
                "score_override_allowed": False,
            },
            "finding_population": {
                "decision_finding_count": 2,
                "finding_register_count": 2,
                "canonical_finding_count": 2,
            },
        },
        "canonical_findings": findings,
        "findings_register": findings,
        "unique_finding_count": 1,
        "finding_register_count": 2,
        "canonical_finding_count": 2,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    synchronized = synchronize_final_publication_truth(canonical)
    score_contract = synchronized["assessment"]["score_contract"]

    assert len(synchronized["canonical_findings"]) == 2
    assert len(synchronized["findings_register"]) == 2
    assert set(_count_values(synchronized)) == {2}
    assert synchronized["unique_finding_count"] == 2
    assert score_contract["technical_score"] == 92
    assert score_contract["evidence_adjusted_score"] == 90
    assert score_contract["canonical_evidence_adjusted_score"] == 90
    assert score_contract["assurance_penalty"] == 2
    assert score_contract["pre_reconciliation_evidence_adjusted_score"] == 86
    assert score_contract["pre_reconciliation_assurance_penalty"] == 6
    assert score_contract["score_override_allowed"] is False
    assert synchronized["v2_prepublication_contract"][
        "final_register_count_synchronized_before_render"
    ] is True
    assert synchronized["v2_prepublication_contract"][
        "legacy_score_contract_reconciled_before_render"
    ] is True
    assert synchronized["human_review_required"] is True
    assert synchronized["client_delivery_allowed"] is False


def test_final_publication_installer_binds_the_real_register_boundary() -> None:
    from nico import client_report_completion_v2 as completion

    result = install_comprehensive_final_publication_truth_v58()

    assert result["status"] in {"installed", "already_installed"}
    assert result["bound"] is True
    assert getattr(
        completion._install_register,
        "_nico_comprehensive_final_publication_truth_v58",
        False,
    ) is True


def test_final_runtime_orders_source_anchor_then_publication_then_scoring() -> None:
    source = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")

    source_anchor = source.index("install_comprehensive_source_anchor_location_v57()")
    final_publication = source.index("install_comprehensive_final_publication_truth_v58()")
    scoring = source.index("install_comprehensive_scoring_manifest_v54()")

    assert source_anchor < final_publication < scoring
    assert '"final_register_count_synchronized_before_render": True' in source
    assert '"legacy_score_contract_reconciled_before_render": True' in source
