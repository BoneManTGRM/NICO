from __future__ import annotations

import pytest

from nico.phase1_completion_report_contract_v1 import extract_report


EXPECTED_SHA = "a" * 40


def _report_text(score_evidence: str) -> str:
    return f"""
    NICO Comprehensive
    Exact commit: {EXPECTED_SHA}
    Technical triage remains proposal-only.
    Only an authorized reviewer may change the status to APPROVED FINAL.
    Client delivery remains blocked.
    {score_evidence}
    Current-evidence candidates requiring new technical triage: 2
    fresh automated triage completed=2
    Technical triage coverage: 3/3
    Exact carry-forward: 1
    not_actionable=1
    needs_review=2
    confirmed=0
    Individual human attention: 2
    grouped-review eligible candidates: 1
    grouped human-review clusters: 1
    quality-control pool: 1
    Human review work units: 3
    """


def test_extract_report_accepts_legacy_score_separation_phrase() -> None:
    report = extract_report(
        _report_text("No numeric technical-maturity or Evidence-Adjusted score effect."),
        EXPECTED_SHA,
    )

    assert report["fresh_completed"] == 2
    assert report["work_units"] == 3


def test_extract_report_accepts_current_structured_score_truth() -> None:
    report = extract_report(
        _report_text("`score_effect`: none; `technical_score_effect`: none"),
        EXPECTED_SHA,
    )

    assert report["coverage_done"] == report["coverage_total"] == 3


@pytest.mark.parametrize(
    "score_evidence",
    [
        "",
        "Score effect: assurance-only while authorized human disposition remains pending.",
    ],
)
def test_extract_report_rejects_missing_numeric_score_separation(score_evidence: str) -> None:
    with pytest.raises(ValueError, match="missing no score gaming"):
        extract_report(_report_text(score_evidence), EXPECTED_SHA)


@pytest.mark.parametrize(
    "score_evidence",
    [
        "`score_effect`: penalty",
        "`technical_score_effect`: candidate_volume_penalty",
        "`score_effect`: none; `technical_score_effect`: workload_penalty",
    ],
)
def test_extract_report_rejects_non_none_or_conflicting_score_effects(score_evidence: str) -> None:
    with pytest.raises(ValueError, match="non-none score-effect evidence"):
        extract_report(_report_text(score_evidence), EXPECTED_SHA)


@pytest.mark.parametrize("score_evidence", [
    "Score effect: None; Technical score effect: None",
    "Score effect: assurance-only while authorized human disposition remains pending. "
    "Score effect: None; Technical score effect: None",
    "Score effect:\nNone; Technical\nscore effect: None",
])
def test_extract_report_accepts_pdf_display_labels(score_evidence):
    assert extract_report(_report_text(score_evidence), EXPECTED_SHA)["work_units"] == 3


@pytest.mark.parametrize("score_evidence", [
    "Score effect: None; Technical score effect: penalty",
    "score_effect: none; Score effect: workload_penalty",
    "No numeric technical-maturity or Evidence-Adjusted score effect. Technical score effect: penalty",
    "Technical score effect: assurance-only",
])
def test_display_conflicts_fail_even_with_other_positive_evidence(score_evidence):
    with pytest.raises(ValueError, match="non-none score-effect evidence"):
        extract_report(_report_text(score_evidence), EXPECTED_SHA)


def test_rendered_triage_labels_preserve_counts():
    text = _report_text("Score effect: None; Technical score effect: None")
    text = text.replace("not_actionable=", "not actionable=").replace("needs_review=", "needs review=")
    report = extract_report(text, EXPECTED_SHA)
    assert (report["not_actionable"], report["needs_review"], report["confirmed"]) == (1, 2, 0)
