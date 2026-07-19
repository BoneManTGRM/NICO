from nico.express_decision_quality_v17 import (
    _canonical_ci_categories,
    _reconcile_ci_statement,
    _score_contribution_geometry,
    normalize_express_decision_quality,
)


def test_score_contribution_geometry_is_truly_proportional() -> None:
    zero = _score_contribution_geometry(0)
    one = _score_contribution_geometry(1)
    six = _score_contribution_geometry(6)

    assert zero["width"] == 0
    assert zero["ratio"] == 0
    assert one["width"] == 20
    assert one["width"] < six["width"] / 2
    assert six["width"] == 120
    assert six["ratio"] == 1


def test_score_contribution_normalization_removes_glyph_bars_and_adds_geometry() -> None:
    result = {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [],
        "score_contributions": [
            {"label": "No contribution", "contribution": 0, "bar": "██████"},
            {"label": "Small contribution", "contribution": 1, "glyph_bar": "█"},
            {"label": "Full contribution", "contribution": 6, "contribution_bar": "██████"},
        ],
    }

    normalized = normalize_express_decision_quality(result)
    items = normalized["score_contributions"]

    assert items[0]["bar_geometry"]["width"] == 0
    assert items[1]["bar_geometry"]["width"] == 20
    assert items[2]["bar_geometry"]["width"] == 120
    assert items[0]["bar"] is None
    assert items[1]["glyph_bar"] is None
    assert items[2]["contribution_bar"] is None
    assert all(item["bar_render_mode"] == "proportional_geometry" for item in items)


def test_ci_categories_are_canonicalized_exactly_once_and_reconcile_to_total() -> None:
    categories = _canonical_ci_categories(
        100,
        [
            ("success", 90),
            ("failure", 3),
            ("cancelled", 2),
            ("other/unknown", 5),
            ("other/unknown", 5),
        ],
    )

    assert categories == {
        "success": 90,
        "failure": 3,
        "cancelled": 2,
        "other/unknown": 5,
    }
    assert sum(categories.values()) == 100


def test_detailed_ci_categories_replace_non_success_aggregate() -> None:
    raw = (
        "GitHub Actions workflow runs returned in assessment window: "
        "100; success=90; non-success=5; failure=3; cancelled=2; other/unknown=5; other/unknown=5."
    )

    reconciled = _reconcile_ci_statement(raw)

    assert reconciled.count("success=") == 1
    assert reconciled.count("failure=") == 1
    assert reconciled.count("cancelled=") == 1
    assert reconciled.count("other/unknown=") == 1
    assert "non-success=" not in reconciled
    assert "100; success=90; failure=3; cancelled=2; other/unknown=5" in reconciled


def test_aggregate_non_success_is_retained_when_no_detailed_categories_exist() -> None:
    raw = "CI runs: 25; success=20; non-success=3; other/unknown=2; other/unknown=2."
    reconciled = _reconcile_ci_statement(raw)

    assert reconciled == "CI runs: 25; success=20; non-success=3; other/unknown=2."
    assert reconciled.count("other/unknown=") == 1
