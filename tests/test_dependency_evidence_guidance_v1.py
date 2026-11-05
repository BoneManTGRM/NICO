from copy import deepcopy
import pytest
from tests.test_dependency_identity_evidence_v1 import row, capture, SCOPE
from nico.candidate_investigation_pipeline_v1 import investigate_register, display_investigation


def view(retained=None, *, change_row=None, change_capture=None):
    r=row()
    if change_row:
        change_row(r)
    retained=capture([r]) if retained is None else retained
    register={'findings':[r]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    if change_capture:
        change_capture(retained)
    before=deepcopy(register)
    result=display_investigation(register,SCOPE,trusted_capture=retained)
    assert register==before
    assert result['completed_count']==0
    return result['packets'][0]


def test_verified_identity_keeps_installed_and_runtime_questions():
    assert view()['dependency_next_step']=='verify_installation_and_use'


def test_missing_request_does_not_invent_capture_cause():
    assert view(change_row=lambda r:r.pop('dependency_identity_request'))['dependency_next_step']=='supply_scanner_identity'


def test_foreign_capture_requests_current_evidence():
    assert view(change_capture=lambda c:c['scope'].update(customer_id='foreign'))['dependency_next_step']=='supply_current_capture'


def test_missing_observation_requests_capture_not_repair():
    assert view(change_capture=lambda c:c.update(observations={}))['dependency_next_step']=='supply_lockfile_observation'


def test_unavailable_observation_does_not_invent_parser_failure():
    assert view(change_capture=lambda c:c['observations'].update({'package-lock.json':{'status':'unavailable'}}))['dependency_next_step']=='inspect_lockfile_capture'


def test_ambiguous_identity_requests_match_review_without_claiming_clearance():
    r=row(); retained=capture([r],{'node_modules/demo':{'version':'1.2.3'},'node_modules/a/node_modules/demo':{'version':'2.0.0'}})
    assert view(retained)['dependency_next_step']=='reconcile_lockfile_identity'


def test_missing_persisted_receipt_never_claims_matching_was_attempted():
    r=row(); retained=capture([r]); register={'findings':[r]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    register['candidate_investigation']['packets'][0].pop('dependency_identity')
    result=display_investigation(register,SCOPE,trusted_capture=retained)
    assert result['packets'][0]['dependency_next_step']=='reconcile_lockfile_identity'
    assert result['dependency_identity_collected_count']==0


def test_injected_stored_next_step_is_not_projected():
    r=row(); retained=capture([r]); register={'findings':[r]}
    register['candidate_investigation']=investigate_register(register,retained,SCOPE)
    packet=register['candidate_investigation']['packets'][0]
    packet.pop('dependency_identity')
    packet['dependency_next_step']='verify_installation_and_use'
    result=display_investigation(register,SCOPE,trusted_capture=retained)
    assert result['packets'][0]['dependency_next_step']=='reconcile_lockfile_identity'
    assert 'dependency_identity' not in result['packets'][0]


@pytest.mark.parametrize('field',['scope','path','artifact_schema','origin'])
def test_foreign_observation_requests_current_evidence(field):
    assert view(change_capture=lambda c:c['observations']['package-lock.json'].update({field:'foreign'}))['dependency_next_step']=='supply_current_capture'


@pytest.mark.parametrize('field',['customer_id','project_id','exact_commit_sha','source_repository'])
def test_foreign_candidate_requests_current_evidence(field):
    assert view(change_row=lambda r:r.update({field:'foreign'}))['dependency_next_step']=='supply_current_capture'
