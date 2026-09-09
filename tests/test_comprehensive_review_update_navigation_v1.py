from __future__ import annotations

import base64
import io
import re
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico.comprehensive_four_phase_model_v1 import apply_four_phase_program
from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
from nico.comprehensive_pdf_layout_polish_v1 import install_comprehensive_pdf_layout_polish_v1
from nico.comprehensive_review_report_truth_v1 import _synchronize_package, build_review_truth, synchronize_review_truth
from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline
from tests.test_comprehensive_four_phase_report_v1 import _canonical
from tests.test_comprehensive_pdf_layout_polish_v1 import _semantic_fixture
from tests.test_phase2_full_coverage_v2 import _complete_review, _record


def _package(spanish: bool) -> dict:
    from nico.comprehensive_four_phase_model_v1 import four_phase_markdown

    install_comprehensive_pdf_layout_polish_v1()
    canonical = apply_four_phase_program(_canonical(language="es-MX" if spanish else "en"))
    pdf = apply_four_phase_pdf(semantic_renumber_and_outline(_semantic_fixture(spanish=spanish)), canonical)
    return {
        "json": canonical,
        "four_phase_program": deepcopy(canonical["four_phase_program"]),
        "markdown": "# NICO Comprehensive\n\n" + four_phase_markdown(canonical) + "\n## Evidence\nUnchanged source evidence.\n",
        "html": "<html><body>READY FOR REVIEW - HUMAN DISPOSITIONS PENDING</body></html>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_page_count": len(PdfReader(io.BytesIO(pdf)).pages),
    }


@pytest.mark.parametrize("spanish", [False, True])
def test_review_update_refreshes_phase_summary_and_all_physical_pages(spanish: bool) -> None:
    package = _package(spanish)
    original_count = package["pdf_page_count"]
    truth = build_review_truth(_complete_review(_record()))
    for _ in range(2):
        _synchronize_package(package, truth)
        canonical = package["json"]
        assert canonical["four_phase_program"]["phases"][1]["status"] == "complete"
        assert package["four_phase_program"] == canonical["four_phase_program"]
        assert canonical["four_phase_program"]["human_approval_completed"] is False
        assert canonical["four_phase_program"]["client_delivery_allowed"] is False
        pending = "DISPOSICIONES HUMANAS PENDIENTES" if spanish else "HUMAN DISPOSITIONS PENDING"
        assert pending not in package["markdown"]
        assert pending not in package["html"]
        assert package["markdown"].count("<!-- NICO_PHASE2_REVIEW_TRUTH_START -->") == 1
        assert package["html"].count("<!-- NICO_PHASE2_REVIEW_TRUTH_START -->") == 1
        reader = PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"])))
        assert len(reader.pages) == original_count + 1 == package["pdf_page_count"]
        texts = [page.extract_text() or "" for page in reader.pages]
        assert pending not in "\n".join(texts)
        assert sum(text.count("Human Review and Approval Truth") for text in texts) == 1
        for index, text in enumerate(texts, 1):
            expected = f"Página del documento {index} de {len(texts)}" if spanish else f"Document page {index} of {len(texts)}"
            labels = re.findall(r"(?:Document page \d+ of \d+|Página del documento \d+ de \d+)", text)
            assert labels == [expected]


def test_accepted_review_report_remains_immutable() -> None:
    record = _complete_review(_record())
    record["accepted_edition"] = {"accepted_edition": True}
    assert synchronize_review_truth(record) == record


@pytest.mark.parametrize("spanish", [False, True])
def test_review_update_rebinds_real_manifest_after_all_presentation_changes(spanish: bool) -> None:
    import hashlib

    from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_comprehensive_artifact_manifest_approval_v1 import _package as manifest_package

    package = manifest_package()
    package["json"]["identity"]["report_language"] = "es-MX" if spanish else "en"
    package["json"]["report_language"] = "es-MX" if spanish else "en"
    package["json"] = apply_four_phase_program(package["json"])
    package["pdf_base64"] = base64.b64encode(_semantic_fixture(spanish=spanish)).decode("ascii")
    package = attach_artifact_manifest(package)
    old_pdf_sha = package["pdf_sha256"]
    truth = build_review_truth(_complete_review(_record()))
    for _ in range(2):
        _synchronize_package(package, truth)
        _validate_exact_artifact_hashes(package)
        pdf = base64.b64decode(package["pdf_base64"])
        assert hashlib.sha256(pdf).hexdigest() == package["pdf_sha256"] != old_pdf_sha
        reader = PdfReader(io.BytesIO(pdf))
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            expected = f"Página del documento {index} de {len(reader.pages)}" if spanish else f"Document page {index} of {len(reader.pages)}"
            assert re.findall(r"(?:Document page \d+ of \d+|Página del documento \d+ de \d+)", text) == [expected]
        assert package["draft_artifact_identity"]["pdf_sha256"] == package["pdf_sha256"]
        assert package["human_review_status"] == "pending"
        assert package["client_delivery_allowed"] is False
