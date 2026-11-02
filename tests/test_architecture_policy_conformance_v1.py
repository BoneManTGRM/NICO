from copy import deepcopy
import io

import pytest
from pypdf import PdfReader
from reportlab.platypus import SimpleDocTemplate

from nico.architecture_policy_conformance_v1 import KEY, VERSION, build_policy
from nico.source_function_witness_v1 import current_witness
from nico.comprehensive_native_providers import architecture_data_flow_provider
from nico import comprehensive_report_package as report
from test_source_function_measurement_report_v1 import collected
from source_function_witness_fixture import persist_parser_population


def function(name='f', cc=1):
    return f'def {name}(x):\n'+'    if x: pass\n'*(cc-1)+'    return x\n'


def policy(inputs):
    return build_policy(*inputs, witness=current_witness())


def test_complete_pass_and_no_authority(monkeypatch,tmp_path):
    inputs=collected(monkeypatch,tmp_path,function(cc=20));before=deepcopy(inputs)
    value=policy(inputs)
    assert value['counts']=={'pass':2,'fail':0,'unknown':0,'not_applicable':0}
    assert value['conformance_percentage']==100 and value['critical_status']=='clear'
    assert value['version']==VERSION and value['identity']['snapshot_commit_sha']==inputs[0]['commit_sha']
    assert inputs==before
    assert all(value[k] is False for k in ('included_in_overall_maturity','architecture_quality_established','delivery_velocity_established','changes_acceptance_authority'))
    assert 'complexity_score' not in value


@pytest.mark.parametrize('damage',['missing','partial','wrong_identity','contradictory','untrusted'])
def test_unknown_never_shrinks_denominator(monkeypatch,tmp_path,damage):
    from nico.source_function_measurements_v1 import KEY as MEASUREMENTS
    inputs=collected(monkeypatch,tmp_path,function())
    if damage=='missing':del inputs[2][MEASUREMENTS]
    elif damage=='partial':inputs[2]['profile_coverage']['inventory_complete']=False
    elif damage=='wrong_identity':inputs[0]['customer_id']='wrong'
    elif damage=='contradictory':inputs[2][MEASUREMENTS]['aggregate']['function_count']+=1
    value=build_policy(*inputs,witness={'verified':True} if damage=='untrusted' else current_witness())
    assert value['counts']=={'pass':0,'fail':0,'unknown':2,'not_applicable':0}
    assert value['normative_denominator']==2 and value['conformance_percentage'] is None
    assert value['status']=='incomplete' and value['critical_status']=='unknown'


def test_verified_empty_is_na_not_perfect(monkeypatch,tmp_path):
    inputs=collected(monkeypatch,tmp_path,'x=1\n')
    value=policy(inputs)
    assert value['counts']=={'pass':0,'fail':0,'unknown':0,'not_applicable':2}
    assert value['status']=='not_applicable' and value['conformance_percentage'] is None
    assert all(r['reason']=='verified_empty_eligible_function_population' for r in value['rules'])


def test_critical_failure_cannot_be_diluted(monkeypatch,tmp_path):
    results=[]
    for suffix in ('',''.join(function('trivial'+str(i)) for i in range(1000))):
        results.append(policy(collected(monkeypatch,tmp_path,function(cc=21)+suffix)))
    for value in results:
        assert value['counts']=={'pass':1,'fail':1,'unknown':0,'not_applicable':0}
        assert value['conformance_percentage']==50 and value['critical_status']=='blocked'
        assert value['critical_failure_count']==1 and value['rules'][0]['violations']==1
        assert value['sum_cc_minus_1']==20


def test_partial_dimension_keeps_critical_failure(monkeypatch,tmp_path):
    from nico.full_assessment_complexity_evidence import _analyze_python
    source=function(cc=21);inputs=collected(monkeypatch,tmp_path,source)
    analysis=_analyze_python('src/a.py',source);analysis['functions'][0]['max_nesting']=None
    persist_parser_population(monkeypatch,tmp_path,inputs,{'src/a.py':source},[analysis],{})
    value=policy(inputs)
    assert value['counts']=={'pass':0,'fail':1,'unknown':1,'not_applicable':0}
    assert value['conformance_percentage'] is None and value['critical_status']=='blocked'
    assert value['normative_denominator']==2


