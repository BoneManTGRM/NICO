"""Spanish scored rows must not become semantic navigation destinations."""
import os
from pathlib import Path
import subprocess
import sys


def test_actual_spanish_strong_scorecard_keeps_dedicated_targets():
    from tests.test_scorecard_status_navigation_targets import (
        test_actual_scorecard_cells_do_not_steal_dedicated_section_targets,
    )
    test_actual_scorecard_cells_do_not_steal_dedicated_section_targets(True, 'strong')


def test_fuerte_matches_only_bounded_table_status():
    from nico.comprehensive_semantic_navigation_v1 import _scorecard_table_followup
    assert _scorecard_table_followup('FUERTE')
    assert _scorecard_table_followup('Fuerte 96/100')
    assert not _scorecard_table_followup('FUERTE · 96/100')
    assert not _scorecard_table_followup('Fuerte evidencia conservada')


def _worker():
    import base64
    from copy import deepcopy
    import io
    from pypdf import PdfReader
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_report_semantic_manifest_v1 import SECTION_BY_ID
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package

    ids = ('code_audit', 'dependency_library_ecosystem', 'secrets_exposure_review',
           'static_analysis', 'ci_cd_analysis', 'architecture_technical_debt', 'velocity_complexity')
    package = _package('es-MX')
    package['json']['assessment']['sections'] = [
        dict(id=key, label=SECTION_BY_ID[key]['title_en'], status='strong',
             presented_status='STRONG', score=score, presented_score=score,
             summary='Synthetic retained summary.', evidence=[f'DEDICATED_BODY_{index}'])
        for index, (key, score) in enumerate(zip(ids, (96, 86, 96, 96, 100, 96, 96)))
    ]
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    reader = PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64'])))
    destinations = {item.title: reader.get_destination_page_number(item)
                    for item in reader.outline if not isinstance(item, list)}
    all_text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    for index, key in enumerate(ids):
        title = SECTION_BY_ID[key]['title_es']
        page = reader.pages[destinations[title]]
        lines = (page.extract_text() or '').splitlines()
        # Navigation targets the heading; evidence may flow onto the next page.
        assert title in lines, title
        assert lines[lines.index(title) + 1].startswith('SÓLIDO · '), title
        assert f'DEDICATED_BODY_{index}' in all_text, title
        assert '/NICOScorecardPages' not in page, title
    assert package == before
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert result['approval_status'] == 'pending_human_approval'
    assert result['delivery_status'] == 'blocked_pending_human_approval'


def test_installed_spanish_worker_targets_all_seven_real_sections(tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    environment = owned_worker_environment(root, tmp_path, os.environ)
    completed = subprocess.run(
        [sys.executable, '-c',
         'from tests.test_spanish_strong_scorecard_navigation import _worker; _worker()'],
        cwd=root, env=environment, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
