"""Applicability score synchronization preserves declared formula semantics."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest


def _contract():
    return dict(version='nico.comprehensive-native-providers.v5',
        scoring_model_version='technical-minus-named-assurance-deductions.v1',
        all_numeric_score_inputs_renderable=True, technical_score=95,
        evidence_adjusted_score=95, candidate_volume_penalty=0,
        missing_raw_payload_penalty=0, incomplete_analyzer_penalty=0,
        other_assurance_penalties={}, other_assurance_penalty_total=0,
        assurance_penalty=0, evidence_penalty_points=0,
        score_formula='95 - 0 - 0 - 0 - 0 = 95')


@pytest.mark.parametrize('payload,execution', [(0,0),(2,4),(90,10)])
def test_named_model_formula_survives_authoritative_evidence_sync(payload, execution):
    from nico.comprehensive_authoritative_scanner_truth_v62 import _synchronize_evidence_score_aliases
    source=_contract();source['missing_raw_payload_penalty']=payload
    before=deepcopy(source)
    result=_synchronize_evidence_score_aliases(source,technical_score=95,
        payload_penalty=payload,execution_penalty=execution)
    assert result['scoring_model_version']==source['scoring_model_version']
    assert result['score_formula']==f'95 - 0 - {payload} - {execution} - 0 = {max(0,95-payload-execution)}'
    expected=deepcopy(before)
    expected.update(evidence_adjusted_score=max(0,95-payload-execution),
        incomplete_analyzer_penalty=execution, assurance_penalty=payload+execution,
        evidence_penalty_points=payload+execution)
    assert {k:v for k,v in result.items() if k!='score_formula'}=={k:v for k,v in expected.items() if k!='score_formula'}
    assert source==before


def _worker(language):
    import base64,io
    from nico.api import final_report_worker_bootstrap
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_authoritative_scanner_truth_v62 import _synchronize_evidence_score_aliases
    from nico.report_score_explanation import UNAVAILABLE,LABELS_ES
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from pypdf import PdfReader
    package=_package(language);assessment=package['json']['assessment']
    assessment.update(technical_score=95,canonical_technical_score=95,evidence_adjusted_score=95,canonical_evidence_adjusted_score=95)
    assessment['maturity_signal'].update(score=95,presented_score=95,technical_score=95,evidence_adjusted_score=95,evidence_readiness_score=95)
    assessment['score_contract']=_contract()
    # Production applicability synchronization formerly changed this valid named
    # contract to the exact three-term formula retained in the M3 report.
    package['json']=_synchronize_evidence_score_aliases(package['json'],technical_score=95,payload_penalty=0,execution_penalty=0)
    before=deepcopy(package)
    result=rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages).split())
    label='Retained formula' if language=='en' else LABELS_ES['Retained formula']
    assert label in text
    assert '95 - 0 - 0 - 0 - 0 = 95' in text
    assert UNAVAILABLE not in text and LABELS_ES[UNAVAILABLE] not in text
    assert package==before
    assert result['json']['assessment']['technical_score']==95
    assert result['json']['assessment']['evidence_adjusted_score']==95
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False
    assert result['approval_status']=='pending_human_approval'
    assert result['delivery_status']=='blocked_pending_human_approval'


@pytest.mark.parametrize('language',['en','es-MX'])
def test_installed_final_worker_explains_synchronized_named_contract(language,tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    env=owned_worker_environment(root,tmp_path,os.environ)
    code='from tests.test_score_contract_scanner_synchronization import _worker; import sys; _worker(sys.argv[1])'
    result=subprocess.run([sys.executable,'-c',code,language],cwd=root,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('change',['missing_candidate','missing_others','candidate_bool','other_bool','other_named','candidate_nonzero','other_total_mismatch','empty_key','noninteger_other_total','absent_formula'])
def test_incomplete_or_conflicting_named_terms_are_not_fabricated(change):
    from nico.comprehensive_authoritative_scanner_truth_v62 import _synchronize_evidence_score_aliases
    from nico.report_score_explanation import score_explanation, UNAVAILABLE
    source=_contract()
    # Retain the observed incompatible formula; incomplete evidence must not be
    # silently supplied merely to make a presentation contract pass.
    source['score_formula']='95 - 0 - 0 = 95'
    if change=='missing_candidate':source.pop('candidate_volume_penalty')
    elif change=='missing_others':source.pop('other_assurance_penalties')
    elif change=='candidate_bool':source['candidate_volume_penalty']=False
    elif change=='other_bool':source['other_assurance_penalties']={'synthetic':False}
    elif change=='other_named':source['other_assurance_penalties']={'synthetic':1}
    elif change=='candidate_nonzero':source['candidate_volume_penalty']=1
    elif change=='other_total_mismatch':source['other_assurance_penalty_total']=1
    elif change=='empty_key':source['other_assurance_penalties']={'':0}
    elif change=='noninteger_other_total':source['other_assurance_penalty_total']=0.0
    elif change=='absent_formula':source.pop('score_formula')
    before=deepcopy(source)
    result=_synchronize_evidence_score_aliases(source,technical_score=95,payload_penalty=0,execution_penalty=0)
    assert result==before
    assert source==before
    assert score_explanation({'score_contract':result})==[UNAVAILABLE]


def test_evidence_completeness_formula_and_nonpresentation_fields_unchanged():
    from nico.comprehensive_authoritative_scanner_truth_v62 import _synchronize_evidence_score_aliases
    source=_contract();source['scoring_model_version']='technical-minus-evidence-completeness-deductions.v1'
    source['score_formula']='95 - 0 - 0 = 95'
    assert _synchronize_evidence_score_aliases(source,technical_score=95,payload_penalty=0,execution_penalty=0)==source
    source=_contract();source['score_formula']='95 - 0 - 0 = 95'
    result=_synchronize_evidence_score_aliases(source,technical_score=95,payload_penalty=0,execution_penalty=0)
    assert {k:v for k,v in result.items() if k!='score_formula'}=={k:v for k,v in source.items() if k!='score_formula'}
