from copy import deepcopy
import pytest
from nico.candidate_investigation_pipeline_v1 import capture_sources, investigate_register, display_investigation
from nico.candidate_investigation_finalization_v1 import final_investigation_scope, finalize_investigation
from tests.test_candidate_investigation_pipeline_v1 import SCOPE
from tests.test_candidate_source_observations_v1 import row


def inputs(scope=SCOPE):
    capture = capture_sources({'example.py': 'assert permitted\n'}, scope)
    register = {'findings': [row(source_path='./example.py', exact_commit_sha=scope['commit_sha'])]}
    register['candidate_investigation'] = investigate_register(register, capture, scope)
    context = {**scope, 'prior_stage_results': {
        'repository_and_delivery_evidence': {'repository_evidence': {'candidate_source_observations': capture}},
        'evidence_reconciliation_and_scoring': {'assessment': {'canonical_scanner_finding_register': register}}}}
    canonical = {'identity': dict(scope), 'assessment': {'canonical_scanner_finding_register': deepcopy(register)}}
    canonical['assessment']['canonical_scanner_finding_register']['findings'][0]['source_path'] = 'example.py'
    return context, canonical


def test_trusted_finalization_reanalyzes_normalized_rows_without_rebinding_original_hashes():
    context, canonical = inputs()
    before = deepcopy((context, canonical))
    register = canonical['assessment']['canonical_scanner_finding_register']
    assert not display_investigation(register, SCOPE)['available']  # reproduced old lifecycle failure
    with final_investigation_scope(context):
        final = finalize_investigation(canonical)
        again = finalize_investigation(canonical)
    retained = final['assessment']['canonical_scanner_finding_register']
    assert display_investigation(retained, SCOPE)['completed_count'] == 1
    assert retained['candidate_investigation'] == register['candidate_investigation']
    assert retained['findings'] == register['findings']
    assert again == final
    assert (context, canonical) == before
    assert finalize_investigation(canonical) is canonical  # GET/export cannot refresh stale packets


@pytest.mark.parametrize('field,value', [('candidate_id','other'),('source_path','other.py'),('path','other.py'),('line',2),
    ('line',True),('rule_id','B404'),('exact_commit_sha','b'*40),('source_commit_sha','b'*40),
    ('source_repository','other/repo'),('category','secret'),('evidence_quality','count_only'),
    ('raw_fingerprint','different'),('evidence','changed scanner claim')])
def test_changed_final_candidate_is_not_revalidated(field, value):
    context, canonical = inputs()
    canonical['assessment']['canonical_scanner_finding_register']['findings'][0][field] = value
    with final_investigation_scope(context):
        final = finalize_investigation(canonical)
    register = final['assessment']['canonical_scanner_finding_register']
    assert register['final_candidate_investigation']['reason'] == 'candidate_analysis_identity_changed'
    assert not display_investigation(register, SCOPE)['available']


@pytest.mark.parametrize('damage', ['scope','capture','original','packet','count','final_scope'])
def test_stale_or_missing_originals_fail_closed(damage):
    context, canonical = inputs()
    stages = context['prior_stage_results']
    original = stages['evidence_reconciliation_and_scoring']['assessment']['canonical_scanner_finding_register']
    if damage == 'scope': context['customer_id'] = 'other'
    elif damage == 'capture': stages['repository_and_delivery_evidence']['repository_evidence'].clear()
    elif damage == 'original': original['findings'][0]['line'] = 3
    elif damage == 'packet': original['candidate_investigation']['packets'][0]['candidate_input_sha256'] = 'f'*64
    elif damage == 'count': canonical['assessment']['canonical_scanner_finding_register']['findings'].append(row(candidate_id='extra'))
    else: canonical['identity']['run_id'] = 'other'
    with final_investigation_scope(context):
        final = finalize_investigation(canonical)
    register = final['assessment']['canonical_scanner_finding_register']
    assert register['final_candidate_investigation']['status'] == 'unavailable'
    assert not display_investigation(register, SCOPE)['available']


def test_scope_resets_on_failure_and_repeated_finalization_has_one_analysis(monkeypatch):
    from nico import candidate_investigation_finalization_v1 as module
    context, canonical = inputs()
    calls = []
    original = module.investigate_register
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'investigate_register', counted)
    with pytest.raises(RuntimeError), final_investigation_scope(context):
        finalize_investigation(canonical)
        finalize_investigation(canonical)
        raise RuntimeError('synthetic')
    assert len(calls) == 1
    assert finalize_investigation(canonical) is canonical


