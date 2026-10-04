from copy import deepcopy
import pytest
from nico.scanner_score_lifts import apply_verified_scanner_score_lifts


def owned_result():
    tools={name:{'status':'completed_clean','findings_count':0,'verified_for_this_report':True} for name in ('bandit','semgrep','eslint','typescript','pip-audit','npm-audit','osv-scanner')}
    tools['bandit'].update(status='completed_with_findings',findings_count=1,findings=[{'rule_id':'B101'}])
    return {'status':'complete','sections':[{'id':'static_analysis','score':55,'status':'yellow','findings':['Current TypeScript diagnostic requires review.'],'unavailable':[]},{'id':'velocity_complexity','score':55,'status':'yellow','findings':[],'unavailable':[]}],'scanner_artifacts':{'tools':tools},'bandit_triage':{'finding_count':1,'approved_count':1,'blocking_count':0,'review_required_count':0,'score_lift_allowed':True},'complexity_engine':{'velocity_score':88}}


@pytest.mark.parametrize('analyzer', ['semgrep','eslint','typescript'])
def test_bandit_only_triage_cannot_clear_other_analyzers(analyzer):
    result=owned_result()
    result['scanner_artifacts']['tools'][analyzer].update(status='completed_with_findings',findings_count=1,findings=[{'rule_id':'UNRESOLVED_OWNED_CONTROL'}])
    original=deepcopy(result['scanner_artifacts']['tools'][analyzer])
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==55
    assert sections['velocity_complexity']['score']==55
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is False
    assert sections['static_analysis']['findings']==['Current TypeScript diagnostic requires review.']
    assert output['scanner_artifacts']['tools'][analyzer]==original


def test_bandit_triage_with_clean_other_analyzers_still_lifts():
    output=apply_verified_scanner_score_lifts(owned_result())
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==88
    assert sections['velocity_complexity']['score']==88
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is True


@pytest.mark.parametrize('triage', [
    None,
    {},
    {'finding_count': 0, 'score_lift_allowed': True},
    {'finding_count': 2, 'score_lift_allowed': True},
    {'finding_count': 1, 'score_lift_allowed': False},
    {'finding_count': 1, 'score_lift_allowed': True, 'static_lift_allowed': False},
    {'finding_count': 1, 'score_lift_allowed': True, 'human_review_required': True},
    {'finding_count': 1, 'score_lift_allowed': True, 'invalid_triage_records': [{'reason': 'invalid reviewer'}]},
    {'finding_count': 1, 'score_lift_allowed': True, 'missing_triage_records': ['owned_missing']},
    {'finding_count': 1, 'score_lift_allowed': True, 'blocker_count': 1},
    {'finding_count': 1, 'score_lift_allowed': True, 'status': 'needs_human_review'},
    {'finding_count': 1, 'status': 'approved_no_blockers', 'approved_count': 0, 'approval_artifact_attached': True, 'human_review_required': False},
    {'finding_count': 1, 'status': 'approved_no_blockers', 'approved_count': 1, 'approval_artifact_attached': False, 'human_review_required': False},
])
def test_bandit_triage_cannot_infer_missing_denied_or_wrong_population_authority(triage):
    result=owned_result()
    if triage is None:
        result.pop('bandit_triage')
    else:
        result['bandit_triage']=triage
    original=deepcopy(result['scanner_artifacts']['tools']['bandit'])
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==55
    assert sections['velocity_complexity']['score']==55
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is False
    assert output['scanner_artifacts']['tools']['bandit']==original


@pytest.mark.parametrize('triage', [
    {'finding_count': 1, 'status': 'approved_no_blockers', 'approved_count': 1, 'approval_artifact_attached': True, 'human_review_required': False},
    {'total_findings': 1, 'approved_count': 1, 'score_lift_allowed': True},
    {'total_findings': 1, 'informational_count': 1, 'static_lift_allowed': True},
])
def test_existing_affirmative_bandit_contracts_remain_eligible(triage):
    result=owned_result()
    result['bandit_triage']=triage
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==88
    assert sections['velocity_complexity']['score']==88
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is True


@pytest.mark.parametrize('count_field', ['blocking_count','review_required_count','needs_review_count','unresolved_high_confidence_count','blocker_count'])
def test_negative_triage_counts_do_not_grant_clearance(count_field):
    result=owned_result()
    result['bandit_triage'][count_field]=-1
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==55
    assert sections['velocity_complexity']['score']==55
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is False


@pytest.mark.parametrize('counts', [
    {'blocking_count': -1, 'review_required_count': 1},
    {'review_required_count': 1, 'needs_review_count': -1},
])
def test_triage_counts_cannot_cancel_or_hide_other_alias_counts(counts):
    result=owned_result()
    result['bandit_triage'].update(counts)
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==55
    assert sections['velocity_complexity']['score']==55
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is False


@pytest.mark.parametrize('invalid_count', [0.5, 'invalid', None, False])
def test_present_invalid_count_cannot_be_coerced_to_zero(invalid_count):
    result=owned_result()
    result['bandit_triage']['blocking_count']=invalid_count
    output=apply_verified_scanner_score_lifts(result)
    sections={item['id']:item for item in output['sections']}
    assert sections['static_analysis']['score']==55
    assert sections['velocity_complexity']['score']==55
    assert output['final_evidence_score_bridge']['static_triaged_without_blockers'] is False
