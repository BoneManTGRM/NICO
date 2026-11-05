"""Installed worker attach/rebind must support content-sized supplements."""
import subprocess
import sys

import pytest


@pytest.mark.parametrize("language", ["en", "es-MX"])
@pytest.mark.parametrize("changed_field", [None, "markdown", "html", "findings_csv", "grow", "shrink"])
def test_installed_manifest_rebind_preserves_flowing_supplement(language, changed_field):
    result = subprocess.run([sys.executable, "-c", r'''
import base64, hashlib, io, sys
from copy import deepcopy
from pypdf import PdfReader
from nico.api import final_report_worker_bootstrap
from nico import comprehensive_artifact_manifest_approval_v1 as manifest
from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
from tests.test_comprehensive_artifact_manifest_approval_v1 import _package
package = _package()
canonical = package['json']
canonical['report_language'] = sys.argv[1]
canonical['identity'].update(report_language=sys.argv[1], run_id='run_'+'x'*176,
    repository='example/'+'r'*170, evidence_ledger_id='ledger_'+'l'*170)
from reportlab.pdfgen import canvas
buffer = io.BytesIO()
c = canvas.Canvas(buffer, invariant=1)
c.drawString(40, 770, "Índice de evidencias: registros 00–29" if sys.argv[1] == "es-MX" else "Evidence index: records 00–29")
c.drawString(40, 750, 'Auditoría de código' if sys.argv[1] == 'es-MX' else 'Code Audit')
for i in range(30):
    c.drawString(40, 720-i*18, f'Synthetic retained body evidence {i:02d}')
c.showPage(); c.save()
package['pdf_base64'] = base64.b64encode(buffer.getvalue()).decode('ascii')
if sys.argv[2] == 'grow':
    canonical['identity']['run_id'] = 'short_run'
original = deepcopy(package)
attached = manifest.attach_artifact_manifest(package)
pdf = base64.b64decode(attached['pdf_base64'])
reader = PdfReader(io.BytesIO(pdf))
texts = [p.extract_text() for p in reader.pages]
manifest_index = next(i for i,t in enumerate(texts) if 'Client Artifact Manifest' in t or 'Manifiesto de artefactos del cliente' in t)
assert len(reader.pages) - manifest_index > 2
if sys.argv[2] in ('grow', 'shrink'):
    attached['json']['identity']['run_id'] = ('run_'+'x'*176 if sys.argv[2] == 'grow' else 'short_run')
    attached['markdown'] += '\nSynthetic changed retained artifact\n'
elif sys.argv[2] != 'unchanged':
    attached[sys.argv[2]] += '\nSynthetic changed retained artifact\n'
rebound = manifest.rebind_artifact_manifest(attached)
assert package == original
final_pdf = base64.b64decode(rebound['pdf_base64'])
if sys.argv[2] == 'unchanged':
    assert final_pdf == pdf
else:
    assert final_pdf != pdf
    assert manifest.rebind_artifact_manifest(rebound)['pdf_base64'] == rebound['pdf_base64']
final_reader = PdfReader(io.BytesIO(final_pdf))
final_text = ''.join(p.extract_text() for p in final_reader.pages)
for i in range(30):
    assert f'Synthetic retained body evidence {i:02d}' in final_text
for before in reader.pages:
    if 'Synthetic retained body evidence 00' in before.extract_text():
        after = next(p for p in final_reader.pages if 'Synthetic retained body evidence 00' in p.extract_text())
        if sys.argv[2] not in ('grow', 'shrink'):
            assert before.get_contents().get_data() == after.get_contents().get_data()
assert final_reader.outline
from nico import comprehensive_manifest_navigation_v1 as navigation
navigation._validate_final_package(rebound)
assert len(final_reader.page_labels) == len(final_reader.pages)

count = len(final_reader.pages)
if sys.argv[2] == 'grow':
    assert count > len(reader.pages)
elif sys.argv[2] == 'shrink':
    assert count < len(reader.pages)
assert rebound['pdf_page_count'] == rebound['final_package_page_count'] == count
assert rebound['client_report_completion']['page_count'] == count
assert rebound['client_report_completion']['client_pdf_page_count'] == count
if sys.argv[1] == 'es-MX':
    assert 'Document page ' not in final_text
    for index, page in enumerate(final_reader.pages, 1):
        assert f'Página del documento {index} de {count}' in page.extract_text()
assert rebound['pdf_sha256'] == hashlib.sha256(final_pdf).hexdigest()
assert rebound['human_review_required'] is True
assert rebound['client_delivery_allowed'] is False
_validate_exact_artifact_hashes(rebound)
''', language, changed_field or 'unchanged'], check=False, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('damage', ['gap', 'label', 'approval', 'tail'])
def test_flowing_manifest_ownership_rejects_ambiguous_blocks(damage):
    from nico.comprehensive_artifact_manifest_approval_v1 import _flowing_manifest_block

    footer = 'NICO | exact-artifact review package | automated draft'
    pages = [
        footer + '\nIntegrity 1\nClient Artifact Manifest\nSHA-256',
        footer + '\nIntegrity 2\nRetained structured artifacts',
        footer + '\nIntegrity 3\nHuman Review and Exact-Artifact Approval Record\n'
        'Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED.',
    ]
    assert _flowing_manifest_block(pages) == (0, 3)
    if damage == 'gap':
        pages[1] = 'unowned report body'
    elif damage == 'label':
        pages[1] = pages[1].replace('Integrity 2', 'Integrity 7')
    elif damage == 'approval':
        pages[2] = pages[2].replace('Human Review and Exact-Artifact Approval Record', 'unknown')
    else:
        pages[2] = pages[2].replace('Automation cannot change this package', 'missing tail')
    with pytest.raises(ValueError):
        _flowing_manifest_block(pages)


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_refresh_growing_owned_block_rebuilds_navigation(language, monkeypatch):
    import io
    import hashlib
    from functools import partial
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico.comprehensive_human_review_package_cleanup_v1 import render_manifest_approval_supplement
    from nico.comprehensive_spanish_client_surface_localization_v85 import _render_spanish_manifest
    from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline

    renderer = partial(_render_spanish_manifest, manifest) if language == 'es-MX' else render_manifest_approval_supplement
    monkeypatch.setattr(manifest, '_render_manifest_approval_supplement', renderer)
    canonical = {'identity': {'report_language': language}}
    entries = [{'artifact_type': 'evidence_csv', 'filename': f'evidence_{i}.csv',
                'sha256': hashlib.sha256(str(i).encode()).hexdigest()} for i in range(40)]
    body = io.BytesIO()
    document = canvas.Canvas(body, invariant=1)
    document.drawString(40, 750, 'SYNTHETIC_DISTINCT_COVER')
    document.showPage()
    document.drawString(40, 750, 'Auditoría de código' if language == 'es-MX' else 'Code Audit')
    document.drawString(40, 700, 'PRESERVED_BODY_SENTINEL')
    document.showPage(); document.save()
    writer = PdfWriter()
    for blob in (body.getvalue(), renderer(canonical, entries[:1])):
        for page in PdfReader(io.BytesIO(blob)).pages:
            writer.add_page(page)
    initial = io.BytesIO(); writer.write(initial)
    pdf = semantic_renumber_and_outline(initial.getvalue())
    # Add a legitimate matching-title body heading only after generating the
    # initial contents, so the regression isolates the rebind growth path.
    original_reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter(); writer.clone_document_from_reader(original_reader)
    heading = io.BytesIO()
    document = canvas.Canvas(heading, invariant=1)
    document.drawString(40, 730, 'Índice de evidencias: registros 00–29' if language == 'es-MX' else 'Evidence mentioning table of contents')
    document.showPage(); document.save()
    body_page = next(p for p in writer.pages if 'PRESERVED_BODY_SENTINEL' in p.extract_text())
    body_page.merge_page(PdfReader(io.BytesIO(heading.getvalue())).pages[0])
    prepared = io.BytesIO(); writer.write(prepared); pdf = prepared.getvalue()
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 5
    refreshed = manifest._refresh_visible_manifest(pdf, canonical, entries)
    reader = PdfReader(io.BytesIO(refreshed))
    assert len(reader.pages) > len(PdfReader(io.BytesIO(pdf)).pages)
    text = ''.join(''.join(page.extract_text().split()) for page in reader.pages)
    assert text.count('PRESERVED_BODY_SENTINEL') == 1
    assert all(entry['sha256'] in text for entry in entries)
    assert reader.outline and len(reader.page_labels) == len(reader.pages)
    assert manifest._refresh_visible_manifest(refreshed, canonical, entries) == refreshed
    # Legacy/unmarked contents are ambiguous in this growth path: never guess
    # ownership from a body title or remove any page by substring matching.
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(io.BytesIO(pdf)))
    for page in writer.pages:
        for key in ('/NICOGeneratedTOC', '/NICOGeneratedTOCOrdinal'):
            if key in page:
                del page[key]
    unmarked = io.BytesIO(); writer.write(unmarked)
    with pytest.raises(ValueError, match='Generated contents ownership'):
        manifest._refresh_visible_manifest(unmarked.getvalue(), canonical, entries)

