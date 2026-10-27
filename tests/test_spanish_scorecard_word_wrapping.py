"""Readable authored score labels retain whole words at the existing font size."""
import io
import os
from pathlib import Path
import subprocess
import sys

from pypdf import PdfReader


def _assert_words(pdf):
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page for page in reader.pages if '/NICOScorecardPages' in page]
    assert pages
    lines = '\n'.join(page.extract_text() or '' for page in pages).splitlines()
    assert 'Puntuación' in lines
    assert any(line in ('PUNTUACIÓN', 'SIN PUNTUACIÓN') for line in lines)
    assert not any(line in ('Puntuaci', 'ón', 'SIN PUNT', 'UACIÓN') for line in lines)


def test_actual_spanish_scorecard_preserves_whole_score_label_words():
    from nico.v2_localized_report_quality_repairs import _spanish_scorecard_page
    _assert_words(_spanish_scorecard_page({'assessment': {'sections': [
        dict(label='Control', status='gray', score=None, summary='Synthetic summary.')
    ]}}))


def test_shared_scorecard_keeps_english_geometry_and_fonts():
    from nico.comprehensive_report_package import _scorecard_pdf_table
    table = _scorecard_pdf_table([], width=520.8, localized=lambda value: value)
    assert table._colWidths == [520.8 * fraction for fraction in (.23, .23, .11, .43)]
    assert all(cell.style.fontSize == 9 for row in table._cellvalues for cell in row)


def _worker():
    import base64
    from copy import deepcopy
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package
    package = _package('es-MX')
    package['json']['assessment']['sections'][0].update(score=None, presented_score=None, status='gray', presented_status='gray')
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    _assert_words(base64.b64decode(result['pdf_base64']))
    assert package == before
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False


def test_installed_spanish_final_scorecard_preserves_whole_score_label_words(tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, '-c',
        'from tests.test_spanish_scorecard_word_wrapping import _worker; _worker()'],
        cwd=root, env=owned_worker_environment(root, tmp_path, os.environ),
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_supported_spanish_width_remains_positive_and_preserves_total():
    from nico.comprehensive_report_package import _scorecard_pdf_table
    labels={'Score':'Puntuación','NOT SCORED':'SIN PUNTUACIÓN'}
    table=_scorecard_pdf_table([],width=520.8,localized=lambda value:labels.get(value,value))
    assert all(width>0 for width in table._colWidths)
    assert abs(sum(table._colWidths)-520.8)<1e-9
