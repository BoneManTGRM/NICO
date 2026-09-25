"""Localize display labels without erasing retained scanner status identifiers."""
from copy import deepcopy
import base64
import io

import pytest
from pypdf import PdfReader


def scanner_stage(state: str, language: str, *, status_only: bool = False):
    from nico.comprehensive_human_review_package_cleanup_v1 import build_scanner_execution_stage
    from nico import v2_premium_report_renderer as renderer

    record = {
        'scanner_name': 'bandit',
        'status' if status_only else 'state': state,
        'completed': state.startswith('completed'),
        'exact_commit_match': True,
        'artifact_hash': 'a' * 64,
        'findings': [],
    }
    canonical = {'report_language': language, 'scanner_execution_records': [record]}
    before = deepcopy(canonical)
    stage = build_scanner_execution_stage(canonical, renderer)
    assert canonical == before
    return next(line for line in stage['evidence'] if line.startswith('bandit: '))


@pytest.mark.parametrize('state', ['completed_with_findings', 'completed_clean', 'timed_out', 'review_required'])
@pytest.mark.parametrize('status_only', [False, True])
def test_structured_scanner_states_remain_exact_identifiers(state, status_only):
    line = scanner_stage(state, 'es-MX', status_only=status_only)
    assert line.startswith('bandit: ' + state + '; ')


@pytest.mark.parametrize('state,label', [('completed', 'completada'), ('failed', 'fallida'), ('partial', 'parcial')])
def test_plain_scanner_statuses_still_receive_spanish_labels(state, label):
    assert scanner_stage(state, 'es-MX').startswith('bandit: ' + label + '; ')


@pytest.mark.parametrize('state', ['completed_with_findings', 'completed_clean', 'timed_out', 'completed', 'failed'])
def test_english_stage_copy_is_unchanged(state):
    assert scanner_stage(state, 'en') == (
        'bandit: ' + state + '; exact commit=yes; artifact=retained; '
        'confirmed material finding count=0; raw finding payload embedded=no.'
    )


def test_public_spanish_export_retains_machine_status_in_all_three_formats():
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    package = _package('es-MX')
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    # This is the same invariant that failed in the original terminal parity test;
    # it does not replace or modify the existing exact-artifact golden assertions.
    assert 'completed_with_findings' in result['markdown']
    assert 'completed_with_findings' in result['html']
    pdf_text = '\n'.join(page.extract_text() or '' for page in
                         PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    assert 'completed_with_findings' in pdf_text
    assert 'ENTREGA AL CLIENTE BLOQUEADA' in result['markdown']
    assert package == before
