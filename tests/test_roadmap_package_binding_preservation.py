from copy import deepcopy
import pytest
from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap, _hash
from nico.phase16_client_delivery_verification_v1 import repair_client_delivery_package


def complete_report(include_candidate=True):
    findings=[{'finding_id':f'NICO-FINDING-{i:012X}','finding_aliases':[f'NICO-FINDING-ALIAS-{i}']+(['NICO-FINDING-EXTRA-ALIAS'] if i==0 else []),
     'title':'Retained complexity hotspot','category':'architecture','location':f'fixture/source_{i}.py:10',
     'status':'review_required','disposition':'unconfirmed','severity':'medium',
     'recommendation':'Retained synthetic correction','verification':['Retained synthetic test'],
     'impact':'Retained synthetic rationale'} for i in range(50)]
    raw={'fixture_gap_stage':{'status':'incomplete','missing_evidence':[
     {'evidence_type':f'synthetic_gap_{i}','state':'missing','evidence_to_resolve':'Retained input',
      'why_it_matters':'Retained limitation'} for i in range(5 if include_candidate else 6)]}}
    canonical={'identity':{'run_id':'comprun_synthetic_complete','repository':'fixture/repository',
     'commit_sha':'a'*40,'evidence_ledger_id':'ledger_synthetic'},'report_language':'en',
     'canonical_findings':findings,'assessment':{'technical_score':93,'evidence_adjusted_score':93},
     'review_candidate_summary':{'review_required_total':1536 if include_candidate else 0},
     'scanner_summary':{'scanner_units':248,'source_findings':50,'reconciled_total':298},
     'qc_summary':{'pending':187},
     'stage_summaries':[{'stage_id':'six_month_roadmap'},{'stage_id':'risk_reduction_and_executive_briefing'},
                        {'stage_id':'staffing_sequencing_and_cost'}]}
    complete=bind_final_finding_roadmap(canonical,raw_stages=raw)
    complete['assessment']['stage_summaries']=deepcopy(complete['stage_summaries'])
    complete.update(report_finality='automated_draft', approval_status='pending_human_approval',
                    delivery_status='blocked_pending_human_approval', human_review_required=True,
                    human_review_completed=False, client_delivery_allowed=False)
    packages=complete['roadmap'];assert len(packages)==56
    assert len({p['package_id'] for p in packages})==56
    package_owned_fields=set(packages[0])-{'finding_id','verification'}
    assert len(package_owned_fields)==26
    assert sum(p.get('finding_id') is not None for p in packages)==50
    for p in packages:
     assert all(k in p for k in ['package_id','source_binding','source_refs','action','verification','dependencies',
      'sequence_state','execution_state','stakeholder_approved','assigned_owner','committed_date','capacity_estimate','cost_estimate','delivery_authorized'])
    for p in packages[:50]:
     finding=next(f for f in findings if f['finding_id']==p['finding_id'])
     assert p['source_refs'][0]['record_sha256']==_hash(finding)
    return complete


def surfaces(value):
    return [value['roadmap'], value['assessment']['roadmap'],
            value['stage_summaries'][0]['roadmap'],
            value['assessment']['stage_summaries'][0]['roadmap']]


@pytest.mark.parametrize('include_candidate', [False, True])
def test_complete_50_finding_six_gap_packages_survive_production_repair(include_candidate):
    report=complete_report(include_candidate);before=deepcopy(report)
    result=repair_client_delivery_package({'json':report})['json']
    for actual,expected in zip(surfaces(result),surfaces(before)):
        assert actual==expected
    for stage in (1,2):
        assert result['stage_summaries'][stage]==before['stage_summaries'][stage]
    for key in ('review_candidate_summary','scanner_summary','qc_summary'):
        assert result[key]==before[key]
    assert result['assessment']['technical_score']==93
    assert result['assessment']['evidence_adjusted_score']==93
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True
    for key in ('report_finality','approval_status','delivery_status','human_review_required',
                'human_review_completed','client_delivery_allowed'):
        assert result[key]==before[key]
    assert report==before
    assert repair_client_delivery_package({'json':result})['json']==result


@pytest.mark.parametrize('id_key',['package_id','work_package_id'])
def test_distinct_packages_for_same_finding_and_alias_survive(id_key):
    report=complete_report();first=deepcopy(report['roadmap'][0]);second=deepcopy(first)
    first[id_key]=first.pop('package_id') if id_key!='package_id' else first['package_id']
    second[id_key]='NICO-WORK-SECOND'
    if id_key!='package_id':second.pop('package_id')
    finding=next(f for f in report['canonical_findings'] if f['finding_id']==first['finding_id'])
    second['finding_id']=finding['finding_aliases'][0]
    second['action']='Different retained work scope'
    report['roadmap']=[first,second]
    expected=deepcopy(report['roadmap'])
    result=repair_client_delivery_package({'json':report})['json']
    assert result['roadmap']==expected
    aliases={alias for f in result['canonical_findings'] for alias in [f['finding_id'],*f.get('finding_aliases',[])]}
    assert {p['finding_id'] for p in expected}<=aliases


def test_phase9_publication_normalization_keeps_bound_package_fields(monkeypatch):
    from nico import phase9_comprehensive_report_integration_v1 as integration
    report=complete_report();before=deepcopy(report)
    def stop_before_render(value):
        # Run actual normalization/repair; stop only before expensive artifact generation.
        value['report_package'].update(canonical_truth_sha256='fixture',findings_csv_base64='fixture')
        return value
    monkeypatch.setattr(integration,'apply_v2_pipeline',stop_before_render)
    result=integration.finalize_report_package({'report_package':{'json':report}})['report_package']['json']
    for actual,expected in zip(surfaces(result),surfaces(before)):
        for a,e in zip(actual,expected,strict=True):
            assert a==e
    assert report==before


def test_final_projection_preserves_package_bindings_and_real_finding_mirrors():
    from nico.comprehensive_canonical_projection_truth_v55 import normalize_final_projection
    report=complete_report();before=deepcopy(report)
    # Ordinary finding mirrors must still resolve an alias and receive canonical copy.
    finding=report['canonical_findings'][0]
    report['finding_cards']=[{'finding_id':finding['finding_aliases'][0],'title':'stale title'}]
    result=normalize_final_projection(report)
    for actual,expected in zip(surfaces(result),surfaces(before)):
        assert actual==expected
    assert result['finding_cards'][0]['finding_id']==finding['finding_id']
    assert result['finding_cards'][0]['title']==finding['title']
    assert len(result['canonical_findings'])==50


@pytest.mark.parametrize('identity', [None, '', 42])
def test_incomplete_package_identity_does_not_invent_or_delete_fields(identity):
    report=complete_report();package={'package_id':identity, 'finding_id':report['canonical_findings'][0]['finding_id'],
                                    'action':'Retained incomplete object'}
    report['roadmap']=[package]
    assert repair_client_delivery_package({'json':report})['json']['roadmap']==[package]
