import base64
import hashlib
import importlib
import inspect
import json
from types import SimpleNamespace

import pytest

from nico.ordinary_bundle_boundary_v2 import ERROR, has_report_bundle, require_legacy_single_pdf
from tests.test_client_pdf_compose_v2 import _pdf
from tests.test_comprehensive_operator_approval_v1 import service, current, payload


def record():
    pdf=_pdf(['Valid first volume alone does not establish bundle approval'])
    package={'report_bundle_schema':'nico.ordinary-report-files.v2',
             'pdf_base64':base64.b64encode(pdf).decode(), 'pdf_sha256':hashlib.sha256(pdf).hexdigest(),
             'markdown':'review', 'html':'<p>review</p>', 'json':{}}
    return {'terminal':True,'status':'approved','human_review_completed':True,
            'client_delivery_allowed':True,'revision':1,'reports':package,
            'accepted_edition':{'accepted_edition':True,'client_delivery_allowed':True}}


@pytest.mark.parametrize('location',['direct','reports','json','serialized_json','stage','operator'])
def test_marker_locations_reject_even_valid_volume_one(location):
    package=record()['reports']
    if location=='direct': value=package
    if location=='reports': value={'reports':package}
    if location=='json': value={'json':package}
    if location=='serialized_json': value={'artifacts':{'json':json.dumps(package)}}
    if location=='stage': value={'stage_results':{'final_comprehensive_report_generation':{'report_package':package}}}
    if location=='operator': value={'operator_approved_edition':{'reports':package}}
    with pytest.raises(ValueError,match=ERROR):require_legacy_single_pdf(value)


def test_quoted_evidence_is_not_a_format_marker():
    evidence={'artifact_schema':'nico.ordinary-report-files.v2','report_bundle':{}}
    assert not has_report_bundle({'json':{'evidence':[evidence]}})
    assert not has_report_bundle({'json':json.dumps({'evidence':[evidence]})})
    for malformed in (None,{},False):
        with pytest.raises(ValueError,match=ERROR): require_legacy_single_pdf({'report_bundle':malformed})
    with pytest.raises(ValueError,match=ERROR):require_legacy_single_pdf({'artifact_schema':'nico.ordinary-report-files.v999'})


BOUNDARIES = [
    ('comprehensive_run_service','_require_exact_final_report_integrity','record'),
    ('decision_grade_accepted_edition_guard_v1','current_report_artifact_digests','package'),
    ('decision_grade_accepted_edition_guard_v1','validate_accepted_edition','package'),
    ('decision_grade_accepted_edition_v2','build_accepted_report_edition','artifacts'),
    ('comprehensive_review_decision_v1','build_reviewed_edition','record'),
    ('comprehensive_approved_report_v1','build_approved_report_package','package'),
    ('comprehensive_delivery_authorization_v1','authorize_accepted_edition','record'),
    ('comprehensive_delivery_authorization_v1','validate_delivery_authorization','record'),
    ('comprehensive_operator_approval_v1','build_operator_edition','record'),
    ('comprehensive_operator_approval_v1','_artifact_digests','reports'),
    ('comprehensive_delivery_package_v2','build_comprehensive_delivery_package','report_package'),
    ('comprehensive_automated_delivery_v1','build_automated_delivery_package','record'),
    ('comprehensive_exact_artifact_hash_binding_v1','_validate_exact_artifact_hashes','result'),
    ('comprehensive_retained_report_export_v1','retained_report_zip','report'),
    ('comprehensive_same_run_locale_report_v1','build_same_run_locale_report','status'),
    ('comprehensive_same_run_locale_report_v1','build_same_run_locale_pdf_response','status'),
    *[(f'comprehensive_approved_delivery_v{n}','build_approved_delivery_package','record') for n in (1,2,3,4)],
    *[(f'comprehensive_approved_delivery_v{n}','validate_approved_delivery_package','record') for n in (1,3,4)],
]


@pytest.mark.parametrize('module,name,parameter', BOUNDARIES)
def test_legacy_entry_points_reject_v2_before_single_pdf_work(module,name,parameter):
    fn=getattr(importlib.import_module('nico.'+module),name)
    arguments={key:'' for key,p in inspect.signature(fn).parameters.items()
               if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_KEYWORD,p.VAR_POSITIONAL)}
    arguments[parameter]=record() if parameter in ('record','status') else record()['reports']
    with pytest.raises(ValueError,match=ERROR): fn(**arguments)


@pytest.mark.parametrize('operation',['review','authorize_delivery','operator_approve','operator_authorize'])
def test_service_actions_never_persist_partial_authority(operation):
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_operator_approval_v1 import approve_operator_report
    from nico.comprehensive_operator_delivery_v1 import authorize_operator_delivery
    source=record(); saved=[]
    store=SimpleNamespace(load=lambda _:source,save=lambda *a,**k:saved.append((a,k)))
    service=SimpleNamespace(_store=store,load_read_only=lambda _:source)
    with pytest.raises(ValueError,match=ERROR):
        if operation=='review':
            ComprehensiveRunService.review(service,'run',reviewer='r',reviewer_role='r',decision='approved',decision_reason='reviewed')
        elif operation=='authorize_delivery':
            ComprehensiveRunService.authorize_delivery(service,'run',authorizer='r',authorizer_role='r',authorization_reason='reviewed')
        elif operation=='operator_approve': approve_operator_report(service,'run',{})
        else: authorize_operator_delivery(service,'run',{'delivery_kind':'operator_report','delivery_authorized':True,'authorization_confirmed':True})
    assert not saved


def test_old_operator_receipts_cannot_validate_v2_source():
    from nico.comprehensive_operator_approval_v1 import validated_operator_edition
    from nico.comprehensive_operator_delivery_v1 import validated_operator_delivery
    source=record();source['operator_approved_edition']={'artifact_schema':'legacy-receipt'}
    source['operator_delivery_edition']={'artifact_schema':'legacy-receipt'}
    assert validated_operator_edition(source) is None
    assert validated_operator_delivery(source) is None


def test_mobile_artifact_boundary_returns_explicit_conflict(monkeypatch):
    from fastapi import HTTPException
    from nico import comprehensive_mobile_recovery_v1 as mobile
    service=SimpleNamespace(load_read_only=lambda _:record())
    monkeypatch.setattr(mobile.routes_module,'_controller',lambda _:object())
    monkeypatch.setattr(mobile.routes_module,'_service',lambda _:service)
    with pytest.raises(HTTPException) as caught:mobile._artifact_record(object(),'run')
    assert caught.value.status_code==409 and caught.value.detail==ERROR


@pytest.mark.parametrize('service',[False,True],indirect=True)
def test_previously_valid_operator_receipt_is_invalid_for_bundle_source(service):
    from copy import deepcopy
    from nico.comprehensive_operator_approval_v1 import approve_operator_report, validated_operator_edition
    from nico.comprehensive_review_decision_v1 import report_package_from_record
    before=current(service)
    approved=approve_operator_report(service,before['identity']['run_id'],payload(before))
    assert validated_operator_edition(approved) is not None
    changed=deepcopy(approved)
    package=changed['stage_results']['final_comprehensive_report_generation']['report_package']
    original=report_package_from_record(approved)
    package['report_bundle_schema']='nico.ordinary-report-files.v2'
    # The old approved PDF and four-artifact payload are still byte-identical.
    # Their valid receipt must not gain authority over newly declared volumes.
    for key in ('pdf_base64','pdf_sha256','markdown','html','json'):
        assert package[key]==original[key]
    assert validated_operator_edition(changed) is None
    with pytest.raises(ValueError,match=ERROR):require_legacy_single_pdf(changed)
