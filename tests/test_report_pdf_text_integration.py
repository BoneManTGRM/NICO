import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from nico import report_pdf_text as cache
from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs
from nico.v2_single_pass_premium_report import _validate_review_pdf


def _review_pdf():
    output = io.BytesIO()
    canvas = Canvas(output, invariant=True)
    canvas.drawString(40, 700, "Human review and acceptance gate")
    canvas.drawString(40, 675, "run-one source-one")
    canvas.save()
    return output.getvalue()


def test_real_validators_reuse_text_but_recheck_changed_identity(monkeypatch):
    pdf = _review_pdf()
    reads = []

    def reader(stream):
        reads.append(stream.getvalue())
        return PdfReader(stream)

    monkeypatch.setattr(cache, "PdfReader", reader)
    with cache.pdf_text_cache_scope():
        _assert_no_control_glyphs(pdf)
        assert _validate_review_pdf(pdf, {"identity": {"run_id": "run-one", "commit_sha": "source-one"}}) == 1
        with pytest.raises(ValueError, match="omitted required identity text: run-two"):
            _validate_review_pdf(pdf, {"identity": {"run_id": "run-two", "commit_sha": "source-one"}})
        with pytest.raises(ValueError, match="omitted required identity text: source-two"):
            _validate_review_pdf(pdf, {"identity": {"run_id": "run-one", "commit_sha": "source-two"}})
    assert reads == [pdf]


def test_report_attempt_releases_text_after_preparation_failure(monkeypatch):
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17

    retained = []

    def prepare(package):
        attempt = cache._ATTEMPT_CACHE.get()
        assert attempt is not None
        cache.extract_pdf_page_texts(_review_pdf())
        assert attempt.entries
        retained.append(attempt)
        raise ValueError("preparation failed")

    monkeypatch.setattr(phase17, "_prepare_client_artifact_package", prepare)
    with pytest.raises(ValueError, match="preparation failed"):
        phase17.rebuild_client_artifacts({})
    assert cache._ATTEMPT_CACHE.get() is None
    assert not retained[0].entries
    assert retained[0].retained_bytes == 0