def _installed_chain(language):
    from nico.api import final_report_worker_bootstrap
    from tests.test_roadmap_pdf_detail_completeness import _five_gap_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico.comprehensive_review_work_v2 import review_work_projection
    import json
    package = _five_gap_package(language)
    context, canonical = inputs(package['json']['identity'])
    totals = {'raw': 1, 'review_required': 1, 'material': 0, 'exact_source': 1, 'source_path': 0, 'payload_without_source': 0, 'count_only': 0, 'approved_or_nonblocking': 0, 'excluded_test_only': 0}
    source_register = context['prior_stage_results']['evidence_reconciliation_and_scoring']['assessment']['canonical_scanner_finding_register']
    source_register.update(candidate_record_count=1, totals=totals, summary_by_category={'static': totals}, summary_by_tool={'bandit': totals})
    source_register['review_workload_clusters'] = [{'cluster_id': 'synthetic', 'candidate_ids': [source_register['findings'][0]['candidate_id']]}]
    original = deepcopy(context['prior_stage_results']['evidence_reconciliation_and_scoring']['assessment']['canonical_scanner_finding_register'])
    package['json']['assessment']['canonical_scanner_finding_register'] = deepcopy(original)
    before = deepcopy(package)
    with final_investigation_scope(context):
        result = rebuild_client_artifacts(package)
    register = result['json']['assessment']['canonical_scanner_finding_register']
    assert register['candidate_investigation'] == original['candidate_investigation']
    assert register['findings'][0]['source_path'] == 'example.py'
    assert display_investigation(register, package['json']['identity'])['completed_count'] == 1
    exported = json.loads(json.dumps(register))
    assert display_investigation(exported, package['json']['identity'])['completed_count'] == 1
    record = {'identity': package['json']['identity'], 'stage_results': {
        'final_comprehensive_report_generation': {'report_package': result}}}
    visible = review_work_projection(record)['review_assistance']['source_investigation']
    assert visible['available'] and visible['completed_count'] == 1
    _validate_exact_artifact_hashes(result)
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert package == before


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_capture_to_final_artifact_and_ui(language, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    code = 'from tests.test_candidate_investigation_finalization_v1 import _installed_chain; import sys; _installed_chain(sys.argv[1])'
    result = subprocess.run([sys.executable, '-c', code, language], cwd=root,
        env=owned_worker_environment(root, tmp_path, os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_final_packets_remain_stale_after_subsequent_row_mutation():
    context, canonical = inputs()
    with final_investigation_scope(context):
        final = finalize_investigation(canonical)
        changed = deepcopy(canonical)
        changed['assessment']['canonical_scanner_finding_register']['findings'][0]['review_note'] = 'later enrichment'
        refused = finalize_investigation(changed)
    assert refused['assessment']['canonical_scanner_finding_register']['final_candidate_investigation']['reason'] == 'final_candidate_input_changed'
    register = final['assessment']['canonical_scanner_finding_register']
    register['findings'][0]['line'] = 99
    assert not display_investigation(register, SCOPE)['available']
    assert finalize_investigation(final) is final


def test_production_publication_supplies_retained_scope_only_during_render(monkeypatch):
    from nico import v2_production_authority as authority
    context, canonical = inputs()
    source = {'status': 'complete', 'report_package': {'json': canonical}}
    monkeypatch.setattr(authority, '_canonical_source', lambda value: (deepcopy(source), context, 0))
    monkeypatch.setattr(authority, '_inject_live_runtime_truth', lambda value, context: value)
    monkeypatch.setattr(authority, '_reassert_terminal_report_language_authority', lambda: {})
    observed = []
    def render(value):
        final = finalize_investigation(value['report_package']['json'])
        observed.append(display_investigation(final['assessment']['canonical_scanner_finding_register'], SCOPE))
        return {'report_package': {'json': final}}
    monkeypatch.setattr(authority, 'finalize_report_package', render)
    result = authority.wrap_final_report_publication(lambda context: pytest.fail('unexpected fallback'))(context)
    assert result['status'] == 'complete'
    assert observed[0]['completed_count'] == 1
    assert finalize_investigation(canonical) is canonical
