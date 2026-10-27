"""Page-sized explanations stay coherent; oversized explanations still flow."""
import base64
from copy import deepcopy
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pypdf import PdfReader


def _assessment(language, extreme):
    from tests.test_report_score_explanation import assessment
    value = assessment((0, 0, 0, 0))
    value['sections'] = [dict(id=f'control{i}', label=f'CONTROL_{i}', score=96,
        presented_score=96, status='strong', presented_status='strong', summary='Synthetic summary.')
        for i in range(26 if language == 'en' else 20)]
    if extreme:
        value['score_contract']['other_assurance_penalties'] = {
            f'COMPLETE_DEDUCTION_{i:03d}': 0 for i in range(80)}
    return value


def _check(pdf, language, extreme):
    from nico.report_score_explanation import LABELS_ES
    pages = [' '.join((page.extract_text() or '').split()) for page in PdfReader(io.BytesIO(pdf)).pages]
    labels = ['Technical-to-adjusted score explanation', 'Technical score',
              'Candidate-volume deduction', 'Missing raw-payload deduction',
              'Incomplete-analyzer deduction', 'Other named deductions',
              'Retained formula', 'Evidence-adjusted score']
    labels = [LABELS_ES.get(label, label) if language == 'es-MX' else label for label in labels]
    joined = ' '.join(pages)
    assert joined.count(labels[0]) == 1, ('explanation headings', language, joined.count(labels[0]))
    assert joined.count('92 - 0 - 0 - 0 - 0 = 92') == 1, ('explanation formulas', language)
    start = next(i for i, text in enumerate(pages) if labels[0] in text)
    if not extreme:
        assert all(label in pages[start] for label in labels), (language, start)
        assert '92 - 0 - 0 - 0 - 0 = 92' in pages[start]
    else:
        text = ' '.join(pages)
        assert all(label in text for label in labels)
        for i in range(80):
            assert text.count(f'COMPLETE_DEDUCTION_{i:03d}: 0') == 1
        end = next(i for i, text in enumerate(pages) if '92 - 0 - 0 - 0 - 0 = 92' in text)
        assert end > start


@pytest.mark.parametrize('language', ['en', 'es-MX'])
@pytest.mark.parametrize('extreme', [False, True])
def test_final_scorecard_explanation_coherence_and_safe_overflow(language, extreme):
    from nico.v2_report_quality_repairs import _scorecard_page
    from nico.v2_localized_report_quality_repairs import _spanish_scorecard_page
    canonical = {'report_language': language, 'assessment': _assessment(language, extreme)}
    before = deepcopy(canonical)
    pdf = (_scorecard_page if language == 'en' else _spanish_scorecard_page)(canonical)
    _check(pdf, language, extreme)
    assert canonical == before


@pytest.mark.parametrize('language', ['en', 'es-MX'])
@pytest.mark.parametrize('extreme', [False, True])
def test_shared_initial_pdf_explanation_coherence_and_safe_overflow(language, extreme):
    from nico.comprehensive_report_package import _pdf
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    value = _assessment(language, extreme)
    before = deepcopy(value)
    encoded, error, _ = _pdf(
        {'run_id': 'comprun_synthetic_pagination', 'repository': 'owned/synthetic', 'commit_sha': 'a' * 40},
        value, [], '2026-01-01',
        localize_presentation=_translate_presentation if language == 'es-MX' else None)
    assert error is None
    _check(base64.b64decode(encoded), language, extreme)
    assert value == before


def _worker(language, extreme):
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package
    package = _package(language)
    package['json']['assessment'] = _assessment(language, extreme)
    package['json']['assessment']['report_language'] = language
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    _check(base64.b64decode(result['pdf_base64']), language, extreme)
    assert package == before
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert result['approval_status'] == 'pending_human_approval'
    assert result['delivery_status'] == 'blocked_pending_human_approval'


@pytest.mark.parametrize('language', ['en', 'es-MX'])
@pytest.mark.parametrize('extreme', [False, True])
def test_installed_final_explanation_layout(language, extreme, tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c',
        'from tests.test_score_explanation_pagination import _worker; import sys; _worker(sys.argv[1],sys.argv[2]=="True")',
        language, str(extreme)], cwd=root, env=owned_worker_environment(root, tmp_path, os.environ),
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('mutation', ['partial', 'fraction', 'negative', 'oversized', 'ordinal', 'total', 'underclaimed'])
def test_invalid_owned_scorecard_ranges_fail_closed(mutation):
    from pypdf.generic import NameObject, NumberObject, FloatObject
    from nico.v2_report_quality_repairs import _scorecard_page, _owned_scorecard_page_count
    reader = PdfReader(io.BytesIO(_scorecard_page({'assessment': _assessment('en', True)})))
    first = reader.pages[0]
    if mutation == 'partial': del first['/NICOScorecardPages']
    elif mutation == 'fraction': first[NameObject('/NICOScorecardPages')] = FloatObject(1.5)
    elif mutation == 'negative': first[NameObject('/NICOScorecardPages')] = NumberObject(-1)
    elif mutation == 'oversized': first[NameObject('/NICOScorecardPages')] = NumberObject(len(reader.pages)+1)
    elif mutation == 'ordinal': reader.pages[1][NameObject('/NICOScorecardPage')] = NumberObject(0)
    elif mutation == 'total': reader.pages[1][NameObject('/NICOScorecardPages')] = NumberObject(1)
    elif mutation == 'underclaimed': first[NameObject('/NICOScorecardPages')] = NumberObject(1)
    with pytest.raises(ValueError, match='ownership is inconsistent'):
        _owned_scorecard_page_count(reader, 0)