@pytest.mark.parametrize('spanish',[False,True])
def test_real_collection_provider_markdown_html_pdf_and_identity(monkeypatch,tmp_path,spanish):
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    inputs=collected(monkeypatch,tmp_path,function(cc=21))
    result=architecture_data_flow_provider(inputs[0]);value=result['evidence'][KEY]
    stage=report._stage_summary('architecture_and_data_flow',result)
    before=deepcopy(stage)
    assert stage[KEY]==value and _localize_tree(stage)[KEY]==value
    title='Conformidad con la política de arquitectura' if spanish else 'Architecture policy conformance'
    markdown='\n'.join(report._source_markdown(stage,spanish=spanish))
    html=report._semantic_html(markdown,'Synthetic policy proof')
    pdf=io.BytesIO();SimpleDocTemplate(pdf).build(report._source_pdf_tables(stage,spanish=spanish,width=450))
    text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf.getvalue())).pages)
    for rendered in (markdown,html,text):
        assert title in rendered
        assert ('Política bloqueada' if spanish else 'Policy critical blocked') in rendered
        assert '50.0%' in rendered
    assert stage==before
    assert value['included_in_overall_maturity'] is False


def test_projection_leaves_existing_scores_and_delivery_unchanged(monkeypatch,tmp_path):
    from nico.comprehensive_native_providers_v3 import _immutable_delivery_score
    from tests.test_client_report_completion_v2 import _package
    canonical=_package()['json'];before=deepcopy(canonical['assessment'])
    inputs=collected(monkeypatch,tmp_path,function())
    canonical['stage_summaries']=[report._stage_summary('architecture_and_data_flow',architecture_data_flow_provider(inputs[0]))]
    assert canonical['assessment']==before
    assert _immutable_delivery_score(None,100,{}, {})[0] is None
    assert 'complexity_score' not in inputs[2]
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_native_providers_v4 as scoring
    monkeypatch.setattr(providers,'_scan',lambda _: {'status':'complete',
                        'actual_commit_sha':inputs[0]['commit_sha'],'scanner_results':[]})
    before_score=scoring.canonical_scoring_provider(inputs[0])
    inputs[0]['prior_stage_results']['architecture_and_data_flow']=architecture_data_flow_provider(inputs[0])
    after_score=scoring.canonical_scoring_provider(inputs[0])
    assert before_score['assessment']['score_contract']
    assert after_score['assessment']['score_contract']==before_score['assessment']['score_contract']
    assert after_score['assessment']['sections']==before_score['assessment']['sections']
    assert after_score==before_score
    for section in after_score['assessment']['sections']:
        if section['id'] in ('architecture_debt','velocity_complexity'):
            assert section['presented_score'] is None


@pytest.mark.parametrize('depth',[4,5])
def test_nesting_boundary_is_noncritical_policy_rule(monkeypatch,tmp_path,depth):
    source='def f(x):\n'+''.join('    '*(i+1)+'if x:\n' for i in range(depth))+'    '*(depth+1)+'return x\n'
    value=policy(collected(monkeypatch,tmp_path,source))
    assert value['rules'][1]['status']==('pass' if depth==4 else 'fail')
    assert value['critical_status']=='clear'
    assert value['conformance_percentage']==(100 if depth==4 else 50)


