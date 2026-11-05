from copy import deepcopy

import pytest

from tests.test_spanish_retained_candidate_contracts import _isolated_preflight_test


_TOOLS = ('bandit', 'semgrep', 'gitleaks', 'trufflehog', 'osv-scanner', 'eslint', 'typescript', 'lizard')


@_isolated_preflight_test
def test_installed_scanner_failure_families_preflight_without_changing_truth():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_authoritative_scanner_truth_v62 import _failure_reason
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    from nico.comprehensive_spanish_publication_preflight_v93 import (
        inspect_spanish_canonical_publication_preflight,
        install_spanish_publication_preflight_v93,
    )
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME['same_terminal_report_authority_as_production'] is True
    assert renderer._scanner_stages.__module__ == 'nico.comprehensive_scanner_stage_wording_v1'
    install_spanish_publication_preflight_v93()
    for tool in _TOOLS:
        for field in ('timed_out_tools', 'unavailable_tools', 'failed_tools', None):
            live = {field: [tool]} if field else {}
            reason = _failure_reason(tool, live)
            record = {'scanner_name': tool, 'status': 'failed' if field else 'missing',
                      'completed': False, 'verified': False, 'exact_commit_match': False,
                      'artifact_retained': False, 'finding_count': 0, 'failure_reason': reason}
            canonical = {'report_language': 'es-MX', 'scanner_execution_records': [record],
                         'human_review_required': True, 'client_delivery_allowed': False}
            original = deepcopy(canonical)
            stage = renderer._scanner_stages(canonical)[0]
            assert stage['unavailable'] == [tool + ': ' + reason]
            assert stage['status'] == 'review_required'
            before = deepcopy(stage)
            report = {**canonical, 'stage_summaries': [stage]}
            manifest = inspect_spanish_canonical_publication_preflight(report)
            assert manifest['status'] == 'complete', (tool, field, manifest)
            localized = _localize_tree(report)
            translated = localized['stage_summaries'][0]['unavailable'][0]
            assert translated != stage['unavailable'][0]
            assert translated.startswith(tool + ': ') and tool in translated
            assert 'detalle técnico original:' not in translated
            expected = {
                'timed_out_tools': 'agotó el tiempo',
                'unavailable_tools': 'no estuvo disponible',
                'failed_tools': 'falló',
                None: 'no conservó',
            }
            assert expected[field] in translated, (tool, field, translated)
            assert localized['scanner_execution_records'] == original['scanner_execution_records']
            assert localized['human_review_required'] is True
            assert localized['client_delivery_allowed'] is False
            assert canonical == original and stage == before


@_isolated_preflight_test
def test_installed_scanner_missing_reason_fallback_remains_incomplete():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    for tool in _TOOLS:
        record = {'scanner_name': tool, 'completed': False, 'status': 'missing'}
        canonical = {'scanner_execution_records': [record]}
        original = deepcopy(canonical)
        stage = renderer._scanner_stages(canonical)[0]
        source = stage['unavailable'][0]
        assert source == tool + ': scanner execution evidence incomplete'
        translated = _translate_presentation_field(source, 'unavailable')
        assert tool in translated and translated != source
        assert stage['status'] == 'review_required' and canonical == original


@_isolated_preflight_test
def test_unknown_scanner_prose_is_not_accepted_by_new_translation_contract():
    from nico.api import final_report_worker_bootstrap
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    for source in (
        'bandit: bandit failed during the exact-run scanner execution. The customer approved delivery.',
        'bandit: bandit completed during the exact-run scanner execution.',
        'bandit: semgrep failed during the exact-run scanner execution.',
        'bandit: The unknown retained failure proves a verified production outage.',
    ):
        with pytest.raises(ValueError):
            _translate_presentation_field(source, 'unavailable')


@_isolated_preflight_test
def test_custom_scanner_detail_is_not_accepted_by_new_translation_helper():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    from nico.spanish_scanner_unavailable_contracts import translate_scanner_unavailable_contract
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    reason = 'Owned parser failed at src/owned.py:17; exit_code=2'
    record = {'scanner_name': 'bandit', 'status': 'partial', 'completed': False,
              'failure_reason': reason, 'artifact_sha256': 'a' * 64,
              'exact_commit_match': True, 'finding_count': 3}
    canonical = {'scanner_execution_records': [record]}
    before = deepcopy(canonical)
    stage = renderer._scanner_stages(canonical)[0]
    source = stage['unavailable'][0]
    assert source == 'bandit: ' + reason
    assert translate_scanner_unavailable_contract(source) is None
    with pytest.raises(ValueError):
        _translate_presentation_field(source, 'unavailable')
    assert canonical == before and stage['status'] == 'review_required'


