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
    second[id_key]='NICO-WORK-0000000000000001'
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
def test_incomplete_package_marker_does_not_bypass_finding_normalization(identity):
    report=complete_report();package={'package_id':identity, 'finding_id':report['canonical_findings'][0]['finding_id'],
                                    'action':'Retained incomplete object'}
    report['roadmap']=[package]
    result=repair_client_delivery_package({'json':report})['json']['roadmap'][0]
    assert result['title']==report['canonical_findings'][0]['title']
    assert result['finding_id']==package['finding_id']

@pytest.mark.parametrize('identity', [None, '', 42, 'not-a-package'])
@pytest.mark.parametrize('walker', ['phase16', 'phase9', 'v4', 'v55'])
def test_package_marker_cannot_hide_stale_finding_card(identity, walker):
    from nico.phase16_client_delivery_verification_v1 import _replace_nested_findings
    from nico.phase9_comprehensive_report_integration_v1 import _sync_surface as phase9
    from nico.client_finding_remediation_register_v4 import _sync_surface as v4
    from nico.comprehensive_canonical_projection_truth_v55 import _sync_finding_reference as v55
    canonical={'finding_id':'primary', 'finding_aliases':['alias'], 'title':'Current title'}
    card={'finding_id':'alias', 'title':'Stale title', 'package_id':identity}
    result={'phase16':_replace_nested_findings,'phase9':phase9,'v4':v4,'v55':v55}[walker]([card],{'alias':canonical})
    assert result[0]['finding_id']=='primary'
    assert result[0]['title']=='Current title'


def test_package_references_resolve_after_rebinding_reconciled_findings():
    report=complete_report(False)
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap
    result=rebind_generated_roadmap(repair_client_delivery_package({'json':report})['json'])
    by_id={f['finding_id']:f for f in result['canonical_findings']}
    refs=[p['source_refs'][0] for p in result['roadmap'] if p.get('finding_id')]
    assert len(refs)==50
    assert all(ref['record_sha256']==_hash(by_id[ref['finding_id']]) for ref in refs)


def test_complete_publication_binds_all_packages_and_dependent_surfaces():
    import base64
    from io import BytesIO
    from pypdf import PdfReader
    from tests.test_comprehensive_finding_roadmap_v1 import _context
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
    from nico.comprehensive_finding_roadmap_v1 import _base, assert_final_roadmap_binding
    context=_context()
    raw=context['prior_stage_results']
    hotspot=raw['repository_and_delivery_evidence']['complexity_evidence']['hotspots'][0]
    raw['repository_and_delivery_evidence']['complexity_evidence']['hotspots']=[
        {**hotspot,'path':f'nico/source_{i}.py','name':f'function_{i}'} for i in range(50)]
    raw['risk_reduction_and_executive_briefing']={'status':'complete','evidence':[]}
    gaps=[{'evidence_type':f'explicit_gap_{i}','state':'missing',
           'evidence_to_resolve':'Retained input','why_it_matters':'Retained limitation'} for i in range(6)]
    raw['functional_qa']={'status':'incomplete','missing_evidence':gaps}
    source=build_canonical_report_source(context)
    before=deepcopy(source)
    original=source['report_package']['json']
    assert len(original['roadmap'])==56
    result=finalize_report_package(source)['report_package']
    report=result['json']; packages=report['roadmap']; ids=[p['package_id'] for p in packages]
    assert len(ids)==len(set(ids))==56
    assert len(report['canonical_findings'])==50
    by_alias={alias:f for f in report['canonical_findings'] for alias in [f['finding_id'],*f.get('finding_aliases',[])]}
    for package in packages:
        assert package['package_id']==_base(package['source_binding'],package['kind'],package['source_refs'])['package_id']
        for ref in package['source_refs']:
            if ref['surface']=='canonical_findings':
                assert ref['record_sha256']==_hash(by_alias[ref['finding_id']])
            elif ref['surface']=='prior_stage_results':
                assert ref['record_sha256'] in {_hash(gap) for gap in gaps}
        for dep in package['dependencies']:
            if 'source_ref' in dep: assert dep['source_ref'] in package['source_refs']
    stale=set(p['package_id'] for p in original['roadmap'])-set(ids)
    assert stale
    for container in (report, report['assessment']):
        assert container['roadmap']==packages
        stages={s['stage_id']:s for s in container['stage_summaries']}
        assert stages['six_month_roadmap']['roadmap']==packages
        for name in ('staffing_sequencing_and_cost','risk_reduction_and_executive_briefing'):
            assert stages[name]['source_package_ids']==ids
        assert not any(old in str(stages) for old in stale)
    visible=result['markdown']+result['html']+'\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    assert not any(old in visible for old in stale)
    assert_final_roadmap_binding(report)
    assert source==before
    assert report['client_delivery_allowed'] is False
    assert report['human_review_required'] is True

