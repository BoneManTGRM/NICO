"""Synthetic composition checks only; no real approval authority or delivery."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import pytest

from pypdf import PdfReader
from pypdf.generic import ContentStream
from reportlab.pdfgen import canvas

from nico import comprehensive_approved_report_v1 as approved
from nico.comprehensive_express_quality_v7 import _front_matter_overlay, _overlay_front_matter
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from tests.test_v2_golden_premium_cover_restoration import _package


def extracted(pdf):
    return [' '.join((p.extract_text() or '').split()) for p in PdfReader(io.BytesIO(pdf)).pages]


def convert(package, tmp_path):
    original = deepcopy(package)
    source = base64.b64decode(package['pdf_base64'])
    result = approved.build_approved_report_package(
        package, reviewer='Synthetic reviewer', reviewer_role='Synthetic specialist',
        decision_reason='Synthetic composition qualification only; no authority conferred.',
        decided_at='2026-11-11T00:00:00Z')
    pdf = base64.b64decode(result['pdf_base64'])
    count = len(PdfReader(io.BytesIO(pdf)).pages)
    source_count = len(PdfReader(io.BytesIO(source)).pages)
    assert count > source_count
    assert result['pdf_page_count'] == result['final_package_page_count'] == count
    assert result['pdf_sha256'] == hashlib.sha256(pdf).hexdigest()
    assert result['source_review_artifact_identity']['pdf_sha256'] == hashlib.sha256(source).hexdigest()
    assert result['json']['approval_projection']['source_review_pdf_sha256'] == hashlib.sha256(source).hexdigest()
    assert result['client_delivery_allowed'] is False
    assert result['json']['client_delivery_allowed'] is False
    assert result['json']['approval_projection']['client_delivery_allowed'] is False
    assert package == original
    text = extracted(pdf)
    (tmp_path / 'source.pdf').write_bytes(source)
    (tmp_path / 'converted.pdf').write_bytes(pdf)
    (tmp_path / 'receipt.json').write_text(json.dumps({
        'source_pages': source_count, 'final_pages': count,
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'pdf_bytes': len(pdf),
        'pdf_page_count': result['pdf_page_count'],
        'final_package_page_count': result['final_package_page_count'],
        'client_delivery_allowed': result['client_delivery_allowed'],
        'input_unchanged': package == original, 'source_text': extracted(source),
        'final_text': text}, indent=2) + '\n')
    return result, text


def test_actual_merged_overlay_preserves_declined_count_fields(tmp_path):
    raw = io.BytesIO()
    page = canvas.Canvas(raw, invariant=1)
    for label in ['Synthetic underlying page one', 'Synthetic underlying page two']:
        page.drawString(42, 400, label)
        page.showPage()
    page.save()
    identity = {'repository': 'synthetic/overlay', 'commit_sha': 'a' * 40}
    assessment = {'executive_risk_register': [{'title': 'Final PDF pages: 2'}, {'title': 'Page 1 of 2'}]}
    overlay = _front_matter_overlay(identity, assessment, {}, '2026-11-11T00:00:00Z', 2)
    source = _overlay_front_matter(raw.getvalue(), overlay)
    reader = PdfReader(io.BytesIO(source))
    for p in reader.pages:
        operators = [op for _, op in ContentStream(p.get_contents(), reader).operations]
        assert b'q' in operators and b'Q' in operators
    package = {'json': {'identity': identity, 'assessment': assessment,
                       'client_delivery_allowed': False},
               'markdown': 'Technical evidence remains literal.',
               'html': '<p>Technical evidence remains literal.</p>',
               'pdf_base64': base64.b64encode(source).decode(),
               'pdf_sha256': hashlib.sha256(source).hexdigest()}
    result, text = convert(package, tmp_path)
    assert 'Synthetic underlying page one' in text[0]
    assert 'Synthetic underlying page two' in text[1]
    assert 'PRIORITY DECISIONS 1 Final PDF pages: 2 2 Page 1 of 2' in text[0]
    assert 'Page 1 of 2' in text[0] and 'Page 2 of 2' in text[1]
    assert 'Final PDF pages: 2' in text[1]
    assert 'Final PDF pages: 3' not in text[1]
    assert result['json']['assessment']['executive_risk_register'] == assessment['executive_risk_register']


@pytest.fixture
def production_lifecycle_binding(tmp_path):
    from nico.comprehensive_approved_lifecycle_consistency_v1 import install_approved_lifecycle_consistency
    result = install_approved_lifecycle_consistency()
    bound = approved.build_approved_report_package
    assert result['installed'] is True
    assert result['cross_format_fail_closed'] is True
    assert getattr(approved, '_nico_approved_lifecycle_consistency_v1_installed', False) is True
    assert bound.__code__.co_filename.endswith('/nico/comprehensive_approved_lifecycle_consistency_v1.py')
    assert bound.__code__.co_name == 'build_consistent_approved_report'
    (tmp_path / 'binding.json').write_text(json.dumps({
        'installer': result, 'callable_module': bound.__module__,
        'code_filename': bound.__code__.co_filename,
        'code_firstlineno': bound.__code__.co_firstlineno,
        'code_name': bound.__code__.co_name,
        'phase': 'fixture before canonical rebuild and approved builder call'}, indent=2) + '\n')
    return bound


def test_canonical_rebuild_dark_cover_then_installed_approved_builder(tmp_path, production_lifecycle_binding):
    canonical_package = _package()
    original = deepcopy(canonical_package)
    package = rebuild_client_artifacts(canonical_package)
    assert canonical_package == original
    source = extracted(base64.b64decode(package['pdf_base64']))
    assert 'HUMAN REVIEW Pending' in source[0]
    assert 'CLIENT DELIVERY Blocked' in source[0]
    assert package['premium_report_renderer']['dark_branded_cover_restored'] is True
    assert approved.build_approved_report_package is production_lifecycle_binding
    result, text = convert(package, tmp_path)
    assert 'HUMAN REVIEW Approved' in text[0]
    assert 'CLIENT DELIVERY Controlled' in text[0]
    joined = ' '.join(text)
    assert 'High-complexity code hotspot' in joined
    assert 'apps/web/app/operations/page.tsx:177' in joined
    assert 'The technical analysis is unchanged' in joined
    assert result['json']['canonical_findings'] == package['json']['canonical_findings']
    assert result['approved_lifecycle_consistency']['status'] == 'valid'