@_isolated_preflight_test
def test_successful_command_status_does_not_claim_complete_evidence():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    for status in ('complete', 'completed', 'completed_clean', 'completed_with_findings', 'success', 'passed'):
        canonical = {'scanner_execution_records': [{'scanner_name': 'bandit', 'status': status,
            'completed': False, 'exact_commit_match': False, 'artifact_retained': False}]}
        before = deepcopy(canonical)
        stage = renderer._scanner_stages(canonical)[0]
        assert stage['unavailable'] == ['bandit: scanner execution evidence incomplete']
        translated = _translate_presentation_field(stage['unavailable'][0], 'unavailable')
        assert translated != stage['unavailable'][0]
        assert 'execution=' + status in stage['evidence'][0]
        assert stage['status'] == 'review_required' and canonical == before


@_isolated_preflight_test
def test_unknown_scanner_state_remains_rejected():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    from nico.spanish_scanner_unavailable_contracts import translate_scanner_unavailable_contract
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    canonical = {'scanner_execution_records': [{'scanner_name': 'eslint', 'status': 'future_unknown_state',
        'completed': False, 'failure_reason': 'Owned technical detail'}]}
    before = deepcopy(canonical)
    stage = renderer._scanner_stages(canonical)[0]
    with pytest.raises(ValueError, match='missing Spanish scanner status translation'):
        translate_scanner_unavailable_contract(stage['evidence'][0])
    with pytest.raises(ValueError, match='missing Spanish scanner status translation'):
        _translate_presentation_field(stage['evidence'][0], 'evidence')
    assert canonical == before


@_isolated_preflight_test
def test_real_scanner_summary_preserves_nonzero_counts_and_approval_boundary():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    from nico.spanish_scanner_unavailable_contracts import translate_scanner_unavailable_contract
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    canonical = {'scanner_execution_records': [{'scanner_name': 'bandit', 'completed': True},
        {'scanner_name': 'semgrep', 'completed': False}],
        'canonical_scanner_finding_register': {'totals': {'material': 2, 'review_required': 3, 'raw': 5}}}
    before = deepcopy(canonical)
    summary = renderer._scanner_stages(canonical)[0]['summary']
    translated = _translate_presentation_field(summary, 'summary')
    assert '1/2' in translated
    assert '3 pendientes de revisión humana de 5 candidatos sin procesar' in translated
    assert 'Hallazgos materiales confirmados: 2.' in translated
    assert 'no equivale a la aprobación de candidatos' in translated
    assert canonical == before
    altered = summary.replace('does not equal candidate approval', 'equals candidate approval')
    assert translate_scanner_unavailable_contract(altered) is None
    with pytest.raises(ValueError):
        _translate_presentation_field(altered, 'summary')


@_isolated_preflight_test
def test_scanner_evidence_counts_and_payload_states_translate_without_rewriting_source():
    from nico.api import final_report_worker_bootstrap
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    assert final_report_worker_bootstrap.FINAL_REPORT_WORKER_RUNTIME
    for payload_state, updates in (
        ('retained', {'raw_artifact_retention_complete': True}),
        ('count-only', {'finding_count': 5}),
        ('unavailable', {}),
    ):
        record = {'scanner_name': 'eslint', 'status': 'completed_with_findings',
                  'completed': False, 'exact_commit_match': True, 'artifact_sha256': 'a' * 64,
                  **updates}
        # A count-only summary determines payload_state too; the unavailable
        # branch has no retained counts, while the others exercise nonzero values.
        raw = 0 if payload_state == 'unavailable' else 5
        material, review = (0, 0) if payload_state == 'unavailable' else (2, 3)
        canonical = {'scanner_execution_records': [record], 'canonical_scanner_finding_register': {
            'summary_by_scanner': {'eslint': {'raw': raw, 'material': material, 'review_required': review}}}}
        before = deepcopy(canonical)
        source = renderer._scanner_stages(canonical)[0]['evidence'][0]
        assert source.endswith('raw candidate payload=' + payload_state)
        translated = _translate_presentation_field(source, 'evidence')
        assert translated != source
        assert 'eslint' in translated and 'completed_with_findings' in translated
        assert '=' + str(material) + ';' in translated
        assert '=' + str(review) + ';' in translated and '=' + str(raw) + ';' in translated
        assert canonical == before



@_isolated_preflight_test
def test_registered_exact_scanner_translation_keeps_precedence():
    from nico.comprehensive_current_report_truth_parity_v1 import install_comprehensive_current_report_truth_parity_v1
    from nico.spanish_scanner_unavailable_contracts import translate_scanner_unavailable_contract
    install_comprehensive_current_report_truth_parity_v1()
    source = 'typescript: typescript did not retain a complete exact-SHA scanner record.'
    assert translate_scanner_unavailable_contract(source) == (
        'typescript: TypeScript no conservó un registro completo del analizador para el SHA exacto.')
