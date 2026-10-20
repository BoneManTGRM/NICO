"""Ordinary reports grow with evidence; explicit legacy limits remain fail-closed."""
import base64
import io
from collections import Counter
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from nico.comprehensive_client_ready_projection_v1 import compose_compact_client_pdf as legacy_compose
from tests.test_client_pdf_compose_v2 import _pdf


@pytest.mark.parametrize('primary', [1, 20, 58])
def test_small_ordinary_reports_preserve_pages_without_reflow(monkeypatch, primary):
    from nico import comprehensive_pdf_reflow_v1 as reflow

    def unexpected_reflow(_pdf):
        pytest.fail('Reports at or below 60 pages must not incur composition reflow')

    monkeypatch.setattr(reflow, 'compact_sparse_stage_pages', unexpected_reflow)
    base = _pdf(*[[f'PRIMARY_{i} immutable content'] for i in range(primary)])
    register, gate = _pdf(['REGISTER_REQUIRED']), _pdf(['GATE_REQUIRED'])
    result = compose_compact_client_pdf(base, register, gate)
    expected = [page.extract_text() for pdf in (base, register, gate)
                for page in PdfReader(io.BytesIO(pdf)).pages]
    assert [page.extract_text() for page in PdfReader(io.BytesIO(result)).pages] == expected


@pytest.mark.parametrize('primary,required', [(80, 2), (3, 90), (120, 80)])
def test_ordinary_composition_preserves_large_primary_and_required_sets(primary, required):
    base = _pdf(*[[f'PRIMARY_{i:03d} P1 immutable evidence'] for i in range(primary)])
    register = _pdf(*[[f'REGISTER_{i:03d} pending human disposition'] for i in range(required)])
    gate = _pdf(['HUMAN_REVIEW_REQUIRED CLIENT_DELIVERY_BLOCKED'])
    review = _pdf(['REVIEW_COMPONENT_REQUIRED'])
    ci = _pdf(['CI_BOUNDARY_REQUIRED'])
    human = _pdf(['HUMAN_EVIDENCE_REQUIRED'])
    source = (base, register, gate, review, ci, human)
    result = compose_compact_client_pdf(base, register, gate, review_pdf=review,
                                       ci_boundary_pdf=ci, human_evidence_pdf=human)
    pages = PdfReader(io.BytesIO(result)).pages
    assert len(pages) == primary + required + 4 > 75
    actual = [page.extract_text() for page in pages]
    expected = [page.extract_text() for pdf in (base, ci, review, human, register, gate)
                for page in PdfReader(io.BytesIO(pdf)).pages]
    assert actual == expected
    assert Counter(' '.join(actual).split()) == Counter(' '.join(expected).split())
    assert source == (base, register, gate, review, ci, human)


@pytest.mark.parametrize("limit", [60, 75])
def test_explicit_legacy_cap_rejects_without_truncation(limit):
    base = _pdf(*[[f'PRIMARY_{i}'] for i in range(80)])
    with pytest.raises(ValueError, match=f'{limit}-page boundary') as error:
        compose_compact_client_pdf(base, _pdf(['Register']), _pdf(['Gate']), page_limit=limit)
    assert error.value.pdf_cap_diagnostic['total_pages'] == 82
    assert error.value.pdf_cap_diagnostic['page_limit'] == limit
    from nico.pdf_cap_failure_diagnostics import sanitize_pdf_cap_diagnostic
    assert sanitize_pdf_cap_diagnostic(error.value.pdf_cap_diagnostic) is not None
    assert len(PdfReader(io.BytesIO(base)).pages) == 80


@pytest.mark.parametrize('limit', [0, -1, True, 75.5, '75'])
def test_invalid_explicit_limit_is_configuration_error(limit):
    with pytest.raises(ValueError, match='positive integer or None'):
        compose_compact_client_pdf(_pdf(['Primary']), _pdf(['Register']), _pdf(['Gate']), page_limit=limit)


def test_large_manifest_and_rebinding_preserve_hash_and_pending_authority():
    from tests.test_comprehensive_artifact_manifest_approval_v1 import _package
    from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest, rebind_artifact_manifest
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    package = _package()
    package['pdf_base64'] = base64.b64encode(_pdf(*[[f'RETAINED_PAGE_{i:03d}'] for i in range(80)])).decode()
    snapshot = deepcopy(package)
    result = rebind_artifact_manifest(attach_artifact_manifest(package))
    _validate_exact_artifact_hashes(result)
    pages = PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages
    assert len(pages) > 80
    words = Counter(' '.join(page.extract_text() for page in pages).split())
    assert all(words[f'RETAINED_PAGE_{i:03d}'] == 1 for i in range(80))
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert package == snapshot
    tampered = deepcopy(result)
    tampered['pdf_base64'] = base64.b64encode(_pdf(['REPLACED CONTENT'])).decode()
    with pytest.raises(ValueError):
        _validate_exact_artifact_hashes(tampered)


def test_final_surface_validation_accepts_large_complete_report():
    from tests.test_client_report_completion_v2 import _package
    from nico import client_report_completion_v2 as completion
    from pypdf import PdfWriter
    result = completion.finalize_client_report_package(_package())
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))))
    writer.append(PdfReader(io.BytesIO(_pdf(*[[f'ADDITIONAL_EVIDENCE_{i:03d}'] for i in range(80)]))))
    output = io.BytesIO(); writer.write(output)
    canonical = result['json']
    validation = completion._validate_final_surfaces(canonical, canonical['client_finding_remediation_register'],
                                                   result['markdown'], result['html'], output.getvalue())
    assert validation['client_pdf_page_count'] > 75
    assert validation['client_pdf_page_boundary'] is None
    assert validation['client_pdf_length_policy'] == 'evidence_sized'


def test_legacy_projection_also_defaults_to_evidence_sized_reports():
    base = _pdf(*[[f'LEGACY_PRIMARY_{i:03d}'] for i in range(80)])
    result = legacy_compose(base, _pdf(['Register']), _pdf(['Gate']))
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 82
    text = ' '.join(page.extract_text() for page in reader.pages)
    assert all(f'LEGACY_PRIMARY_{i:03d}' in text for i in range(80))
    with pytest.raises(ValueError, match='60-page boundary'):
        legacy_compose(base, _pdf(['Register']), _pdf(['Gate']), page_limit=60)
