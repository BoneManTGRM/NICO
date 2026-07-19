from __future__ import annotations

from types import SimpleNamespace

from nico.express_decision_quality_v17 import (
    _canonical_ci_categories,
    _proportional_bar,
    _reconcile_ci_statement,
    normalize_express_decision_quality,
)


def test_proportional_bars_have_exact_zero_short_six_and_ordered_widths() -> None:
    zero = _proportional_bar(0)
    six = _proportional_bar(6)
    seventy_four = _proportional_bar(74)
    eighty_six = _proportional_bar(86)
    assert zero == "□" * 20
    assert six.count("■") == 1
    assert 0 < six.count("■") < seventy_four.count("■") < eighty_six.count("■") <= 20


def test_normalization_sets_geometry_and_scanner_supplemental_truth() -> None:
    result = {
        "maturity_signal": {"score": 90, "level": "Senior"},
        "score_contributions": [
            {"control": "Code Audit", "presented_score": 86, "bar": "■" * 10},
            {"control": "Scanner Worker Evidence", "presented_score": 6, "bar": "■" * 10},
            {"control": "Client / Human Acceptance", "presented_score": 0, "bar": "■" * 11},
        ],
        "sections": [],
    }
    output = normalize_express_decision_quality(result)
    code, scanner, human = output["score_contributions"]
    assert code["bar_geometry"]["width"] == 103.2
    assert scanner["bar_geometry"]["width"] == 0.0
    assert scanner["directly_scored"] is False
    assert scanner["mapped_to_scored_controls"] is True
    assert scanner["status"] == "SUPPLEMENTAL"
    assert human["bar_geometry"]["width"] == 0.0
    assert human["bar"].count("■") == 0


def test_ci_categories_are_each_rendered_once_and_reconcile_to_total() -> None:
    raw = (
        "GitHub Actions workflow runs returned in assessment window: "
        "100; success=86; failure=5; cancelled=2; skipped=1; neutral=1; timed_out=1; "
        "action_required=1; stale=0; startup_failure=0; other/unknown=3; other/unknown=3."
    )
    output = _reconcile_ci_statement(raw)
    for label in (
        "success",
        "failure",
        "cancelled",
        "skipped",
        "neutral",
        "timed_out",
        "action_required",
        "stale",
        "startup_failure",
        "unknown",
    ):
        assert output.count(f"{label}=") == 1
    pairs = {label: int(value) for label, value in __import__("re").findall(r"([a-z_]+)=(\d+)", output)}
    assert sum(pairs.values()) == 100


def test_ci_parser_does_not_rewrite_unrelated_score_text() -> None:
    raw = "Score trend: 100; success=86; failure=14"
    assert _reconcile_ci_statement(raw) == raw


def test_architecture_and_velocity_receive_separate_page_contract() -> None:
    result = {
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [
            {"id": "architecture_debt", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "evidence": [], "findings": [], "unavailable": []},
        ],
    }
    output = normalize_express_decision_quality(result)
    velocity = next(item for item in output["sections"] if item["id"] == "velocity_complexity")
    assert velocity["page_break_before"] is True
    assert velocity["pdf_page_break_before"] is True
    assert velocity["decision_record_boundary"] == "new_page"


def test_dossier_quality_removes_generic_boilerplate_and_root_only_evidence(monkeypatch) -> None:
    import nico.express_decision_quality_v17 as module

    dossier = SimpleNamespace(
        finding_id="FND-X",
        title="Complexity hotspot: nico/no_server_assessment.py score=360.2, loc=671, churn=795.",
        section_id="architecture_debt",
        severity="medium",
        confidence="review-limited",
        business_impact="Business impact requires reviewer confirmation.",
        repair_specification="Define the smallest reversible repair from the exact evidence.",
        owner="Unassigned",
        effort="medium",
        verification="Run tests.",
        rollback="Revert.",
        residual_risk="Pending.",
        disposition="open",
        evidence=("Repository root contains nico/.", "Repository root contains apps/."),
    )
    enriched = module._classify_dossier(dossier)
    assert "requires reviewer confirmation" not in enriched.business_impact
    assert "smallest reversible repair" not in enriched.repair_specification
    assert "nico/no_server_assessment.py" in enriched.business_impact
    assert all("repository root contains" not in value.casefold() for value in enriched.evidence)
    assert any("score=360.2" in value for value in enriched.evidence)


def test_scanner_section_is_supplemental_and_not_a_separate_red_score() -> None:
    result = {
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [
            {
                "id": "scanner_worker_evidence",
                "title": "Scanner Worker Evidence",
                "status": "RED",
                "presented_score": 6,
                "evidence": [],
                "findings": [],
                "unavailable": [],
            }
        ],
    }
    section = normalize_express_decision_quality(result)["sections"][0]
    assert section["status"] == "SUPPLEMENTAL"
    assert section["directly_scored"] is False
    assert section["mapped_to_scored_controls"] is True
    assert section["display_status"] == "SUPPLEMENTAL · MAPPED TO SCORED CONTROLS"


def test_canonical_ci_category_sum_invariant() -> None:
    categories = _canonical_ci_categories(
        100,
        [("success", 86), ("failure", 5), ("cancelled", 2), ("skipped", 1), ("neutral", 1), ("timed_out", 1)],
    )
    assert sum(categories.values()) == 100
