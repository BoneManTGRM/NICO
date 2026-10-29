from copy import deepcopy
import pytest
from nico.candidate_investigation_pipeline_v1 import capture_sources, investigate_register, display_investigation
from tests.test_candidate_source_observations_v1 import row, SHA

SCOPE = {'run_id': 'synthetic', 'repository': 'example/repo', 'commit_sha': SHA, 'customer_id': 'c', 'project_id': 'p'}


def register():
    return {'findings': [row(), row(candidate_id='B', rule_id='B105'), row(candidate_id='C', source_commit_sha='b'*40)]}


def test_capture_and_persisted_projection_are_read_only_and_repeatable():
    source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE)
    reg = register(); before = deepcopy(reg)
    result = investigate_register(reg, source, SCOPE)
    assert reg == before and result['bounded_rule_analysis_completed'] == 1
    assert result['candidate_count'] == 3
    reg['candidate_investigation'] = result
    frozen = deepcopy(reg)
    assert display_investigation(reg, SCOPE) == display_investigation(reg, SCOPE)
    assert reg == frozen
    assert display_investigation(reg, SCOPE)['completed_count'] == 1
    assert 'permitted' not in str(source)
    assert source['observations']['example.py']['source_binding']['origin'] == 'snapshot_decoded_text'
    assert 'blob_oid' not in source['observations']['example.py']['source_binding']


@pytest.mark.parametrize('field', list(SCOPE))
def test_stale_cross_scope_capture_and_packet_fail_closed(field):
    source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE)
    wrong = {**SCOPE, field: 'wrong'}
    result = investigate_register(register(), source, wrong)
    assert result['bounded_rule_analysis_completed'] == 0
    reg = register(); reg['candidate_investigation'] = investigate_register(reg, source, SCOPE)
    assert display_investigation(reg, wrong)['available'] is False


def test_timeout_and_unsupported_sources_retain_population():
    ticks = iter([0, 6, 7])
    source = capture_sources({'example.py': 'assert permitted\n', 'file.ts': 'ignored'}, SCOPE, clock=lambda: next(ticks))
    assert source['unavailable_reasons']['source_time_budget'] == 1
    assert not source['observations']
    ticks = iter([0, 3, 4, 5])
    result = investigate_register(register(), source, SCOPE, clock=lambda: next(ticks))
    assert result['candidate_count'] == 3 and result['bounded_rule_analysis_completed'] == 0
    assert result['unresolved_reasons'] == {'investigation_budget_exhausted': 3}


def test_malformed_failed_observation_is_unresolved_and_changed_candidate_invalidates_packet():
    source = capture_sources({'example.py': 'assert (\n'}, SCOPE)
    reg = register(); result = investigate_register(reg, source, SCOPE)
    assert result['bounded_rule_analysis_completed'] == 0
    reg['candidate_investigation'] = result
    reg['findings'][0]['line'] = 99
    assert display_investigation(reg, SCOPE)['available'] is False


def test_real_scoring_provider_attaches_investigation_without_score_or_raw_candidate_change(monkeypatch):
    from nico import comprehensive_native_providers as legacy, comprehensive_native_providers_v5 as v5
    from tests.test_comprehensive_native_providers_v2 import _context, _repo, _scan
    context = _context(); repo = _repo()
    monkeypatch.setattr(legacy, '_repo', lambda _: repo)
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: {})
    baseline = v5.canonical_scoring_provider(context)
    repo['candidate_source_observations'] = capture_sources({'example.py': 'assert permitted\n'}, context)
    result = v5.canonical_scoring_provider(context)
    a, b = baseline['assessment'], result['assessment']
    assert a['technical_score'] == b['technical_score']
    assert a['canonical_scanner_finding_register']['findings'] == b['canonical_scanner_finding_register']['findings']
    assert 'candidate_investigation' in b['canonical_scanner_finding_register']
    assert result['client_delivery_allowed'] is False


@pytest.mark.parametrize('bad', ['bad', [], 42, {'packets': None}])
def test_malformed_persisted_metadata_keeps_review_projection_available(bad):
    from nico.comprehensive_review_work_v2 import review_work_projection
    reg = register(); reg.update(candidate_record_count=3, candidate_investigation=bad)
    reg['review_workload_clusters'] = [{'cluster_id': 'synthetic', 'candidate_ids': ['A', 'B', 'C']}]
    identity = {**SCOPE, 'evidence_ledger_id': 'synthetic-ledger'}
    c = {'identity': identity, 'assessment': {'canonical_scanner_finding_register': reg}}
    record = {'identity': identity, 'stage_results': {'final_comprehensive_report_generation': {'report_package': {'json': c}}}}
    result = review_work_projection(record)
    assert result['review_assistance']['source_investigation']['available'] is False
    assert len(result['candidates']) == 3 and result['client_delivery_allowed'] is False


def test_malformed_packet_and_reference_fail_closed():
    reg = register(); source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE)
    reg['candidate_investigation'] = investigate_register(reg, source, SCOPE)
    reg['candidate_investigation']['packets'][0] = None
    assert display_investigation(reg, SCOPE)['available'] is False
    reg['candidate_investigation'] = investigate_register(reg, source, SCOPE)
    reg['candidate_investigation']['packets'][0]['source_reference'] = 'bad'
    assert display_investigation(reg, SCOPE)['available'] is False
