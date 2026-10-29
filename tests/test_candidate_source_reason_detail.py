from copy import deepcopy
import pytest
from nico.candidate_investigation_pipeline_v1 import VERSION, capture_sources, investigate_register, display_investigation
from nico.candidate_source_reason_detail_v1 import LABELS, VERSION as DETAIL_VERSION
from tests.test_candidate_investigation_pipeline_v1 import SCOPE
from tests.test_candidate_source_observations_v1 import row


def run(observations, *, candidate=None, scope=SCOPE):
    register={'findings':[candidate or row()]}
    retained={'artifact_schema':VERSION,'scope':dict(SCOPE),'observations':observations,
              'unavailable_reasons':{'source_time_budget':42,'observation_size_budget':17}}
    before=deepcopy((register,retained))
    packet=investigate_register(register,retained,scope)
    assert (register,retained)==before
    register['candidate_investigation']=packet
    return packet,display_investigation(register,scope),register

@pytest.mark.parametrize('observations,code',[
    ({},'source_not_retained'),(None,'capture_observations_invalid'),([], 'capture_observations_invalid'),
    ({'example.py':{}},'observation_status_unknown'),
    ({'example.py':{'status':['PRIVATE_SENTINEL']}},'observation_status_unknown'),
    ({'example.py':{'status':'PRIVATE_SENTINEL'}},'observation_status_unknown'),
    ({'example.py':{'status':'source_parse_unavailable'}},'observation_parse_unavailable'),
    ({'example.py':{'status':'source_size_limit'}},'observation_size_limit'),
    ({'example.py':{'status':'source_binding_invalid'}},'observation_binding_invalid'),
    ({'example.py':{'status':'source_parse_unavailable','source_binding':{'repository':'foreign'}}},'observation_scope_conflict'),
])
def test_supported_details_preserve_legacy_reason_and_do_not_infer_budget(observations,code):
    record,view,_=run(observations)
    assert record['unresolved_reasons']==view['unresolved_reasons']=={'source_parse_unavailable':1}
    assert record['source_availability_counts']==view['source_availability_counts']=={code:1}
    assert view['completed_count']==0 and record['candidate_count']==1
    assert record['human_review_required'] and not record['client_delivery_allowed']
    assert 'PRIVATE_SENTINEL' not in str((record,view))
    assert 'source_time_budget' not in view['source_availability_counts']


def test_invalid_path_does_not_request_or_claim_source():
    _,view,_=run({},candidate=row(source_path='../outside.py'))
    assert view['source_availability_counts']=={'candidate_path_unusable':1}
    assert view['packets'][0]['source_path'] is None

@pytest.mark.parametrize('field',list(SCOPE))
def test_foreign_capture_scope_cannot_support_detail(field):
    record,view,_=run({},scope={**SCOPE,field:'foreign'})
    assert record['unresolved_reasons']=={'source_scope_unavailable_or_stale':1}
    assert not record['source_availability_counts'] and not view['source_availability_counts']


def test_wrong_candidate_commit_cannot_support_detail():
    record,_,_=run({},candidate=row(exact_commit_sha='b'*40))
    assert record['unresolved_reasons']=={'source_identity_mismatch':1}
    assert not record['source_availability_counts']

@pytest.mark.parametrize('detail',[None,{}, {'artifact_schema':'foreign','code':'source_not_retained'},
                                 {'artifact_schema':DETAIL_VERSION,'code':'PRIVATE_SENTINEL'}])
def test_legacy_unknown_details_and_aggregate_claims_are_not_inferred(detail):
    record,_,register=run({})
    if detail is None:record['packets'][0].pop('source_availability_detail')
    else:record['packets'][0]['source_availability_detail']=detail
    record['source_availability_counts']={'source_not_retained':99999}
    view=display_investigation(register,SCOPE)
    assert view['source_availability_counts']=={'not_recorded':1}
    assert 'PRIVATE_SENTINEL' not in str(view)
    register['findings'][0]['line']=2
    assert display_investigation(register,SCOPE)['available'] is False

@pytest.mark.parametrize('spanish',[False,True])
def test_bound_report_discloses_detail_counts_bilingually(spanish):
    from nico.report_preview_labels_v1 import retained_coverage_disclosures
    _,_,register=run({})
    context={'identity':dict(SCOPE),'assessment':{'canonical_scanner_finding_register':register}}
    before=deepcopy(context)
    text='\n'.join(retained_coverage_disclosures(context,spanish=spanish))
    assert LABELS['source_not_retained'][int(spanish)]+': 1.' in text
    assert ('causa presupuestaria' if spanish else 'budget cause') in text
    assert context==before
    context['identity']['run_id']='foreign'
    assert LABELS['source_not_retained'][int(spanish)] not in '\n'.join(retained_coverage_disclosures(context,spanish=spanish))


