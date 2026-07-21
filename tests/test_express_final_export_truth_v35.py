from __future__ import annotations

from nico.express_final_export_truth_v35 import (
    normalize_final_express_exports,
    reconcile_final_express_scores,
)


def _section(section_id: str, score, *, status="green", findings=None, directly_scored=True) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "source_score": score,
        "presented_score": score,
        "status": status,
        "presented_status": status,
        "summary": "Exact-snapshot section.",
        "evidence": ["Exact-snapshot evidence retained."],
        "findings": findings or [],
        "unavailable": [],
        "directly_scored": directly_scored,
    }


def test_final_score_truth_replaces_stale_first_pass_baselines() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"level": "Senior", "score": 90, "source_score": 56},
        "sections": [
            _section("code_audit", 86),
            _section("dependency_health", 90, findings=["OSV candidate requires human triage."]),
        ],
    }
    result["sections"][0]["source_score"] = 49
    result["sections"][1]["source_score"] = 68

    reconcile_final_express_scores(result)

    code, dependency = result["sections"]
    assert code["source_score"] == 86
    assert code["presented_score"] == 86
    assert dependency["source_score"] == 90
    assert dependency["presented_score"] < 90
    assert result["maturity_signal"]["source_score"] == 90
    assert result["express_final_score_truth"]["stale_first_pass_source_scores_allowed"] is False


def test_none_numeric_scores_are_removed_from_final_markdown_and_html() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"level": "Senior", "score": 90},
        "sections": [
            _section("code_audit", 86),
            _section(
                "scanner_worker_evidence",
                None,
                status="supplemental",
                directly_scored=False,
            ),
            _section(
                "client_human_acceptance",
                None,
                status="gray",
                directly_scored=False,
            ),
        ],
        "reports": {
            "markdown": (
                "### Code Audit — GREEN (86/100)\nEvidence.\n\n"
                "### Scanner Worker Evidence — SUPPLEMENTAL (None/100)\nEvidence.\n\n"
                "### Client Human Acceptance — GRAY (None/100)\nPending.\n"
            ),
            "html": "<html><body>stale</body></html>",
        },
    }

    normalize_final_express_exports(result)

    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]
    assert "NONE/100" not in markdown.upper()
    assert "NULL/100" not in markdown.upper()
    assert "SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "GRAY (NOT SCORED)" in markdown
    assert "NONE/100" not in html.upper()
    assert result["sections"][1]["score"] is None
    assert result["sections"][1]["presented_score"] is None
    assert result["sections"][1]["score_label"] == "NOT SCORED"
    assert result["express_final_export_truth"]["status"] == "complete"


def test_global_null_score_guard_catches_unrecognized_legacy_token() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"score": 80},
        "sections": [_section("code_audit", 80)],
        "reports": {
            "markdown": "### Legacy supplemental control — GRAY (null/100)\nPending.",
            "html": "",
        },
    }

    normalize_final_express_exports(result)

    assert "NULL/100" not in result["reports"]["markdown"].upper()
    assert "NOT SCORED" in result["reports"]["markdown"]
    assert result["express_final_export_truth"]["not_scored_numeric_leakage"] is False
