from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico import v2_dark_branded_cover as cover
from nico.comprehensive_final_two_report_truth_v1 import (
    assert_final_two_report_truth,
    install_final_two_report_truth_v1,
    repair_deployment_population,
)


RUN_ID = "comprun_567a6cd6189c4bf9b9f58832acb0b60a"
COMMIT = "05224082b2a0a5eb64ecb84cc2f892a4834abedb"
ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "comprehensive_human_review_package_cleanup_compat_v1.py"


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        document.drawString(40, y, line)
        y -= 18
    document.showPage()
    document.save()
    return buffer.getvalue()


def _canonical() -> dict:
    return {
        "report_language": "en",
        "generated_at": "2026-08-05T14:17:10Z",
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "run_id": RUN_ID,
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "canonical_evidence_adjusted_score": 89,
        },
        "canonical_findings": [],
    }


def test_incomplete_numeric_deployment_taxonomy_becomes_bounded_remainder() -> None:
    source = {
        "stage_id": "ci_cd_operational_readiness",
        "evidence": [
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployments: 2.",
        ],
    }

    cleaned = repair_deployment_population(source)

    assert "Non-success deployments: 2." not in cleaned["evidence"]
    assert (
        "Non-success or unresolved deployment observations: 3."
        in cleaned["evidence"]
    )
    assert "Outcome classification breakdown: Not available." in cleaned["evidence"]
    assert source["evidence"][-1] == "Non-success deployments: 2."


def test_complete_numeric_deployment_taxonomy_is_preserved() -> None:
    source = {
        "stage_id": "ci_cd_operational_readiness",
        "evidence": [
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployments: 3.",
        ],
    }

    assert repair_deployment_population(source)["evidence"] == source["evidence"]


def test_final_validator_rejects_the_exact_10_7_2_mismatch() -> None:
    text = "\n".join(
        (
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployments: 2.",
        )
    )

    with pytest.raises(ValueError, match="does not reconcile"):
        assert_final_two_report_truth({}, text, text, _pdf(text))


def test_final_validator_accepts_bounded_10_7_3_remainder() -> None:
    text = "\n".join(
        (
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success or unresolved deployment observations: 3.",
            "Outcome classification breakdown: Not available.",
        )
    )

    assert_final_two_report_truth({}, text, text, _pdf(*text.splitlines()))


def test_dark_cover_uses_separately_calculated_language_at_render_time() -> None:
    status = install_final_two_report_truth_v1()

    pdf = cover._cover(_canonical(), spanish=False)
    text = " ".join(
        "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
        ).casefold().split()
    )

    assert status["bounded_cover_copy_bound"] is True
    assert "separately calculated" in text
    assert "evidence-adjusted readiness" in text
    assert "independently evidence-adjusted readiness" not in text


def test_late_compat_binding_installs_final_two_truth_after_mobile_contract() -> None:
    source = COMPAT.read_text(encoding="utf-8")

    mobile = source.rindex("mobile_contract = install_comprehensive_review_companion_v7_mobile_contract()")
    final_two = source.rindex("final_two_truth = install_final_two_report_truth_v1()")
    assert mobile < final_two
    assert 'VERSION = "nico.comprehensive-human-review-package-cleanup-compat.v1.8"' in source
