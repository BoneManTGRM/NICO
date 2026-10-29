from copy import deepcopy
import pytest
from nico import comprehensive_client_truth_canonical_v2 as subject
from nico.report_json_copy import copy_with_tree_ownership
from tests.test_report_json_copy import _graph

def legacy(value):
    return copy_with_tree_ownership(value)[0], False

@pytest.mark.parametrize('shape', ['tree','alias','opaque','missing','malformed','foreign'])
@pytest.mark.parametrize('language',['en','es-MX'])
def test_local_boundary_preserves_nested_evidence_and_graph(monkeypatch,shape,language):
    evidence={'source_path':'/workspace/input/example.py', 'literal':'<arrow>',
              'commit_sha':'a'*40,'source_reference':{'commit_sha':'b'*40},
              'records':[{'line':7,'value':'Client Delivery Blocked'}]}
    source={'identity':{'report_language':language},'assessment':{'technical_score':97},
            'stage_summaries':[{'stage_id':'architecture_and_data_flow','evidence':[' retained '],
                               'source_observation':evidence},
                              {'stage_id':'developer_delivery_process','evidence':[' original '],
                               'source_observation':{'other':'retained'}}],
            'human_review_required':True,'client_delivery_allowed':False}
    if shape=='alias':source['external_alias']=evidence
    if shape=='opaque':source['opaque']=bytearray(b'unchanged')
    if shape=='missing':source.pop('assessment')
    if shape=='malformed':source['stage_summaries'].extend([None,'invalid',42])
    if shape=='foreign':source['identity']['commit_sha']='f'*40
    before=deepcopy(source)
    with monkeypatch.context() as patch:
        patch.setattr(subject,'copy_with_tree_ownership',legacy)
        expected=subject._normalize_stage_truth(source)
    actual=subject._normalize_stage_truth(source)
    assert actual==expected and _graph(actual)==_graph(expected)
    assert source==before
    assert actual['stage_summaries'][0]['source_observation']==evidence
    actual['stage_summaries'][0]['source_observation']['records'][0]['line']=100
    assert actual['assessment']['stage_summaries'][0]['source_observation']['records'][0]['line']==7
    assert source==before

@pytest.mark.parametrize('language',['en','es-MX'])
def test_installed_artifacts_equal_with_private_evidence(monkeypatch,language):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    from nico import phase17_canonical_artifact_rebuild_v1 as phase
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    source={'json':_fixed_status(language)['reports']['json']}
    reg=_install_finalized_scanner_register(source['json'])
    reg['totals']={'raw':1,'review_required':1,'source_path':1}
    reg['summary_by_category']={'static':dict(reg['totals'])}
    source['json']['stage_summaries']=[{'stage_id':'architecture_and_data_flow','status':'complete',
        'title':'Architecture and Data Flow','summary':'Synthetic retained source evidence.',
        'findings':[],'unavailable':[],
        'evidence':['Synthetic source evidence'], 'source_observation':{'commit_sha':'a'*40,
        'components':[{'path':'example.py','line':1}], 'literal':'<arrow>'}}]
    before=deepcopy(source)
    with monkeypatch.context() as patch:
        patch.setattr(subject,'copy_with_tree_ownership',legacy)
        expected=phase.rebuild_client_artifacts(source)
    actual=phase.rebuild_client_artifacts(source)
    assert actual==expected
    _validate_exact_artifact_hashes(actual)
    damaged=deepcopy(actual)
    damaged['markdown'] += '\nTampered artifact\n'
    with pytest.raises(ValueError):
        _validate_exact_artifact_hashes(damaged)
    assert source==before
    assert actual['human_review_required'] is True
    assert actual['client_delivery_allowed'] is False

@pytest.mark.parametrize('corruption',['duplicate_id','raw_total'])
def test_installed_population_rejections_unchanged(monkeypatch,corruption):
    from tests.test_v2_premium_report_renderer import _package
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    from nico import phase17_canonical_artifact_rebuild_v1 as phase
    source=_package('es-MX')
    reg=_install_finalized_scanner_register(source['json'])
    reg['totals']={'raw':1,'review_required':1,'source_path':1}
    reg['summary_by_category']={'static':dict(reg['totals'])}
    if corruption=='duplicate_id':reg['findings'].append(deepcopy(reg['findings'][0]))
    else:reg['totals']['raw']=2
    before=deepcopy(source)
    with monkeypatch.context() as patch:
        patch.setattr(subject,'copy_with_tree_ownership',legacy)
        with pytest.raises(ValueError) as expected:phase.rebuild_client_artifacts(source)
    with pytest.raises(ValueError) as actual:phase.rebuild_client_artifacts(source)
    assert str(actual.value)==str(expected.value)
    assert source==before
