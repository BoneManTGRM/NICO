"""First installed render must support a canonical scorecard spanning pages."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _assert_first_render():
    import base64
    from copy import deepcopy
    import io
    import re
    from pypdf import PdfReader
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    _install_production_wrappers()
    package = _package('es-MX')
    sections = [dict(id=f'control{i}', label=f'CONTROL_{i}', presented_status='gray',
                     presented_score=None,
                     summary=f'SUMMARY_{i}_START ' + ' '.join(f'WORD{i}_{j}' for j in range(35))
                     + f' SUMMARY_{i}_END') for i in range(32)]
    package['json']['assessment']['sections'] = sections
    before = deepcopy(package)
    # This is the initial real producer/Phase17 render, not a replacement-helper
    # call using a PDF that already carries replacement ownership markers.
    rendered = rebuild_client_artifacts(package)
    reader = PdfReader(io.BytesIO(base64.b64decode(rendered['pdf_base64'])))
    owned_indices = [index for index, page in enumerate(reader.pages)
                     if '/NICOScorecardPages' in page]
    assert len(owned_indices) > 1
    assert owned_indices == list(range(owned_indices[0], owned_indices[0] + len(owned_indices)))
    for offset, index in enumerate(owned_indices):
        assert reader.pages[index]['/NICOScorecardPage'] == offset
        assert reader.pages[index]['/NICOScorecardPages'] == len(owned_indices)
    text = re.sub(r'\s+', '', '\n'.join(reader.pages[index].extract_text() or ''
                                      for index in owned_indices))
    surrounding = re.sub(r'\s+', '', '\n'.join(page.extract_text() or ''
        for index, page in enumerate(reader.pages) if index not in owned_indices))
    for section in sections:
        start = section['summary'].split()[0]
        # Detailed control sections intentionally repeat each summary. Uniqueness
        # belongs to the authored scorecard block, not to the whole report.
        assert text.count(start) == 1, (start, text.count(start))
        assert surrounding.count(start) == 1, (start, surrounding.count(start))
        assert section['label'] in text
        assert section['label'] in surrounding
        for token in section['summary'].split():
            assert token in text, token
            assert token in surrounding, token
    assert package == before
    assert rendered['json']['human_review_required'] is True
    assert rendered['json']['client_delivery_allowed'] is False
    assert sum('/NICOScorecardPages' in page for page in reader.pages) > 1


def test_first_installed_spanish_render_accepts_multipage_canonical_scorecard(tmp_path):
    root = Path(__file__).resolve().parents[1]
    from tests.owned_worker_environment import owned_worker_environment
    environment = owned_worker_environment(root, tmp_path, os.environ)
    code = "import runpy,sys; runpy.run_path(sys.argv[1])['_assert_first_render']()"
    completed = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve())],
                               cwd=root, env=environment, capture_output=True, text=True,
                               timeout=120, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _assert_final_decimal_score(language):
    import base64
    from copy import deepcopy
    import io
    import re
    from pypdf import PdfReader
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    _install_production_wrappers()
    package = _package(language)
    section = package['json']['assessment']['sections'][0]
    section.update(score=95.8, presented_score=95.8)
    before = deepcopy(package)
    rendered = rebuild_client_artifacts(package)
    reader = PdfReader(io.BytesIO(base64.b64decode(rendered['pdf_base64'])))
    text = re.sub(r'\s+', '', '\n'.join(page.extract_text() or '' for page in reader.pages))
    assert '96/100' in text
    assert '95/100' not in text
    assert package == before
    assert rendered['json']['human_review_required'] is True
    assert rendered['json']['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_final_installed_decimal_score_uses_same_rounding_in_both_languages(language, tmp_path):
    root = Path(__file__).resolve().parents[1]
    from tests.owned_worker_environment import owned_worker_environment
    environment = owned_worker_environment(root, tmp_path, os.environ)
    code = "import runpy,sys; runpy.run_path(sys.argv[1])['_assert_final_decimal_score'](sys.argv[2])"
    completed = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve()), language],
                               cwd=root, env=environment, capture_output=True, text=True,
                               timeout=120, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