def _repeat_worker(entrypoint):
    from nico.api import final_report_worker_bootstrap
    from nico.comprehensive_report_package import _pdf
    from nico import v2_report_quality_repairs as quality
    from nico import v2_report_quality_runtime_compat as compatibility
    assessment = _assessment('en', True)
    assessment['sections'][0]['evidence'] = ['ADJACENT_BODY_MUST_SURVIVE']
    identity = {'run_id': 'comprun_owned_repeat', 'commit_sha': 'a'*40}
    encoded, error, _ = _pdf(identity, assessment, [], '2026-01-01')
    assert error is None
    package = {'json': {'identity': identity, 'assessment': assessment},
               'pdf_base64': encoded, 'markdown': '', 'html': ''}
    before = deepcopy(package)
    repair = quality.repair_rendered_report if entrypoint == 'quality' else compatibility.repair_rendered_report
    first = repair(package)
    second = repair(first)
    for result in (first, second):
        pdf = base64.b64decode(result['pdf_base64'])
        _check(pdf, 'en', True)
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages)
        assert text.count('ADJACENT_BODY_MUST_SURVIVE') == 1
    assert package == before
    assert [page.extract_text() for page in PdfReader(io.BytesIO(base64.b64decode(first['pdf_base64']))).pages] == [
        page.extract_text() for page in PdfReader(io.BytesIO(base64.b64decode(second['pdf_base64']))).pages]


@pytest.mark.parametrize('entrypoint', ['quality', 'compatibility'])
def test_both_repair_entrypoints_replace_whole_owned_block_repeatedly(entrypoint, tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c',
        'from tests.test_score_explanation_pagination import _repeat_worker; import sys; _repeat_worker(sys.argv[1])',
        entrypoint], cwd=root, env=owned_worker_environment(root, tmp_path, os.environ),
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr

@pytest.mark.parametrize('entrypoint', ['quality', 'compatibility', 'v1', 'v2', 'v3'])
def test_unmarked_ambiguous_continuation_does_not_claim_success(entrypoint):
    """Legacy content has no structural proof that the next page is unrelated."""
    from pypdf import PdfWriter
    from nico import v2_report_quality_repairs as quality
    from nico import v2_report_quality_runtime_compat as compatibility
    from tests.test_v2_report_quality_runtime_compat import _package
    package = _package('Canonical Technical Scorecard')
    reader = PdfReader(io.BytesIO(base64.b64decode(package['pdf_base64'])))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # A second unmarked scorecard page is indistinguishable from an unrelated
    # page by ownership metadata. It must not be left as a duplicate silently.
    continuation = PdfReader(io.BytesIO(quality._scorecard_page(
        {'assessment': _assessment('en', True)}))).pages[-1]
    for key in ('/NICOScorecardPage', '/NICOScorecardPages'):
        del continuation[key]
    assert 'Canonical Technical Scorecard' not in continuation.extract_text()
    writer.add_page(continuation)
    output = io.BytesIO()
    writer.write(output)
    package['pdf_base64'] = base64.b64encode(output.getvalue()).decode('ascii')
    before = deepcopy(package)
    repair = quality.repair_rendered_report if entrypoint == 'quality' else compatibility.repair_rendered_report
    if entrypoint.startswith('v'):
        import importlib
        repair = importlib.import_module('nico.v2_automated_draft_quality_compat_' + entrypoint).repair_rendered_report
    result = repair(package)
    assert result['report_quality_repair_status'] == 'unavailable'
    assert result['pdf_base64'] == before['pdf_base64']
    assert result['json'] == before['json']
    assert result['premium_report_renderer']['scorecard_rows_verified'] is False
    assert not result['premium_report_renderer'].get('automated_draft_is_valid_unapproved_state')
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True
    assert package == before


def _unavailable_worker():
    from nico.api import final_report_worker_bootstrap
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    from nico.v2_report_quality_repairs import _repair_unavailable
    from tests.test_v2_premium_report_renderer import _package
    package = _package('en')
    before = deepcopy(package)
    phase17.repair_rendered_report = _repair_unavailable
    def forbidden_finalize(*args, **kwargs):
        raise AssertionError('unavailable repair reached finalization')
    from nico import client_report_completion_v2 as completion
    completion.finalize_client_report_package = forbidden_finalize
    with pytest.raises(ValueError, match='report quality repair unavailable'):
        phase17.rebuild_client_artifacts(package)
    assert package == before


def test_phase17_stops_unavailable_repair_before_finalization(tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c',
        'from tests.test_score_explanation_pagination import _unavailable_worker; _unavailable_worker()'],
        cwd=root, env=owned_worker_environment(root, tmp_path, os.environ),
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
