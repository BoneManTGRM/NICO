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

@pytest.mark.parametrize('reference', [{}, {'source_sha256': 'bad', 'line': 1},
    {'source_sha256': 'a' * 64}, {'source_sha256': 'a' * 64, 'line': 2},
    {'source_sha256': 'a' * 64, 'line': True}])
def test_missing_or_mismatched_source_reference_cannot_claim_completed_analysis(reference):
    reg = register()
    source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE)
    reg['candidate_investigation'] = investigate_register(reg, source, SCOPE)
    assert display_investigation(reg, SCOPE)['completed_count'] == 1
    reg['candidate_investigation']['packets'][0]['source_reference'] = reference
    before = deepcopy(reg)
    result = display_investigation(reg, SCOPE)
    assert result['completed_count'] == 0
    assert result['packets'][0]['completed'] is False
    assert result['packets'][0]['reason'] == 'retained_observation_invalid'
    assert reg == before


def test_capture_diagnostics_are_count_only_and_preserve_failure_visibility():
    source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE)
    source['unavailable_reasons'] = {'source_time_budget': 7, 'private/path.py': 9,
                                     'source_size_budget': 'secret', 'observation_size_budget': True}
    result = investigate_register(register(), source, SCOPE)
    assert result['source_capture'] == {'scope_valid': True, 'observation_count': 1,
        'parsed_observation_count': 1, 'unavailable_reasons': {'source_time_budget': 7}}
    assert 'private/path.py' not in str(result)
    assert 'secret' not in str(result)
    stale = investigate_register(register(), source, {**SCOPE, 'commit_sha': 'wrong'})
    assert stale['source_capture'] == {'scope_valid': False, 'observation_count': 0,
        'parsed_observation_count': 0, 'unavailable_reasons': {}}


def test_capture_clock_starts_at_invocation_not_acquisition_time():
    # A large absolute clock value models acquisition completed long beforehand.
    ticks = iter([10000, 10000, 10000.01])
    source = capture_sources({'example.py': 'assert permitted\n'}, SCOPE, clock=lambda: next(ticks))
    assert source['observations']['example.py']['status'] == 'parsed'
    assert investigate_register(register(), source, SCOPE)['bounded_rule_analysis_completed'] == 1


def test_one_parse_crossing_deadline_can_leave_zero_observations(monkeypatch):
    import nico.candidate_investigation_pipeline_v1 as pipeline
    ticks = iter([0, 0, 6, 6])
    source = capture_sources({'a.py': 'assert permitted\n', 'example.py': 'assert permitted\n'},
                             SCOPE, clock=lambda: next(ticks))
    assert source['observations'] == {}
    assert source['unavailable_reasons'] == {'source_time_budget': 2}
    result = investigate_register(register(), source, SCOPE)
    assert result['bounded_rule_analysis_completed'] == 0
    assert result['source_capture']['observation_count'] == 0
    assert result['source_capture']['unavailable_reasons'] == {'source_time_budget': 2}


def test_observation_output_cap_can_starve_later_candidate_source(monkeypatch):
    import nico.candidate_investigation_pipeline_v1 as pipeline
    original = pipeline.observe_python_source
    def observed(data, **kwargs):
        value = original(data, **kwargs)
        if kwargs['path'] == 'a.py':
            value['synthetic_size_padding'] = 'x' * (2 * 1024 * 1024 - 600)
        return value
    monkeypatch.setattr(pipeline, 'observe_python_source', observed)
    source = capture_sources({'example.py': 'assert permitted\n', 'a.py': 'assert permitted\n'},
                             SCOPE, clock=lambda: 0)
    assert list(source['observations']) == ['a.py']
    assert source['unavailable_reasons'] == {'observation_size_budget': 1}
    assert investigate_register(register(), source, SCOPE)['bounded_rule_analysis_completed'] == 0