@pytest.mark.parametrize('damage', ['package_id','source_binding','unresolved','ambiguous'])
def test_rebinding_fails_closed_for_invalid_source_graph(damage):
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap, _base
    report=complete_report(False)
    if damage=='package_id': report['roadmap'][0]['package_id']='NICO-WORK-0000000000000000'
    elif damage=='source_binding': report['roadmap_truth']['source_binding']['commit_sha']='b'*40
    elif damage=='unresolved': report['canonical_findings']=[]
    else:
        conflict=deepcopy(report['canonical_findings'][0]);conflict['title']='Different record'
        report['canonical_findings'].append(conflict)
    before=deepcopy(report)
    with pytest.raises(ValueError,match='roadmap_rebinding_'):
        rebind_generated_roadmap(report)
    assert report==before


def test_rebinding_keeps_distinct_alias_proposals_and_all_structured_references():
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap, _base
    report=complete_report(False)
    first=deepcopy(report['roadmap'][0]); second=deepcopy(first)
    finding=next(f for f in report['canonical_findings'] if f['finding_id']==first['finding_id'])
    second['finding_id']=finding['finding_aliases'][0]
    second['source_refs'][0]['finding_id']=second['finding_id']
    second['dependencies'][0]['source_ref']=deepcopy(second['source_refs'][0])
    second['package_id']=_base(second['source_binding'],second['kind'],second['source_refs'])['package_id']
    second['action']='Another authorized proposal'
    report['roadmap']=[first,second];report['roadmap_truth']['work_package_count']=2
    from nico.comprehensive_finding_roadmap_v1 import _roadmap_presentation
    presentation=_roadmap_presentation(report['roadmap'],False)
    for container in (report,report['assessment']):
        container['roadmap']=deepcopy(report['roadmap'])
        container['roadmap_truth']=deepcopy(report['roadmap_truth'])
        for stage in container['stage_summaries']:
            if stage['stage_id']=='six_month_roadmap':
                stage['roadmap']=deepcopy(report['roadmap'])
                stage['evidence']=presentation['roadmap']
            else:
                stage['source_package_ids']=[first['package_id'],second['package_id']]
                stage['evidence']=presentation['executive' if stage['stage_id']=='risk_reduction_and_executive_briefing' else 'staffing']
    # Other structured consumers can retain proposal references too.
    report['backlog']=[deepcopy(first),deepcopy(second)]
    finding['acceptance_criteria']=['Normalized criterion']
    result=rebind_generated_roadmap(report)
    assert len({p['package_id'] for p in result['roadmap']})==2
    assert result['backlog']==result['roadmap']
    assert result['roadmap'][1]['action']=='Another authorized proposal'
    for package in result['roadmap']:
        assert package['source_refs'][0]['record_sha256']==_hash(finding)
        assert package['dependencies'][0]['source_ref']==package['source_refs'][0]
    assert rebind_generated_roadmap(result)==result


def test_final_freeze_rejects_reference_or_mirror_drift():
    from nico.comprehensive_finding_roadmap_v1 import assert_final_roadmap_binding
    report=complete_report(False)
    report['canonical_findings'][0]['title']='Changed after rendering'
    with pytest.raises(ValueError,match='roadmap_binding_changed_after_render'):
        assert_final_roadmap_binding(report)
    report=complete_report(False)
    report['assessment']['stage_summaries'][1]['source_package_ids']=[]
    with pytest.raises(ValueError,match='roadmap_final_dependent_ids_mismatch'):
        assert_final_roadmap_binding(report)


