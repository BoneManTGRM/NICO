from __future__ import annotations

import base64
import io

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_executive_summary_semantic_truth_v1 import (
    _validate_semantic_executive_summary,
)


REPOSITORY = "BoneManTGRM/NICO"
COMMIT = "c" * 40
GENERATED_AT = "2026-08-04T23:30:00Z"
SUMMARY = (
    "NICO completed a native Comprehensive Technical Assessment for "
    f"{REPOSITORY} at immutable commit {COMMIT}. The evidence-bound maturity "
    "signal is Senior (93/100). Seven client-review sections disclose bounded "
    "evidence limitations. This is an automated draft pending human approval."
)
CI_LINES = (
    "A. CI/CD configuration maturity: 100/100.",
    "B. Current operational readiness: exact deployment evidence required.",
    "C. Required-check health: exact commit checks retained.",
    "D. Historical workflow outcomes (unscored context): success=10, failure=1.",
)


def _surface_lines() -> list[str]:
    return [
        f"Repository: {REPOSITORY}",
        f"Exact commit: {COMMIT}",
        f"Generated: {GENERATED_AT}",
        "Technical maturity: 93/100",
        "Evidence-adjusted readiness: 89/100",
        "7 client-review section(s) remain limited",
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        "The automated evidence package is ready for authorized human review.",
        *CI_LINES,
    ]


def _pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        document.drawString(40, y, line)
        y -= 18
    document.showPage()
    document.save()
    return buffer.getvalue()


def _package(*, include_commit_in_html: bool = True) -> dict:
    lines = _surface_lines()
    html_lines = [
        line
        for line in lines
        if include_commit_in_html or COMMIT not in line
    ]
    canonical = {
        "identity": {
            "repository": REPOSITORY,
            "commit_sha": COMMIT,
            "generated_at": GENERATED_AT,
        },
        "generated_at": GENERATED_AT,
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 89,
            "limited_review_section_count": 7,
            "executive_summary": SUMMARY,
            "maturity_signal": {
                "level": "Senior",
                "technical_score": 93,
                "evidence_adjusted_score": 89,
            },
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "json": canonical,
        "markdown": "\n\n".join(lines),
        "html": "<html><body>" + "".join(f"<p>{line}</p>" for line in html_lines) + "</body></html>",
        "pdf_base64": base64.b64encode(_pdf(lines)).decode("ascii"),
    }


def test_format_specific_executive_prose_passes_when_canonical_facts_match() -> None:
    package = _package()

    assert SUMMARY not in package["markdown"]
    assert SUMMARY not in package["html"]
    _validate_semantic_executive_summary(package)


def test_missing_exact_commit_in_one_surface_still_fails_closed() -> None:
    with pytest.raises(ValueError, match="HTML omitted canonical repository or exact commit identity"):
        _validate_semantic_executive_summary(
            _package(include_commit_in_html=False)
        )


def test_missing_client_delivery_boundary_still_fails_closed() -> None:
    package = _package()
    package["markdown"] = package["markdown"].replace(
        "CLIENT DELIVERY BLOCKED",
        "DELIVERY STATE OMITTED",
    )
    package["html"] = package["html"].replace(
        "CLIENT DELIVERY BLOCKED",
        "DELIVERY STATE OMITTED",
    )
    pdf_lines = [
        line.replace("CLIENT DELIVERY BLOCKED", "DELIVERY STATE OMITTED")
        for line in _surface_lines()
    ]
    package["pdf_base64"] = base64.b64encode(_pdf(pdf_lines)).decode("ascii")

    with pytest.raises(ValueError, match="blocked client-delivery boundary"):
        _validate_semantic_executive_summary(package)


def test_missing_ci_boundary_still_fails_closed() -> None:
    package = _package()
    missing = CI_LINES[2]
    package["markdown"] = package["markdown"].replace(missing, "")
    package["html"] = package["html"].replace(f"<p>{missing}</p>", "")
    package["pdf_base64"] = base64.b64encode(
        _pdf([line for line in _surface_lines() if line != missing])
    ).decode("ascii")

    with pytest.raises(ValueError, match="client report omitted CI/CD boundary"):
        _validate_semantic_executive_summary(package)
