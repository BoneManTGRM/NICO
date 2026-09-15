"""Synthetic compact-validator cases; retained quotations do not select locale."""
from copy import deepcopy
import io
import subprocess
import sys
import textwrap

import pytest
from reportlab.pdfgen import canvas

from nico import client_report_completion_v2 as completion
from nico.comprehensive_report_language_truth_v77 import (
    _EN_BOUNDARY_MARKERS, _ES_BOUNDARY_MARKERS,
)


def _case(language):
    canonical = {"identity": {"report_language": language}, "canonical_findings": []}
    register = {"summary": {
        "finding_population_reconciled": True,
        "semantic_duplicate_code_anchors_absent": True,
        "scanner_configuration_errors_promoted_to_code_findings": False,
        "unverified_tls_candidates_promoted_to_p1": False,
        "stable_alias_projection_idempotent": True,
        "decision_finding_count": 0,
    }}
    titles = completion._REVIEW_SECTION_TITLES_ES if language == "es-MX" else completion._REVIEW_SECTION_TITLES
    quoted = completion._REVIEW_SECTION_TITLES if language == "es-MX" else completion._REVIEW_SECTION_TITLES_ES
    markers = _ES_BOUNDARY_MARKERS if language == "es-MX" else _EN_BOUNDARY_MARKERS
    text = "\n".join(("AUTOMATED DRAFT", *titles, *markers))
    literal = '<span data-nico-client-literal="true">' + " / ".join(quoted) + "</span>"
    return canonical, register, text + "\n" + literal, text, markers


def _pdf(text):
    output = io.BytesIO()
    document = canvas.Canvas(output, invariant=1)
    for index, line in enumerate(text.splitlines()):
        document.drawString(30, 800 - index * 18, line)
    document.save()
    return output.getvalue()


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_compact_validator_uses_declared_locale_despite_other_language_titles(language):
    canonical, register, markdown, text, _ = _case(language)
    # Retained generated stage titles also are not language authority.
    rendered_html = markdown + " / ".join(completion._REVIEW_SECTION_TITLES_ES)
    before = deepcopy((canonical, register, markdown, rendered_html))
    result = completion._validate_final_surfaces(canonical, register, markdown, rendered_html, _pdf(text))
    assert result["four_part_ci_cd_boundary_in_markdown"] is True
    assert (canonical, register, markdown, rendered_html) == before


@pytest.mark.parametrize("language", ["en", "es-MX"])
@pytest.mark.parametrize("surface", ["markdown", "html", "pdf"])
def test_compact_validator_still_requires_selected_ci_boundary_on_every_surface(language, surface):
    canonical, register, markdown, text, markers = _case(language)
    surfaces = {"markdown": markdown, "html": markdown, "pdf": text}
    surfaces[surface] = surfaces[surface].replace(markers[0], "missing boundary")
    with pytest.raises(ValueError, match=f"final compact {surface} omitted CI/CD boundary"):
        completion._validate_final_surfaces(canonical, register, surfaces["markdown"], surfaces["html"], _pdf(surfaces["pdf"]))


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_compact_validator_does_not_accept_opposite_language_review_sections(language):
    canonical, register, markdown, text, _ = _case(language)
    titles = completion._REVIEW_SECTION_TITLES_ES if language == "es-MX" else completion._REVIEW_SECTION_TITLES
    for title in titles:
        markdown = markdown.replace(title, "missing section")
        text = text.replace(title, "missing section")
    with pytest.raises(ValueError, match="omitted decision-useful Comprehensive sections"):
        completion._validate_final_surfaces(canonical, register, markdown, markdown, _pdf(text))


@pytest.mark.parametrize("spanish", [False, True])
def test_production_pdf_sanitizer_respects_explicit_render_language(spanish):
    # A production bootstrap installs process-wide compatibility bindings. Run it
    # in isolation so this regression cannot alter another test's bootstrap state.
    code = textwrap.dedent("""
        import io, sys
        from reportlab.pdfgen import canvas
        from pypdf import PdfReader
        from nico.api.final_report_worker_bootstrap import app
        from nico import client_report_completion_v2 as completion
        spanish = sys.argv[1] == 'True'
        source = io.BytesIO()
        document = canvas.Canvas(source, invariant=1)
        english = 'NICO | Comprehensive client review | automated draft'
        document.drawString(30, 800, english)
        document.drawString(30, 780, 'QA funcional')
        document.save()
        original = source.getvalue()
        output = completion.sanitize_client_pdf_status(original, spanish=spanish)
        text = '\\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(output)).pages)
        if spanish:
            assert 'NICO | revisión integral del cliente | borrador automatizado' in text
            assert output == completion.sanitize_client_pdf_status(original)
        else:
            assert english in text
            assert 'NICO | revisión integral del cliente | borrador automatizado' not in text
        assert 'QA funcional' in text
        assert source.getvalue() == original
    """)
    result = subprocess.run([sys.executable, "-c", code, str(spanish)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