@pytest.mark.parametrize('spanish',[False,True])
def test_final_artifacts_preserve_policy_and_existing_acceptance(monkeypatch,tmp_path,spanish):
    import base64
    import test_source_architecture_profile_evidence as fixture
    from test_source_profile_final_rendering import collected_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
    from nico.comprehensive_pdf_layout_polish_v1 import install_comprehensive_pdf_layout_polish_v1
    from nico.comprehensive_spanish_canonical_report_v87 import render_spanish_markdown, render_spanish_pdf
    install_comprehensive_pdf_embedded_fonts_v1();install_comprehensive_pdf_layout_polish_v1()
    monkeypatch.setattr(fixture,'FILES',{'src/a.py':function(cc=21)})
    package,_=collected_package(monkeypatch,tmp_path,spanish=spanish)
    canonical=package['json'];assessment=deepcopy(canonical['assessment']);value=deepcopy(canonical['stage_summaries'][1][KEY])
    if spanish:
        package['markdown']=render_spanish_markdown(canonical)
        pdf,_=render_spanish_pdf(canonical)
        package['pdf_base64']=base64.b64encode(pdf).decode()
    else:
        package['markdown']=report._markdown(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
        package['pdf_base64'],error,_=report._pdf(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
        assert not error
    baseline=deepcopy(package)
    for stage in baseline['json']['stage_summaries']:
        stage.pop(KEY,None)
        stage['structured_tables']=[t for t in stage.get('structured_tables',[])
                                    if not t['title'].startswith('Architecture policy')]
    baseline_result=rebuild_client_artifacts(baseline)
    result=rebuild_client_artifacts(package)
    assert result['json']['stage_summaries'][1][KEY]==value
    # Compare scoring contracts after the same intended presentation normalization.
    expected_assessment=baseline_result['json']['assessment']
    actual_assessment=result['json']['assessment']
    assert actual_assessment.get('overall_score')==expected_assessment.get('overall_score')
    assert actual_assessment.get('score_contract')==expected_assessment.get('score_contract')
    score_fields=('score','source_score','presented_score','score_value','technical_score',
                  'technical_score_display','exclude_from_maturity','weight')
    def section_scores(assessment):
        assert assessment['sections']
        return [(section.get('id'),{k:section[k] for k in score_fields if k in section})
                for section in assessment['sections']]
    assert section_scores(actual_assessment)==section_scores(expected_assessment)
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes, _artifact_bytes
    import hashlib
    _validate_exact_artifact_hashes(result)
    assert result['artifact_manifest']['artifacts']
    for artifact in result['artifact_manifest']['artifacts']:
        content=_artifact_bytes(result,artifact['artifact_type'])
        assert hashlib.sha256(content).hexdigest()==artifact['sha256']
        assert len(content)==artifact['size_bytes']
    tampered=deepcopy(result);tampered['markdown']+='\nchanged'
    with pytest.raises(ValueError,match='SHA-256 mismatch'):
        _validate_exact_artifact_hashes(tampered)
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
    text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    for surface in (result['markdown'],result['html'],text):
        assert ('Conformidad con la política de arquitectura' if spanish else 'Architecture policy conformance') in surface
        assert ('Política bloqueada' if spanish else 'Policy critical blocked') in surface


@pytest.mark.parametrize('spanish',[False,True])
def test_partial_nesting_retains_observed_failure_and_population(monkeypatch,tmp_path,spanish):
    from nico.full_assessment_complexity_evidence import _analyze_python
    source='def deep(x):\n'+''.join('    '*(i+1)+'if x:\n' for i in range(5))+'                        return x\n'+function('other')
    inputs=collected(monkeypatch,tmp_path,source)
    analysis=_analyze_python('src/a.py',source)
    assert analysis['functions'][0]['max_nesting']==5
    analysis['functions'][1]['max_nesting']=None
    persist_parser_population(monkeypatch,tmp_path,inputs,{'src/a.py':source},[analysis],{})
    value=policy(inputs);row=value['rules'][1]
    assert row['status']=='unknown' and row['violations'] is None
    assert row['observed_violations']==1
    assert row['measured_functions']==1 and row['total_functions']==2
    assert value['counts']=={'pass':1,'fail':0,'unknown':1,'not_applicable':0}
    assert value['conformance_percentage'] is None and value['normative_denominator']==2
    result=architecture_data_flow_provider(inputs[0])
    stage=report._stage_summary('architecture_and_data_flow',result)
    assert stage[KEY]==value
    markdown='\n'.join(report._source_markdown(stage,spanish=spanish))
    html=report._semantic_html(markdown,'Partial policy')
    pdf=io.BytesIO();SimpleDocTemplate(pdf).build(report._source_pdf_tables(stage,spanish=spanish,width=450))
    text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf.getvalue())).pages)
    for surface in (markdown,html,text):
        normalized=' '.join(surface.split())
        assert '1 / 2' in normalized
        assert ('Incumplimientos observados' if spanish else 'Observed violations') in normalized
        assert ('no son exhaustivos' if spanish else 'not exhaustive') in normalized
        assert ('Sin porcentaje calificado' if spanish else 'No qualified percentage') in normalized
    # Bind the displayed observed count and denominator to the same rule row.
    tables=result['evidence']['structured_tables']
    rules=next(t for t in tables if t['title']=='Architecture policy rules')
    assert rules['rows'][1][1]=='Policy unknown'
    assert rules['rows'][1][3:5]==[1,'1 / 2']


@pytest.mark.parametrize('dimension,threshold',[('cc',19),('nesting',3)])
def test_policy_threshold_drift_fails_closed(monkeypatch,tmp_path,dimension,threshold):
    from nico import architecture_policy_conformance_v1 as module
    inputs=collected(monkeypatch,tmp_path,function(cc=20))
    monkeypatch.setattr(module,'RULES',tuple((rid,dim,threshold if dim==dimension else limit,critical)
                                           for rid,dim,limit,critical in module.RULES))
    value=policy(inputs)
    row=next(r for r in value['rules'] if r['rule_id']==('function_cc_max_20' if dimension=='cc' else 'function_nesting_max_4'))
    assert row['status']=='unknown' and row['reason']=='source_policy_threshold_mismatch'
    assert row['source_threshold']==(20 if dimension=='cc' else 4)
    assert row['threshold']==threshold
    assert row['observed_violations'] is None and row['violations'] is None
    assert value['conformance_percentage'] is None and value['normative_denominator']==2
