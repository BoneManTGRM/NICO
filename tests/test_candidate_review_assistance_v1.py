from copy import deepcopy

import pytest

from nico.candidate_review_assistance_v1 import build_review_assistance

SHA = 'a' * 40
SCOPE = {'run_id': 'run1', 'repository': 'BoneManTGRM/NICO', 'commit_sha': SHA}


def candidate(**extra):
    return {
        'candidate_id': 'A', 'category': 'static', 'severity': 'low',
        'source_commit_sha': SHA, 'source_provider': 'github', 'source_path': 'nico/example.py', 'line': 12,
        'evidence_quality': 'exact_source',
        'technical_triage_source_type': 'deterministic_contextual_analysis',
        'technical_triage_status': 'fresh_proposal',
        'technical_triage_model_or_version': 'nico.deterministic-contextual-triage.v2',
        'technical_triage_verdict': 'not_actionable',
        'technical_triage_confidence': 'high',
        'evidence_used': ['executable=False'],
        'technical_triage_proof_gaps': [], 'human_disposition_state': 'pending',
        **extra,
    }


def test_bound_packet_nonmutation_and_link():
    rows = [candidate()]
    before = deepcopy(rows)
    result = build_review_assistance(rows, SCOPE)
    assert rows == before
    packet = result['queue'][0]
    assert packet['recommendation'] == 'review_nonblocking_proposal'
    assert packet['source_url'] == f'https://github.com/BoneManTGRM/NICO/blob/{SHA}/nico/example.py#L12'
    assert result['new_source_investigations_performed'] == 0
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert result['score_effect'] == 'none'


@pytest.mark.parametrize('extra', [
    {'technical_triage_status': None}, {'technical_triage_status': 'future'},
    {'individual_attention_required': True}, {'review_requires_individual_attention': True},
    {'conflicting_evidence': True}, {'counterevidence_conflict': True},
    {'evidence_change_state': 'changed'}, {'review_routing_class': 'CRITICAL_ATTENTION'},
    {'source_commit_sha': 'b' * 40}, {'source_commit_sha': None},
    {'evidence_quality': 'count_only'}, {'evidence_quality': 'payload_without_source'},
    {'evidence_used': []}, {'technical_triage_proof_gaps': ['reachability']},
    {'technical_triage_proof_gaps': 'malformed'},
    {'technical_triage_source_type': 'llm'}, {'technical_triage_status': 'failed'},
    {'candidate_evidence_context_status': 'ambiguous'}, {'evidence_changed': True},
    {'technical_triage_confidence': 'low'}, {'severity': 'high'},
    {'category': 'secret'}, {'counterevidence': ['conflict']},
])
def test_uncertain_or_high_impact_never_gets_nonblocking_recommendation(extra):
    packet = build_review_assistance([candidate(**extra)], SCOPE)['queue'][0]
    assert packet['recommendation'] != 'review_nonblocking_proposal'
    assert packet['limitations']


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', 'x/../y', 'https://evil/x', 'x\\y', 'x\nY', 'javascript:alert(1)', 'data:text/html,test', 'vbscript:msgbox(1)'])
def test_unsafe_source_path_has_no_link(path):
    assert build_review_assistance([candidate(source_path=path)], SCOPE)['queue'][0]['source_url'] is None


def test_duplicate_ids_not_dropped_and_profile_cluster_not_equivalence():
    rows = [candidate(cluster_id='group'), candidate(cluster_id='group')]
    result = build_review_assistance(rows, SCOPE)
    assert result['candidate_record_count'] == 2
    assert len(result['queue']) == 2
    assert all('duplicate_candidate_identity' in p['limitations'] for p in result['queue'])
    assert result['grouping_is_disposition_equivalence'] is False


def test_residual_queue_order_and_completed_count():
    rows = [candidate(), candidate(candidate_id='B', severity='high'),
            candidate(candidate_id='C', human_disposition_state='completed')]
    result = build_review_assistance(rows, SCOPE)
    assert [p['candidate_id'] for p in result['queue']] == ['B', 'A']
    assert result['human_disposition_completed_count'] == 1
    assert result['candidate_record_count'] == 3


def test_no_raw_or_model_payload_disclosure():
    raw = 'DO_NOT_EMIT_SECRET_OR_INSTRUCTIONS'
    result = build_review_assistance([candidate(raw_output=raw, technical_triage_rationale=raw,
        model_response=raw, technical_triage_source_type='llm')], SCOPE)
    assert raw not in str(result)
    assert result['queue'][0]['recommendation'] == 'resolve_evidence_gaps'