def test_legacy_work_package_shape_is_preserved():
    from nico.phase16_client_delivery_verification_v1 import _replace_nested_findings
    package={'work_package_id':'WP-1','finding_id':'alias','time_window':'0-30 days',
             'related_finding_ids':['alias'],'objective':'Retained scope',
             'ordered_implementation_steps':['Inspect'],'dependencies':[]}
    assert _replace_nested_findings([package],{'alias':{'finding_id':'primary'}})==[package]


def synchronize_test_package_mirrors(report):
    """Keep mirrors consistent so controls exercise source contracts, not mirror checks."""
    from nico.comprehensive_finding_roadmap_v1 import _base
    for p in report['roadmap']:
        p['package_id']=_base(p['source_binding'],p['kind'],p['source_refs'])['package_id']
    ids=[p['package_id'] for p in report['roadmap']]
    for container in (report,report['assessment']):
        container['roadmap']=deepcopy(report['roadmap'])
        for stage in container['stage_summaries']:
            if stage['stage_id']=='six_month_roadmap':stage['roadmap']=deepcopy(report['roadmap'])
            else:stage['source_package_ids']=list(ids)


@pytest.mark.parametrize('operation',['rebind','freeze'])
@pytest.mark.parametrize('damage', ['dependency','commit_sha','source_commit_sha','run_id','repository',
                                    'conflicting_commit_alias','candidate_count','package_finding_id'])
def test_inconsistent_source_contract_rejected_before_rebinding_and_freeze(operation,damage):
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap, assert_final_roadmap_binding
    report=complete_report()
    package=report['roadmap'][0]
    finding=next(f for f in report['canonical_findings'] if f['finding_id']==package['finding_id'])
    if damage=='dependency':
        package['dependencies'][0]['source_ref']['record_sha256']='0'*64
    elif damage=='package_finding_id':package['finding_id']='no_such_finding'
    elif damage=='candidate_count':report['review_candidate_summary']['review_required_total']=3
    else:
        if damage=='conflicting_commit_alias':
            finding['source_commit_sha']=report['identity']['commit_sha']
            finding['commit_sha']='b'*40
        else:finding[damage]='b'*40 if 'sha' in damage else 'other-source'
        # Even a self-consistent digest cannot legitimize another source identity.
        package['source_refs'][0]['record_sha256']=_hash(finding)
        package['dependencies'][0]['source_ref']=deepcopy(package['source_refs'][0])
    if damage=='candidate_count':
        candidate=next(p for p in report['roadmap'] if p['kind']=='candidate_disposition')
        candidate['source_refs'][0]['record_sha256']=_hash(report['review_candidate_summary'])
    synchronize_test_package_mirrors(report)
    before=deepcopy(report)
    fn=rebind_generated_roadmap if operation=='rebind' else assert_final_roadmap_binding
    with pytest.raises(ValueError,match='roadmap_rebinding_'):
        fn(report)
    assert report==before

@pytest.mark.parametrize('operation',['rebind','freeze'])
def test_reviewer_foreign_source_repro_rejected_without_rewriting_old_reference(operation):
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap, assert_final_roadmap_binding
    report=complete_report(False)
    finding=next(f for f in report['canonical_findings'] if f['finding_id']==report['roadmap'][0]['finding_id'])
    finding.update(source_commit_sha='b'*40,run_id='different_run',repository='different/repository')
    before=deepcopy(report)
    with pytest.raises(ValueError,match='roadmap_rebinding_finding_source_identity_mismatch'):
        (rebind_generated_roadmap if operation=='rebind' else assert_final_roadmap_binding)(report)
    assert report==before


def test_candidate_metadata_normalization_rebinds_without_changing_review_count():
    from nico.comprehensive_finding_roadmap_v1 import rebind_generated_roadmap, assert_final_roadmap_binding, _base
    report=complete_report()
    original=next(p for p in report['roadmap'] if p['kind']=='candidate_disposition')
    report['review_candidate_summary']['normalization_note']='Retained review status'
    result=rebind_generated_roadmap(report)
    candidate=next(p for p in result['roadmap'] if p['kind']=='candidate_disposition')
    assert candidate['review_required_candidate_count']==1536
    assert candidate['source_refs'][0]['record_sha256']==_hash(result['review_candidate_summary'])
    assert candidate['package_id']!=original['package_id']
    assert candidate['package_id']==_base(candidate['source_binding'],candidate['kind'],candidate['source_refs'])['package_id']
    assert_final_roadmap_binding(result)
