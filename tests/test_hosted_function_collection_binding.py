"""Synthetic provider collection and real disposable persistence; no external inputs."""
from copy import deepcopy

import pytest

from nico import typescript_ast_complexity_v1 as collector
from nico.architecture_policy_conformance_v1 import build_policy
from nico.source_function_collection_v1 import KEY_COLLECTION, validate_collection
from nico.source_function_measurements_v1 import KEY
from nico.source_function_witness_v1 import load_witness
from source_function_witness_fixture import persisted, architecture_from_persisted
from test_source_architecture_profile_evidence import collect


def collected(monkeypatch, tmp_path, *, text='def f(x):\n    if x: return 1\n    return 0\n', truncated=False):
    collector.install_typescript_ast_complexity_v1()
    return collect('hosted', monkeypatch, tmp_path, files={'src/a.py': text}, truncated=truncated)


def test_hosted_collection_binds_before_evidence_persistence(monkeypatch, tmp_path):
    context, repo, complexity, storage = collected(monkeypatch, tmp_path)
    assert complexity[KEY]['identity'] is not None
    assert validate_collection(complexity)
    assert complexity[KEY_COLLECTION]['identity'] == complexity[KEY]['identity']
    assert storage.get('evidence_items', complexity['evidence_id'])['evidence'] == complexity
    assert complexity['human_review_required'] is True
    assert complexity['client_delivery_allowed'] is False
    assert 'complexity_score' not in complexity
    assert 'architecture_policy_conformance_v1' not in complexity


@pytest.mark.parametrize('conditions,expected', [(0, 'meets_policy'), (20, 'fails_policy')])
def test_existing_trusted_reader_qualifies_hosted_collection(monkeypatch, tmp_path, conditions, expected):
    text='def f(x):\n'+'    if x: pass\n'*conditions+'    return 0\n'
    context, repo, complexity, _ = collected(monkeypatch, tmp_path, text=text)
    store, _, witness = persisted(context, repo, complexity, tmp_path)
    assert witness is not None
    assert load_witness(store, context) is not None
    result=architecture_from_persisted(context, repo, complexity, tmp_path)['evidence']['architecture_policy_conformance_v1']
    assert result['status'] == expected
    assert result['architecture_quality_established'] is False
    assert result['delivery_velocity_established'] is False
    assert result['changes_acceptance_authority'] is False
    assert build_policy(context, repo, complexity, witness={'verified': True})['status']=='incomplete'


@pytest.mark.parametrize('damage', ['measurement_omission', 'source_hash', 'tool_hash', 'coverage', 'tenant', 'commit'])
def test_hosted_witness_cannot_authorize_changed_context(monkeypatch, tmp_path, damage):
    context, repo, complexity, _ = collected(monkeypatch, tmp_path)
    _, _, witness = persisted(context, repo, complexity, tmp_path)
    assert witness is not None
    context, repo, complexity = deepcopy((context, repo, complexity))
    if damage=='measurement_omission': complexity[KEY]['files']=[]
    elif damage=='source_hash': complexity[KEY]['files'][0]['source_text_sha256']='f'*64
    elif damage=='tool_hash': complexity[KEY]['producer_source_sha256']={k:'f'*64 for k in complexity[KEY]['producer_source_sha256']}
    elif damage=='coverage': complexity['profile_coverage']['analyzed_source_paths']=[]
    elif damage=='tenant': context['customer_id']='other'
    elif damage=='commit': context['commit_sha']='f'*40
    assert build_policy(context, repo, complexity, witness=witness)['status']=='incomplete'


@pytest.mark.parametrize('damage',['incomplete_inventory','parse_failure'])
def test_persisted_hosted_unknowns_remain_unknown(monkeypatch, tmp_path, damage):
    context, repo, complexity, _ = collected(monkeypatch, tmp_path, text='def (' if damage=='parse_failure' else 'def f(): pass')
    if damage=='incomplete_inventory':
        for envelope in (repo['file_evidence'],complexity):
            envelope['profile_coverage']['inventory_complete']=False
            envelope['profile_coverage']['coverage_denominator_scope']='observed_paths_only'
    _, _, witness = persisted(context, repo, complexity, tmp_path)
    assert witness is not None  # Trusted persistence alone never supplies complete coverage.
    result=build_policy(context, repo, complexity, witness=witness)
    assert result['status']=='incomplete'
    assert result['conformance_percentage'] is None
    assert result['counts']['unknown']==2


def test_legacy_idempotent_record_is_not_rebound(monkeypatch, tmp_path):
    from nico import hosted_provider_comprehensive_runtime_v1 as hosted
    context, repo, complexity, storage = collected(monkeypatch, tmp_path)
    legacy=deepcopy(complexity)
    legacy[KEY]['identity']=None
    legacy.pop(KEY_COLLECTION)
    storage.get('evidence_items', complexity['evidence_id'])['evidence']=legacy
    monkeypatch.setattr(hosted,'checkout_hosted_provider_snapshot',lambda *a,**k:pytest.fail('legacy reuse acquired source'))
    snapshot=context['prior_stage_results']['immutable_repository_snapshot']['snapshot']
    reused_repo,reused=hosted.collect_hosted_provider_repository_evidence(context,snapshot,store=storage)
    assert reused['idempotent_reuse'] is True
    assert reused[KEY]['identity'] is None
    assert KEY_COLLECTION not in reused
    assert not validate_collection(reused)
    _,_,witness=persisted(context,reused_repo,reused,tmp_path)
    assert witness is None
    assert build_policy(context,reused_repo,reused,witness=witness)['status']=='incomplete'


def test_invalid_optional_contract_does_not_gain_authority(monkeypatch, tmp_path):
    from nico import hosted_provider_comprehensive_runtime_v1 as hosted
    collector.install_typescript_ast_complexity_v1()
    original=hosted.collect_complexity_evidence
    def malformed(files):
        result=original(files)
        result[KEY_COLLECTION]={'version':'unsupported'}
        return result
    monkeypatch.setattr(hosted,'collect_complexity_evidence',malformed)
    context,repo,complexity,_=collected(monkeypatch,tmp_path)
    assert KEY_COLLECTION not in complexity
    assert complexity['human_review_required'] is True
    assert complexity['client_delivery_allowed'] is False
    _,_,witness=persisted(context,repo,complexity,tmp_path)
    assert witness is None
