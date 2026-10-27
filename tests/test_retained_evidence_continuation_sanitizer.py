"""Generic retained-evidence headings do not make client continuations internal."""
import base64
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas


@pytest.mark.parametrize('label', ['Retained Evidence', 'Evidencia conservada'])
@pytest.mark.parametrize('first_count', [20, 22])
def test_continuation_preserves_all_details_and_adjacent_sections(label, first_count):
    from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    lines = [f'NICO-WORK-SYNTHETIC detail {i:02d}' for i in range(25)]
    for group in (lines[:first_count], lines[first_count:] + [
        'Staffing - ' + label, 'Staffing synthetic scope',
        'Stakeholder - ' + label, 'Stakeholder synthetic scope']):
        for index, text in enumerate(['Roadmap - ' + label, *group]):
            pdf.drawString(48, 744 - index * 18, text)
        pdf.showPage()
    pdf.save()
    output = sanitize_client_pdf_status(buffer.getvalue())
    reader = PdfReader(io.BytesIO(output))
    assert len(reader.pages) == 2
    text = '\n'.join(page.extract_text() for page in reader.pages)
    for line in lines + ['Staffing synthetic scope', 'Stakeholder synthetic scope']:
        assert line in text


@pytest.mark.parametrize('text', [
    'Retained Evidence\nstage_execution.internal',
    'Evidencia conservada\nstage_execution.internal',
    'artifact_schema\nsnapshot.internal',
    'snapshot.one\nsnapshot.two',
    'report_contract_reason',
    'comprehensive_final_report_semantic_contract_failed',
    'Evidence Appendix',
    'Apéndice de evidencia',
    'Instantánea inmutable del repositorio\nEvidencia conservada\nID de etapa: immutable_repository_snapshot',
])
def test_genuine_internal_page_rejection_remains(text):
    from nico.client_pdf_status_sanitizer_v1 import _drop_internal_page
    assert _drop_internal_page(text) is True


def _worker(language):
    from copy import deepcopy
    from nico.api import final_report_worker_bootstrap as worker
    from tests.test_roadmap_pdf_detail_completeness import _five_gap_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    assert worker.FINAL_REPORT_WORKER_RUNTIME['nested_renderer_orchestration_installed'] is False
    package = _five_gap_package(language)
    package['json']['stage_summaries'].append({
        'stage_id': 'stakeholder_and_business_alignment', 'status': 'complete',
        'summary': 'Stage evidence was recorded.', 'evidence': ['SYNTHETIC-STAKEHOLDER-CONTINUATION'],
        'findings': [], 'unavailable': [],
    })
    stages = package['json']['stage_summaries']
    staffing = next(s for s in stages if s['stage_id'] == 'staffing_sequencing_and_cost')
    staffing['evidence'] = ['SYNTHETIC-STAFFING-CONTINUATION']
    before = deepcopy(package)
    expected = next(s for s in stages if s['stage_id'] == 'six_month_roadmap')['evidence']
    assert len(expected) == 25
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    compact = lambda s: ''.join(s.split())
    text = compact('\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages))
    for line in [*expected, 'SYNTHETIC-STAFFING-CONTINUATION', 'SYNTHETIC-STAKEHOLDER-CONTINUATION']:
        assert compact(line) in text
    assert package == before
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True
    assert result['approval_status'] == 'pending_human_approval'
    assert result['delivery_status'] == 'blocked_pending_human_approval'


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_dedicated_worker_preserves_roadmap_and_adjacent_sections(language, tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    environment = owned_worker_environment(root, tmp_path, os.environ)
    code = 'from tests.test_retained_evidence_continuation_sanitizer import _worker; import sys; _worker(sys.argv[1])'
    completed = subprocess.run([sys.executable, '-c', code, language], cwd=root,
        env=environment, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
