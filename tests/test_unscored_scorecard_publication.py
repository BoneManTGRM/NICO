"""Exercise real PDF score cells and the active publication quality boundary."""
import base64
from copy import deepcopy
import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v5 as provider
from nico import scorecard_extraction_validation_v1 as validation
from nico import v2_report_quality_repairs as quality
from nico.v2_automated_draft_quality_compat_v3 import repair_rendered_report
from tests.test_comprehensive_native_providers_v2 import _context, _repo, _scan
from tests.test_v2_report_quality_runtime_compat import _package


def _text(pdf):
    return " ".join("\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).split())


@pytest.mark.parametrize("label", ["Architecture & Technical Debt", "Velocity / Complexity", "Static Analysis"])
def test_unscored_cell_retains_complete_words_without_status_masking(label):
    # Production statuses/summaries must not supply the missing score tokens.
    sections = [{"id": "control", "label": label, "presented_status": "REVIEW_LIMITED",
                 "presented_score": None, "summary": "Evidence is unavailable."}]
    canonical = {"assessment": {"sections": sections}}
    pdf = quality._scorecard_page(canonical)
    validation._verify_all_rows(pdf, canonical, sections)
    assert "NOT SCORED" in _text(pdf)


@pytest.mark.parametrize("value", [None, True, "78", -1, 101, float("nan"), float("inf"), 0, 78])
def test_architecture_and_dependent_velocity_pass_real_publication_repair(monkeypatch, value):
    context = _context()
    evidence = {**context, "snapshot_commit_sha": context["commit_sha"], "evidence_id": "complexity-test"}
    evidence.pop("prior_stage_results")
    if value is not None:
        evidence["complexity_score"] = value
    monkeypatch.setattr(legacy, "_repo", lambda _: _repo())
    monkeypatch.setattr(legacy, "_scan", lambda _: _scan())
    monkeypatch.setattr(legacy, "_complexity", lambda _: evidence)
    assessment = provider.canonical_scoring_provider(context)["assessment"]
    affected = {s["id"]: s for s in assessment["sections"] if s["id"] in ("architecture_debt", "velocity_complexity")}
    valid = type(value) is int and 0 <= value <= 100
    assert affected["architecture_debt"]["presented_score"] == (value if valid else None)
    assert (affected["velocity_complexity"]["presented_score"] is not None) == valid
    package = _package("Technical Scorecard and Weighting")
    package["json"]["assessment"] = assessment
    package["json"]["canonical_findings"] = [{"finding_id": "retained-finding", "title": "Retain evidence"}]
    package["json"]["provenance"] = {"source_sha": context["commit_sha"]}
    before = deepcopy(package)
    result = repair_rendered_report(package)
    assert package == before
    for key, original in assessment.items():
        assert result["json"]["assessment"][key] == original
    for key in ("canonical_findings", "provenance", "identity"):
        assert result["json"][key] == before["json"][key]
    assert result["approval_status"] == "pending_human_approval"
    assert result["client_delivery_allowed"] is False
    assert result["premium_report_renderer"]["scorecard_rows_verified"] is True
    text = _text(base64.b64decode(result["pdf_base64"]))
    assert ("0/100" if value == 0 and valid else "NOT SCORED" if not valid else "78/100") in text


@pytest.mark.parametrize("damage", ["missing_score", "fabricated_zero", "missing_row"])
def test_publication_validator_still_rejects_missing_or_fabricated_unscored_evidence(damage):
    canonical = {"assessment": {"sections": [{"id": "architecture_debt", "label": "Architecture & Technical Debt",
        "presented_status": "REVIEW_LIMITED", "presented_score": None, "summary": "Evidence unavailable."}]}}
    rendered = deepcopy(canonical)
    if damage == "missing_row":
        rendered["assessment"]["sections"][0]["label"] = "Other control"
    elif damage == "fabricated_zero":
        rendered["assessment"]["sections"][0]["presented_score"] = 0
    pdf = quality._scorecard_page(rendered)
    if damage == "missing_score":
        from reportlab.pdfgen import canvas

        output = io.BytesIO()
        page = canvas.Canvas(output, invariant=1)
        page.drawString(54, 740, "Canonical Technical Scorecard")
        page.drawString(54, 710, "Architecture & Technical Debt")
        page.save()
        pdf = output.getvalue()
    with pytest.raises(ValueError, match="scorecard omitted canonical"):
        validation._verify_all_rows(pdf, canonical, canonical["assessment"]["sections"])


def test_actual_publication_boundary_accepts_unscored_architecture_and_velocity(monkeypatch):
    from nico import v2_production_authority as authority
    from tests.test_v2_live_production_authority import _source, _context as report_context, _forbid_final_stage_scan

    source = _source()
    sections = [
        {"id": identifier, "label": label, "presented_score": None, "score": None,
         "score_status": "NOT_SCORED", "exclude_from_maturity": True,
         "presented_status": "REVIEW_LIMITED", "summary": "Evidence is unavailable."}
        for identifier, label in (("architecture_debt", "Architecture & Technical Debt"),
                                  ("velocity_complexity", "Velocity / Complexity"))
    ]
    source["report_package"]["json"]["assessment"]["sections"] = sections
    _forbid_final_stage_scan(monkeypatch)
    # Supply retained canonical input locally; exercise the real renderer,
    # publication wrapper, reinstallation and downstream validation unchanged.
    monkeypatch.setattr(authority, "_canonical_source", lambda context: (deepcopy(source), context, 0.0))
    result = authority.wrap_final_report_publication(lambda _: pytest.fail("unexpected legacy fallback"))(report_context("en"))
    assert result["status"] != "blocked", result.get("reason")
    package = result["report_package"]
    assert package["approval_status"] == "pending_human_approval"
    assert package["client_delivery_allowed"] is False
    for section in package["json"]["assessment"]["sections"]:
        assert section["presented_score"] is None
        assert section["score"] is None
    assert "NOT SCORED" in _text(base64.b64decode(package["pdf_base64"]))
    for surface in (package["markdown"], package["html"]):
        assert "NOT SCORED" in surface
    assert package["canonical_truth_sha256"]
    assert package["findings_csv_base64"]
