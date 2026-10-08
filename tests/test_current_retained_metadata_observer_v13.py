"""Owned projection controls; these objects are not production evidence."""
import copy
import json
import logging

import pytest
from starlette.responses import Response

from nico import current_retained_metadata_observer_v13 as observer
from nico.report_delivery_timing_v1 import report_delivery_timing


@pytest.fixture
def owned():
    identity={'run_id':observer.RUN,'repository':observer.REPOSITORY,'commit_sha':observer.TARGET,
              'customer_id':'owned_fixture_customer','project_id':'owned_fixture_project'}
    # Deliberately synthetic scores. Never substitute them for retained1279.
    assessment={'technical_score':91,'evidence_adjusted_score':86,
                'canonical_evidence_adjusted_score':86,
                'score_contract':{'version':'nico.comprehensive-native-providers.v5',
                                  'incomplete_analyzer_penalty':4,'incomplete_analyzers':['typescript']},
                'scoring_weights':[{'section_id':'static_analysis','weight':0.15,
                                    'technical_score':80,'assurance_factor':0.85,'included':True}],
                'sections':[{'id':'static_analysis','score_value':80,'assurance_status':'unavailable'}],
                'scanner_execution_records':[{'tool':'typescript','status':'unavailable',
                    'execution_observed_for_this_report':True,
                    'failure_reason':'typescript requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local commands.',
                    'verification_deficits':['scanner_verification_not_proven','complete_artifact_capture_not_proven'],
                    'raw_findings_embedded':False,'findings':[]}]}
    record={'identity':identity,'terminal':True,'revision':7,'stage_results':{
        'evidence_reconciliation_and_scoring':{'assessment':copy.deepcopy(assessment)}}}
    package={'json':{'identity':copy.deepcopy(identity),'assessment':copy.deepcopy(assessment)},
             'canonical_truth_sha256':'a'*64,'pdf_sha256':'b'*64}
    response=Response(b'%PDF-owned-unit-object',media_type='application/pdf',headers={
        'X-NICO-Frozen-Source-Artifact':'true','X-NICO-Run-ID':observer.RUN,
        'X-NICO-Commit-SHA':observer.TARGET,'X-NICO-Report-Language':'en',
        'X-NICO-Assessment-Rerun':'false','X-NICO-Canonical-Truth-SHA256':'a'*64,
        'X-NICO-PDF-SHA256':'b'*64,'X-NICO-Approval-Status':'pending_review',
        'X-NICO-Client-Delivery-Allowed':'false'})
    return record,package,response


def messages(caplog):
    return [r.getMessage().split('=',1)[1] for r in caplog.records
            if r.getMessage().startswith('NICO_CURRENT_RETAINED_METADATA=')]


def test_owned_projection_truth_and_source_objects_unchanged(owned,caplog):
    record,package,response=owned
    before=copy.deepcopy((record,package)); body=response.body; headers=dict(response.headers)
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
            observer.observe_validated_retained_pdf(record,package,'en',response)
    captured=messages(caplog);assert len(captured)==1
    value=json.loads(captured[0]);assert value['projection']['retained_report']['scores']['technical_score']==91
    assert value['projection']['typed_assessment_agreement']['evidence_adjusted_score'] is True
    ts=value['projection']['typescript']['observations'][0]
    assert ts['retained_execution_observed_claim'] is True
    assert ts['execution_observed_by_inventory_rule'] is False
    assert ts['source_literal_classification']=='project_command_policy_disabled'
    assert value['raw_artifact_or_native_execution_verified'] is False
    assert value['http_transfer_or_browser_completion_inferred'] is False
    assert (record,package)==before and response.body==body and dict(response.headers)==headers
    assert len(captured[0].encode())<=observer.OUTPUT_LIMIT


