from __future__ import annotations

import inspect

import nico.phase17_canonical_artifact_rebuild_v1 as phase17
from nico.v2_single_pass_premium_report import VERSION, _validate_review_pdf


def test_phase17_uses_only_single_pass_premium_compiler() -> None:
    source = inspect.getsource(phase17.rebuild_client_artifacts)
    assert "rebuild_single_pass_premium_artifacts" in source
    assert "apply_executive_score_dashboard" not in source
    assert "apply_dark_branded_cover" not in source
    assert "rebuild_authoritative_premium_artifacts" not in source


def test_single_pass_contract_version_is_explicit() -> None:
    assert VERSION == "nico.v2.single-pass-premium-report.v2"


def test_review_pdf_validation_rejects_non_pdf_bytes() -> None:
    try:
        _validate_review_pdf(b"not-a-pdf", {})
    except ValueError as exc:
        assert "valid PDF" in str(exc)
    else:
        raise AssertionError("invalid review-package bytes must fail closed")
