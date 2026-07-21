from __future__ import annotations

from nico.express_evidence_specific_scoring_v33 import reconcile_express_scores
from nico.express_source_score_refresh_v34 import refresh_canonical_source_scores


def _section(section_id: str, score: int, *, findings=None, unavailable=None) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green",
        "summary": "Exact-snapshot section.",
        "evidence": ["Exact-snapshot artifact retained."],
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def test_refresh_replaces_stale_first_pass_section_and_maturity_scores() -> None:
    result = {
        "maturity_signal": {"level": "Mid", "score": 56},
        "sections": [
            _section("code_audit", 49),
            _section("dependency_health", 68, findings=["OSV candidate requires human triage."]),
        ],
    }

    reconcile_express_scores(result)
    assert result["sections"][0]["source_score"] == 49
    assert result["maturity_signal"]["source_score"] == 56

    result["sections"][0]["score"] = 86
    result["sections"][1]["score"] = 90
    result["maturity_signal"]["score"] = 88
    refresh_canonical_source_scores(result)
    reconcile_express_scores(result)

    code, dependency = result["sections"]
    assert code["source_score"] == 86
    assert code["presented_score"] == 86
    assert code["presented_status"] == "green"
    assert dependency["source_score"] == 90
    assert dependency["presented_score"] == 85
    assert dependency["presented_status"] == "yellow"
    assert result["maturity_signal"]["source_score"] == 88
    assert result["express_source_score_refresh"]["stale_first_pass_source_scores_allowed"] is False


def test_refresh_is_idempotent_and_does_not_replace_missing_canonical_score() -> None:
    result = {
        "maturity_signal": {"level": "Senior", "score": 90, "source_score": 40},
        "sections": [
            {"id": "code_audit", "score": 86, "source_score": 49},
            {"id": "scanner_worker_evidence", "score": None, "source_score": 12},
        ],
    }

    first = refresh_canonical_source_scores(result)
    second = refresh_canonical_source_scores(result)

    assert first is second is result
    assert result["sections"][0]["source_score"] == 86
    assert result["sections"][1]["source_score"] == 12
    assert result["maturity_signal"]["source_score"] == 90