def test_real_projection_preserves_gates_and_raw_register():
    from nico.comprehensive_review_work_v2 import review_work_projection, assert_ready_for_approval
    identity = {**SCOPE, 'evidence_ledger_id': 'ledger1'}
    canonical = {'identity': identity, 'assessment': {'canonical_scanner_finding_register': {'candidate_record_count': 1, 'findings': [candidate()], 'review_workload_clusters': [{'cluster_id': 'one', 'candidate_ids': ['A']}]}}}
    record = {'identity': identity, 'stage_results': {'final_comprehensive_report_generation': {'report_package': {'json': canonical}}}}
    before = deepcopy(record)
    projection = review_work_projection(record)
    assert projection['review_assistance']['candidate_record_count'] == 1
    assert record == before
    assert projection['client_delivery_allowed'] is False
    with pytest.raises(ValueError, match='review_work_not_ready'):
        assert_ready_for_approval(record)


@pytest.mark.parametrize('ids', [['A', 'A'], ['']])
def test_projection_rejects_ambiguous_ids_before_catalog(ids):
    from nico.comprehensive_review_work_v2 import review_work_projection
    identity = {**SCOPE, 'evidence_ledger_id': 'ledger1'}
    register = {'candidate_record_count': len(ids), 'findings': [candidate(candidate_id=i) for i in ids]}
    canonical = {'identity': identity, 'assessment': {'canonical_scanner_finding_register': register}}
    record = {'identity': identity, 'stage_results': {'final_comprehensive_report_generation': {'report_package': {'json': canonical}}}}
    with pytest.raises(ValueError, match='review_work_candidate_identity_invalid'):
        review_work_projection(record)


@pytest.mark.parametrize('changes', [{'evidence_change_state': 'changed'}, {'conflicting_evidence': True}, {'review_requires_individual_attention': True}])
def test_projection_respects_existing_individual_review(changes):
    from nico.comprehensive_review_work_v2 import review_work_projection
    identity = {**SCOPE, 'evidence_ledger_id': 'ledger1'}
    register = {'candidate_record_count': 1, 'findings': [candidate(**changes)], 'review_workload_clusters': [{'cluster_id': 'one', 'candidate_ids': ['A']}]}
    canonical = {'identity': identity, 'assessment': {'canonical_scanner_finding_register': register}}
    record = {'identity': identity, 'stage_results': {'final_comprehensive_report_generation': {'report_package': {'json': canonical}}}}
    projection = review_work_projection(record)
    assert projection['candidates'][0]['individual_attention_required'] is True
    assert projection['review_assistance']['queue'][0]['recommendation'] != 'review_nonblocking_proposal'


@pytest.mark.parametrize('extra', [
    {'technical_triage_model_or_version': None}, {'technical_triage_model_or_version': 'unknown'},
    {'evidence_used': ['']}, {'evidence_used': [None]}, {'evidence_used': [{}]},
    {'source_repository': 'other/repository'},
])
def test_incomplete_or_foreign_provenance_remains_unresolved(extra):
    packet = build_review_assistance([candidate(**extra)], SCOPE)['queue'][0]
    assert packet['recommendation'] == 'resolve_evidence_gaps'
    assert packet['limitations']


def test_fingerprint_binds_run_source_and_evidence_without_leaking_content():
    baseline = build_review_assistance([candidate()], SCOPE)['queue'][0]['input_sha256']
    assert build_review_assistance([candidate()], {**SCOPE, 'run_id': 'run2'})['queue'][0]['input_sha256'] != baseline
    assert build_review_assistance([candidate(evidence_used=['different'])], SCOPE)['queue'][0]['input_sha256'] != baseline
    assert build_review_assistance([candidate(source_commit_sha='b' * 40)], SCOPE)['queue'][0]['input_sha256'] != baseline


@pytest.mark.parametrize('provider', [None, 'gitlab', 'unknown'])
def test_never_guesses_provider_source_link(provider):
    assert build_review_assistance([candidate(source_provider=provider)], SCOPE)['queue'][0]['source_url'] is None


def test_missing_run_identity_cannot_support_nonblocking_proposal():
    result = build_review_assistance([candidate()], {k: v for k, v in SCOPE.items() if k != 'run_id'})
    assert result['queue'][0]['recommendation'] == 'resolve_evidence_gaps'
    assert 'run_scope_unverified' in result['queue'][0]['limitations']