def test_production_count_shape_keeps_all_candidates_and_known_completed_subset():
    source=capture_sources({'example.py':'assert permitted\n'},SCOPE)
    rows=[row(candidate_id=f'C{i}') for i in range(899)]
    rows += [row(candidate_id=f'M{i}',source_path=f'missing/{i}.py') for i in range(593)]
    # The remaining 189 are deliberately unsupported synthetic cases, not a
    # claim to reproduce the real run's individual source evidence.
    rows += [row(candidate_id=f'U{i}',category='dependency') for i in range(189)]
    register={'findings':rows};before=deepcopy(rows)
    result=investigate_register(register,source,SCOPE,clock=lambda:0)
    register['candidate_investigation']=result
    view=display_investigation(register,SCOPE)
    assert view['candidate_count']==1681 and view['completed_count']==899
    assert sum(view['unresolved_reasons'].values())==782
    assert view['source_availability_counts']=={'source_not_retained':593}
    assert rows==before


@pytest.mark.parametrize('observations', [{}, {'example.py':{'status':'source_parse_unavailable'}}])
def test_foreign_candidate_repository_does_not_attribute_capture_evidence(observations):
    record,view,_=run(observations,candidate=row(source_repository='foreign/repo'))
    assert record['unresolved_reasons']=={'source_parse_unavailable':1}
    assert 'source_availability_detail' not in record['packets'][0]
    assert view['source_availability_counts']=={'not_recorded':1}
    assert view['completed_count']==0


def test_final_enrichment_retains_missing_source_detail_without_new_disposition():
    from tests.test_candidate_investigation_finalization_v1 import inputs
    from nico.candidate_investigation_finalization_v1 import final_investigation_scope, finalize_investigation
    context,canonical=inputs()
    stages=context['prior_stage_results']
    capture=stages['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations']
    original=stages['evidence_reconciliation_and_scoring']['assessment']['canonical_scanner_finding_register']
    original['findings'][0]['source_path']='missing.py'
    canonical['assessment']['canonical_scanner_finding_register']['findings'][0]['source_path']='missing.py'
    original['candidate_investigation']=investigate_register(original,capture,SCOPE)
    before=deepcopy(context)
    with final_investigation_scope(context):
        result=finalize_investigation(canonical)
    view=display_investigation(result['assessment']['canonical_scanner_finding_register'],SCOPE)
    assert view['available'] and view['completed_count']==0
    assert view['source_availability_counts']=={'source_not_retained':1}
    assert context==before


def _installed_detail_worker(locale):
    import base64,io
    from pypdf import PdfReader
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.candidate_investigation_finalization_v1 import final_investigation_scope
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    package={'json':_fixed_status(locale)['reports']['json']}
    identity=package['json']['identity']
    register=_install_finalized_scanner_register(package['json'])
    register['findings'][0].update(exact_commit_sha=identity['commit_sha'],source_path='missing.py',
        path='missing.py',rule_id='B101',line=1,evidence_quality='exact_source')
    register['totals']={'raw':1,'review_required':1,'exact_source':1}
    register['summary_by_category']={'static':dict(register['totals'])}
    capture=capture_sources({},identity)
    register['candidate_investigation']=investigate_register(register,capture,identity)
    context={**identity,'prior_stage_results':{'evidence_reconciliation_and_scoring':{
        'candidate_source_observations':capture,'assessment':{'canonical_scanner_finding_register':deepcopy(register)}}}}
    before=deepcopy((context,package))
    with final_investigation_scope(context):
        result=rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    pdf=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    expected=LABELS['source_not_retained'][locale=='es-MX']+': 1.'
    # This disclosure is installed in the PDF client-summary/workload renderer.
    # Markdown/HTML retain their existing coverage; their hashes still validate.
    assert ''.join(expected.split()) in ''.join(pdf.split())
    view=display_investigation(result['json']['assessment']['canonical_scanner_finding_register'],result['json']['identity'])
    assert view['source_availability_counts']=={'source_not_retained':1}
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
    assert (context,package)==before


@pytest.mark.parametrize('locale',['en','es-MX'])
def test_installed_final_report_displays_source_detail(locale,tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    code='import sys; from tests.test_candidate_source_reason_detail import _installed_detail_worker; _installed_detail_worker(sys.argv[1])'
    result=subprocess.run([sys.executable,'-c',code,locale],cwd=root,
        env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


def test_real_capture_distinguishes_recorded_parser_unavailability_from_absence():
    capture=capture_sources({'example.py':'def broken(:\n'},SCOPE)
    assert capture['observations']['example.py']['status']=='source_parse_unavailable'
    register={'findings':[row(),row(candidate_id='missing',source_path='missing.py')]}
    original=deepcopy(register['findings'])
    register['candidate_investigation']=investigate_register(register,capture,SCOPE)
    view=display_investigation(register,SCOPE)
    assert view['source_availability_counts']=={'observation_parse_unavailable':1,'source_not_retained':1}
    assert view['completed_count']==0 and view['unresolved_reasons']=={'source_parse_unavailable':2}
    assert register['findings']==original
