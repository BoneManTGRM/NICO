"""Synthetic worker-to-API font regressions; never create live authorization."""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico.comprehensive_four_phase_pdf_v1 import four_phase_target_page_index
from nico.comprehensive_operator_approval_v1 import _artifact_digests


def _fresh_python(code: str, *args: str, input_text: str | None = None):
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        input=input_text, text=True, capture_output=True, timeout=30, check=False,
    )


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_worker_embedded_phase_stays_portable_in_fresh_api_process(language):
    worker = _fresh_python(
        "import json,sys; "
        "from nico.comprehensive_pdf_embedded_fonts_v1 import "
        "install_comprehensive_pdf_embedded_fonts_v1; "
        "install_comprehensive_pdf_embedded_fonts_v1(); "
        "from tests.test_authorized_phase_presentation import edition; "
        "print(json.dumps(edition(sys.argv[1])))",
        language,
    )
    assert worker.returncode == 0, worker.stderr
    original = json.loads(worker.stdout)
    frozen = deepcopy(original)
    # The API process has never imported the isolated final-report bootstrap.
    api = _fresh_python(
        "import json,sys; from copy import deepcopy; "
        "from reportlab.pdfbase import pdfmetrics; "
        "from nico.comprehensive_operator_delivery_v1 import "
        "render_delivery_companion_presentation as present; "
        "before=pdfmetrics.getFont('Helvetica'); "
        "source=json.load(sys.stdin); frozen=deepcopy(source); result=present(source); "
        "assert source==frozen; "
        "assert pdfmetrics.getFont('Helvetica') is before; "
        "assert present(result)==result; "
        "assert present(source)==result; "
        "print(json.dumps(result))",
        input_text=worker.stdout,
    )
    assert api.returncode == 0, api.stderr
    result = json.loads(api.stdout)
    assert original == frozen
    for key in ("review", "delivery_authorization"):
        assert result[key] == original[key]
    for key in ("json", "markdown", "html"):
        assert result["reports"][key] == original["reports"][key]
    assert result["artifact_digests"] == _artifact_digests(result["reports"])
    assert result["rendering_derivation"]["new_human_approval"] is False
    assert result["rendering_derivation"]["authoritative_delivery_manifest_sha256"] == original["accepted_edition_manifest_sha256"]

    before = PdfReader(io.BytesIO(base64.b64decode(original["reports"]["pdf_base64"])))
    after = PdfReader(io.BytesIO(base64.b64decode(result["reports"]["pdf_base64"])))
    target = four_phase_target_page_index(after, spanish=language == "es-MX")
    assert len(after.pages) == len(before.pages)
    for index, page in enumerate(after.pages):
        if index != target:
            assert page.extract_text() == before.pages[index].extract_text()
    spans = []

    def visit(text, _cm, _tm, font, _size):
        clean = " ".join(text.split())
        if clean:
            spans.append((clean, font))

    text = after.pages[target].extract_text(visitor_text=visit)
    assert ("AUTORIZADA" if language == "es-MX" else "AUTHORIZED") in text
    assert ("BLOQUEADA" if language == "es-MX" else "BLOCKED") not in text
    marker = "PROGRAMA DE EVALUACIÓN EN CUATRO FASES" if language == "es-MX" else "FOUR-PHASE ASSESSMENT PROGRAM"
    first = next(i for i, (value, _font) in enumerate(spans) if value == marker)
    for value, font in spans[first:]:
        descriptor = (font or {}).get("/FontDescriptor")
        assert descriptor is not None, f"Unembedded phase font: {value!r}"
        descriptor = descriptor.get_object()
        assert descriptor.get("/FontFile2") is not None, f"Missing TrueType font program: {value!r}"