@pytest.mark.parametrize('change',['run','source','tenant','pdf','truth','locale','failed_response','not_frozen'])
def test_wrong_binding_or_failed_builder_emits_nothing(owned,caplog,change):
    record,package,response=owned
    if change=='run':record['identity']['run_id']='comprun_'+'c'*32
    elif change=='source':package['json']['identity']['commit_sha']='c'*40
    elif change=='tenant':package['json']['identity']['customer_id']='different_owned_customer'
    elif change=='pdf':response.headers['X-NICO-PDF-SHA256']='c'*64
    elif change=='truth':response.headers['X-NICO-Canonical-Truth-SHA256']='c'*64
    elif change=='locale':response.headers['X-NICO-Report-Language']='es-MX'
    elif change=='failed_response':response.status_code=403
    elif change=='not_frozen':response.headers['X-NICO-Frozen-Source-Artifact']='false'
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
    assert messages(caplog)==[]


def test_no_active_route_context_emits_nothing(owned,caplog):
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        observer.observe_validated_retained_pdf(owned[0],owned[1],'en',owned[2])
    assert messages(caplog)==[]


def test_owned_tool_version_components_are_retained(owned,caplog):
    record,package,response=owned
    row=package['json']['assessment']['scanner_execution_records'][0]
    row['scanner_tool_version']='Version 5.9.3'
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
    value=json.loads(messages(caplog)[0])
    rows=value['projection']['typescript']['observations']
    retained=next(row for row in rows if row['origin']=='retained_assessment')
    scoring=next(row for row in rows if row['origin']=='score_assessment')
    assert retained['tool_version_components']==[5,9,3]
    assert scoring['tool_version_components'] is None


def test_private_freeform_and_environment_values_are_not_emitted(owned,caplog,monkeypatch):
    record,package,response=owned
    canary='OWNED_SECRET_CANARY_never-log-this-body'
    assessment=package['json']['assessment']
    assessment.update(private_body=canary,technical_score=canary,score_contract={'version':canary})
    row=assessment['scanner_execution_records'][0]
    row.update(failure_reason=canary,execution_provenance={'private':canary},findings=[{'source':canary}])
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA',canary)
    monkeypatch.setenv('RAILWAY_DEPLOYMENT_ID',canary)
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
    raw=messages(caplog);assert len(raw)==1 and canary not in raw[0]
    result=json.loads(raw[0]);assert result['projection']['retained_report']['scores']['technical_score'] is None
    assert result['reader_release'] is None and result['reader_deployment'] is None


def test_projection_refusal_is_closed_and_does_not_change_response(owned,caplog):
    record,package,response=owned; body=response.body
    package['json']['assessment']['sections']=[{'id':'static_analysis'}]*49
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
    raw=messages(caplog);assert len(raw)==1
    assert json.loads(raw[0])=={'schema':'nico.current-retained-metadata.v13',
        'outcome':'observation_unavailable','run_id':observer.RUN,
        'reason_code':'bounded_numeric_projection_unavailable'}
    assert response.body==body


def test_logger_failure_preserves_response(owned,monkeypatch):
    body=owned[2].body
    def unavailable(*args,**kwargs):raise RuntimeError('owned logger fault')
    monkeypatch.setattr(observer._LOGGER,'info',unavailable)
    with report_delivery_timing(observer.RUN,'en'):
        observer.observe_validated_retained_pdf(owned[0],owned[1],'en',owned[2])
    assert owned[2].body==body


def test_observer_never_traverses_retained_raw_receipt_payload(owned,caplog):
    record,package,response=owned
    class NeverTraverse(list):
        def __iter__(self):
            raise AssertionError('owned raw receipt traversal is forbidden')
    row=package['json']['assessment']['scanner_execution_records'][0]
    from nico.scanner_execution_receipt_v1 import VERSION
    row['scanner_execution_receipt']={'artifact_schema':VERSION,'receipt_sha256':'c'*64,
        'argument_count':3,'argv_capture_status':'complete_redacted',
        'input_identity_status':'stable_observed_inputs','argv':NeverTraverse(['owned-only'])}
    with caplog.at_level(logging.INFO,'uvicorn.error'):
        with report_delivery_timing(observer.RUN,'en'):
            observer.observe_validated_retained_pdf(record,package,'en',response)
    value=json.loads(messages(caplog)[0])
    assert value['outcome']=='observed_validated_frozen_pdf'
    retained=next(row for row in value['projection']['typescript']['observations']
                  if row['origin']=='retained_assessment')
    assert retained['execution_receipt']['summary_only_not_reverified'] is True
    assert retained['execution_receipt']['full_configuration_verified'] is False
