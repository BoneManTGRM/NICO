from __future__ import annotations

import io

from pypdf import PdfReader

from nico import express_pdf_score_assurance_v1 as pdf_score
from nico.express_report_final_polish_v41 import (
    _compact_decision_pdf,
    _normalize_repairs,
    _reconcile_static_assurance,
)


def _sample_result() -> dict:
    return {
        "status": "complete",
        "maturity_signal": {"level": "Strong", "score": 87, "presented_score": 85},
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": None,
                "presented_score": None,
                "directly_scored": False,
                "status": "gray",
                "presented_status": "gray",
                "assurance_status": "pending_human_review",
                "assurance_label": "HUMAN REVIEW PENDING",
                "summary": "Static candidates require review.",
                "evidence": [
                    "Exact-snapshot semgrep status=completed; findings=108; commit=abc.",
                    "Exact-snapshot typescript status=completed; findings=1; commit=abc.",
                    "Scanner-worker static artifacts were observed for: bandit, eslint, typescript. Execution acceptance is determined per analyzer.",
                    "Bandit triage artifact attached: blocking=0, needs_review=45, approved=0, candidate_false_positive=161.",
                ],
                "findings": [
                    "bandit ended with status failed; its output requires human review before client-facing conclusions.",
                    "Semgrep and TypeScript produced 109 unverified candidate(s).",
                ],
                "unavailable": [
                    "Accepted current-run execution evidence remains unresolved for: bandit, eslint.",
                    "eslint was unavailable in the exact-snapshot scanner: No ESLint configuration exists and the package lint script does not execute ESLint.",
                    "Live Bandit execution failed for this exact snapshot.",
                ],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 73,
                "presented_score": 73,
                "status": "yellow",
                "summary": "Work-vs-expected signal uses velocity and repository evidence.",
                "evidence": [
                    "Commit velocity: 100 commits over 180 days.",
                    "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                    "Source-file footprint from recursive tree: 1165 files.",
                    "Estimated call graph edges: 21746; max file cyclomatic complexity: 246.",
                    "Project trend unavailable: no prior completed Express runs were found.",
                    "Client acceptance evidence unavailable.",
                ],
                "findings": [],
                "unavailable": [
                    "Precise story-point expectation requires stakeholder context.",
                    "Release-readiness lift not applied because final-clean evidence is incomplete.",
                ],
            },
        ],
    }


def test_static_not_scored_uses_review_limited_assurance_and_eslint_is_inapplicable() -> None:
    result = _reconcile_static_assurance(_sample_result())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert static["assurance_label"] == "REVIEW LIMITED"
    assert static["assurance_status"] == "review_limited"
    assert static["status"] == "yellow"
    assert "eslint" not in " ".join(static["unavailable"]).casefold()
    assert any("ESLint is not applicable" in item for item in static["evidence"])
    assert static["score"] is None


def test_repair_priorities_are_client_facing_and_sequential() -> None:
    repairs = _normalize_repairs([
        {"rank": 20, "title": "First", "severity": "REVIEW"},
        {"rank": 23, "title": "Second", "severity": "medium"},
        {"rank": "P5", "title": "Third", "severity": "review required"},
    ])

    assert [item["rank"] for item in repairs] == ["P1", "P2", "P3"]
    assert repairs[0]["source_rank"] == 20
    assert repairs[0]["severity"] == "review required"


def test_velocity_decision_record_remains_one_page() -> None:
    result = _reconcile_static_assurance(_sample_result())
    setattr(_compact_decision_pdf, "_nico_original", pdf_score._decision_pdf)

    payload = _compact_decision_pdf(
        result,
        "velocity_complexity",
        "Velocity, Complexity, and Ownership Decision Record",
    )

    assert payload.startswith(b"%PDF")
    assert len(PdfReader(io.BytesIO(payload)).pages) == 1
