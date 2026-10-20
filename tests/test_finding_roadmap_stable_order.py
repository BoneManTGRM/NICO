from collections import Counter
from copy import deepcopy

import pytest

from nico.comprehensive_finding_roadmap_v1 import (
    _base, _hash, assert_final_roadmap_binding, bind_final_finding_roadmap,
)
from test_comprehensive_finding_roadmap_v1 import _canonical


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items()
                if k not in {'package_id', 'source_binding', 'record_sha256'}}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def preview(report):
    stage=next(s for s in report['stage_summaries'] if s['stage_id']=='six_month_roadmap')
    # Only replace the provenance prefix; keep every semantic character and order.
    lines=[line.partition(' | ')[2] for line in stage['evidence']]
    assert len(lines)>100
    return lines, lines[:100]


@pytest.mark.parametrize('changed', [('run_id',), ('evidence_ledger_id',), ('run_id','evidence_ledger_id')])
def test_identity_only_changes_preserve_finding_order_and_preview(changed):
    original=_canonical()
    original['canonical_findings']=[{**original['canonical_findings'][0],
        'finding_id':f'F-{i:03}', 'location':f'src/{i}.py:1',
        'recommendation':f'Correction {i}', 'run_id':original['identity']['run_id'],
        'evidence_ledger_id':original['identity']['evidence_ledger_id']} for i in reversed(range(50))]
    raw={}
    other=deepcopy(original); other_raw=deepcopy(raw)
    for key in changed:
        other['identity'][key]+='_next'
        for finding in other['canonical_findings']:
            finding[key]=other['identity'][key]
    before=deepcopy((original,raw,other,other_raw))
    reports=[bind_final_finding_roadmap(c,raw_stages=s) for c,s in [(original,raw),(other,other_raw)]]
    assert (original,raw,other,other_raw)==before
    shuffled=deepcopy(original); shuffled_raw=deepcopy(raw)
    shuffled['canonical_findings'].reverse()
    assert bind_final_finding_roadmap(shuffled,raw_stages=shuffled_raw)['roadmap']==reports[0]['roadmap']
    for report in reports:
        assert_final_roadmap_binding(report)
        assert report['human_review_required'] is True
        assert report['client_delivery_allowed'] is False
        for package in report['roadmap']:
            assert package['package_id']==_base(report['identity'],package['kind'],package['source_refs'])['package_id']
            assert package['delivery_authorized'] is False
            if package['kind']=='finding_review_and_remediation':
                finding=next(f for f in report['canonical_findings'] if f['finding_id']==package['finding_id'])
                assert package['source_refs'][0]['record_sha256']==_hash(finding)
            elif package['kind']=='candidate_disposition':
                assert package['source_refs'][0]['record_sha256']==_hash(report['review_candidate_summary'])
    assert {p['package_id'] for p in reports[0]['roadmap']}.isdisjoint(p['package_id'] for p in reports[1]['roadmap'])
    assert Counter(preview(reports[0])[0])==Counter(preview(reports[1])[0])
    assert semantic(reports[0]['roadmap'])==semantic(reports[1]['roadmap'])
    assert preview(reports[0])[1]==preview(reports[1])[1]


@pytest.mark.parametrize('locator', ['https://evidence/a-run/qa','https://evidence/z-run/qa'])
@pytest.mark.parametrize('artifact_only', [False,True])
def test_gap_locators_and_artifact_ids_keep_existing_order_and_provenance(locator,artifact_only):
    canonical=_canonical(); canonical['canonical_findings']=[]
    gaps=[{'evidence_type':'runtime_qa','state':'missing',
           'evidence_to_resolve':url,'artifact_id':artifact}
          for url,artifact in [(locator,'current'),('https://evidence/m-retained/qa','retained')]]
    if artifact_only:
        gaps[1]['evidence_to_resolve']=gaps[0]['evidence_to_resolve']
    raw={'qa':{'missing_evidence':gaps}}
    before=deepcopy((canonical,raw))
    result=bind_final_finding_roadmap(canonical,raw_stages=raw)
    assert (canonical,raw)==before
    packages=[p for p in result['roadmap'] if p['kind']=='evidence_gap_resolution']
    # No generic locator normalization or semantic-order guarantee for gaps.
    assert [p['package_id'] for p in packages]==sorted(p['package_id'] for p in packages)
    assert len(packages)==2
    for gap in gaps:
        package=next(p for p in packages if p['source_refs'][0]['record_sha256']==_hash(gap))
        assert package['retained_required_input']==gap['evidence_to_resolve']
        assert package['package_id']==_base(canonical['identity'],package['kind'],package['source_refs'])['package_id']
    assert_final_roadmap_binding(result)


def test_kind_and_severity_priority_precede_semantic_ties():
    canonical=_canonical()
    levels=['unknown','informational','info','low','moderate','medium','high','critical']
    canonical['canonical_findings']=[{**canonical['canonical_findings'][0],
        'finding_id':f'F-{i:03}', 'severity':level} for i,level in enumerate(levels)]
    report=bind_final_finding_roadmap(canonical,raw_stages={'qa':{'missing_evidence':[
        {'evidence_type':'runtime_qa','state':'missing'}]}})
    packages=report['roadmap']
    ranks={'critical':0,'high':1,'medium':2,'moderate':2,'low':3,'info':4,'informational':4,'unknown':5}
    assert [ranks[p['retained_severity']] for p in packages[:8]]==[0,1,2,2,3,4,4,5]
    assert [p['kind'] for p in packages[8:]]==['candidate_disposition','evidence_gap_resolution']
    assert [p['advisory_order'] for p in packages]==list(range(1,11))
    assert_final_roadmap_binding(report)
