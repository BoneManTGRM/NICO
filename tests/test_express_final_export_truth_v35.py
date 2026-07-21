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
    assert result["maturity_signal"]["presented_score"] < 90
    assert result["express_final_score_truth"]["stale_first_pass_source_scores_allowed"] is False


def test_none_numeric_scores_and_overall_score_are_normalized_in_final_exports() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"level": "Senior", "score": 90, "source_score": 90, "presented_score": 82},
        "evidence_adjusted_score": 82,
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
                "## Executive Summary\nSummary.\n\n"
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
    assert "Source maturity score: **90/100**" in markdown
    assert "Evidence-adjusted score: **82/100**" in markdown
    assert "82/100" in html
    assert "NONE/100" not in html.upper()
    assert result["sections"][1]["score"] is None
    assert result["sections"][1]["presented_score"] is None
    assert result["sections"][1]["score_label"] == "NOT SCORED"
    assert result["express_final_export_truth"]["status"] == "complete"
    assert result["express_final_export_truth"]["overall_score_parity"] is True


def test_global_null_score_guard_catches_unrecognized_legacy_token() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"score": 80, "source_score": 80, "presented_score": 80},
        "evidence_adjusted_score": 80,
        "sections": [_section("code_audit", 80)],
        "reports": {
            "markdown": "### Legacy supplemental control — GRAY (null/100)\nPending.",
            "html": "",
        },
    }

    normalize_final_express_exports(result)

    assert "NULL/100" not in result["reports"]["markdown"].upper()
    assert "NOT SCORED" in result["reports"]["markdown"]
    assert "Evidence-adjusted score: **80/100**" in result["reports"]["markdown"]
    assert result["express_final_export_truth"]["not_scored_numeric_leakage"] is False
    assert result["express_final_export_truth"]["overall_score_parity"] is True


def test_spanish_html_keeps_locale_and_includes_presented_overall_score() -> None:
    result = {
        "status": "complete",
        "report_language": "es-MX",
        "maturity_signal": {"score": 90, "source_score": 90, "presented_score": 82},
        "evidence_adjusted_score": 82,
        "sections": [_section("code_audit", 86)],
        "reports": {
            "markdown": "## Resumen ejecutivo\nResumen.\n\n### Code Audit — GREEN (86/100)\n",
            "html": '<!doctype html><html lang="es-MX"><body><p>Resumen.</p></body></html>',
        },
    }

    normalize_final_express_exports(result)

    assert 'lang="es-MX"' in result["reports"]["html"]
    assert "Puntaje ajustado por evidencia" in result["reports"]["markdown"]
    assert "82/100" in result["reports"]["markdown"]
    assert "82/100" in result["reports"]["html"]
    assert result["express_final_export_truth"]["localized_html_preserved"] is True
