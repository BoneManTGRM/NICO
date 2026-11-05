from copy import deepcopy
import base64
import io
import json

from pypdf import PdfReader

from nico import comprehensive_report_package as report
from nico.comprehensive_native_providers import architecture_data_flow_provider, canonical_scoring_provider
from nico.source_function_conformance_v1 import KEY
from test_source_function_measurement_report_v1 import collected


def test_report_projection_does_not_change_scoring_or_source(monkeypatch,tmp_path):
    context,repo,complexity = collected(monkeypatch,tmp_path)
    from nico import comprehensive_native_providers as providers
    monkeypatch.setattr(providers, '_scan', lambda _: {'status':'complete', 'actual_commit_sha':context['commit_sha'], 'scanner_results':[]})
    baseline=deepcopy(context)
    score_before=canonical_scoring_provider(context)
    stage=architecture_data_flow_provider(context)
    score_after=canonical_scoring_provider(context)
    assert score_before['status'] == 'complete'
    assert score_before['assessment']['sections']
    assert score_after == score_before
    assert context == baseline
    assert complexity.get('complexity_score') is None
    value=stage['evidence'][KEY]
    assert value['status']=='qualified'
    summary=report._stage_summary('architecture_and_data_flow',stage)
    assert summary[KEY]==value
    assert not any('included_in_overall_maturity' in line for line in summary['evidence'])
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    from nico.v2_authoritative_premium_report import _sanitize_container
    assert _localize_tree({KEY:value}) == {KEY:value}
    assert _sanitize_container({KEY:value}, {'semgrep'}) == {KEY:value}


def test_final_crossformat_keeps_scoped_subscore_and_acceptance(monkeypatch,tmp_path):
    import test_source_architecture_profile_evidence as fixture
    from test_source_profile_final_rendering import collected_package
    from nico import typescript_ast_complexity_v1 as collector
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
    from nico.comprehensive_pdf_layout_polish_v1 import install_comprehensive_pdf_layout_polish_v1
    collector.install_typescript_ast_complexity_v1()
    install_comprehensive_pdf_embedded_fonts_v1()
    install_comprehensive_pdf_layout_polish_v1()
    monkeypatch.setattr(fixture,'FILES',{'src/a.py':'def a(x):\n'+'    if x: pass\n'*20+'    return 0\n'+'def b(): return 0\n'})
    package,_=collected_package(monkeypatch,tmp_path)
    canonical=package['json']
    value=deepcopy(canonical['stage_summaries'][1][KEY])
    assert value['combined']['cc']['percentage']==50.0
    package['markdown']=report._markdown(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
    encoded,error,_=report._pdf(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
    assert not error
    package['pdf_base64']=encoded
    baseline=deepcopy(package)
    stage=baseline['json']['stage_summaries'][1]
    stage.pop(KEY)
    stage['structured_tables']=[t for t in stage['structured_tables'] if not t['title'].startswith(('Function complexity conformance','Separate nesting<=4'))]
    expected=rebuild_client_artifacts(baseline)
    actual=rebuild_client_artifacts(package)
    assert actual['json']['stage_summaries'][1][KEY]==value
    def without_conformance(value):
        if isinstance(value, dict):
            return {k:without_conformance(v) for k,v in value.items() if k != KEY}
        if isinstance(value, list):
            return [without_conformance(v) for v in value if not (isinstance(v,dict) and str(v.get('title','')).startswith(('Function complexity conformance','Separate nesting<=4')))]
        return value
    assert without_conformance(actual['json']['assessment'])==without_conformance(expected['json']['assessment'])
    for key in ('human_review_required','client_delivery_allowed','client_ready','status'):
        assert actual.get(key)==expected.get(key)
    pdf=base64.b64decode(actual['pdf_base64'])
    text='\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages)
    for output in (actual['markdown'],actual['html'],text):
        assert 'Function complexity conformance' in output
        assert 'excluded from overall maturity' in output
        assert '50.0' in output
        assert 'Sum(CC-1)' in output
        assert 'CC at least 21: functions' in output
    for name,data in [('report.pdf',pdf),('report.json',json.dumps(actual['json'],indent=2).encode()),('report.md',actual['markdown'].encode()),('report.html',actual['html'].encode()),('pdf-text.txt',text.encode())]:
        (tmp_path/name).write_bytes(data)


def test_current_five_section_scoring_ignores_additive_conformance(monkeypatch,tmp_path):
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_native_providers_v4 as scoring
    context,_,complexity = collected(monkeypatch,tmp_path)
    monkeypatch.setattr(providers,'_scan',lambda _: {'status':'complete','actual_commit_sha':context['commit_sha'],'scanner_results':[]})
    before=scoring.canonical_scoring_provider(context)
    context['prior_stage_results']['architecture_and_data_flow']=architecture_data_flow_provider(context)
    after=scoring.canonical_scoring_provider(context)
    assert after==before
    sections=after['assessment']['sections']
    assert len([row for row in sections if isinstance(row.get('presented_score'),(int,float))])==5
    for key in ('architecture_debt','velocity_complexity'):
        section=next(row for row in sections if row['id']==key)
        assert section['presented_score'] is None
    assert complexity.get('complexity_score') is None


def test_integration_retains_every_observation_and_histogram_row(monkeypatch,tmp_path):
    from nico.source_function_measurement_report_v1 import measurement_tables
    from nico.source_function_conformance_report_v1 import integrate_conformance
    from test_source_function_conformance_v1 import build_conformance
    files={'a.py':'def a(x):\n'+'    if x: pass\n'*20+'    return 0\n'}
    for mixed in (False, True):
        if mixed:
            files['b.ts']='function b() { return 1; }'
        context,repo,complexity=collected(monkeypatch,tmp_path,files=files)
        original=measurement_tables(context,repo,complexity)
        commitment=deepcopy(original)
        value=build_conformance(context,repo,complexity)
        value_before=deepcopy(value)
        integrated=integrate_conformance(original,value)
        assert original==commitment and value==value_before
        for table in original:
            retained=next(t for t in integrated if t['title']==table['title'])
            assert retained['columns']==table['columns']
            expanded=dict(retained['rows'])
            aliases={
                'Supplied eligible source / complete observed files': ('Supplied eligible source files','Complete observed files'),
                'Partial observed / missing / unsupported files': ('Partial observed files','Missing files','Unsupported files'),
                'Functions (enumerated; measured: CC, NESTING, LOC)': ('Enumerated functions','CC measured functions','NESTING measured functions','LOC measured functions'),
                'Missing functions (CC, NESTING, LOC)': ('CC missing functions','NESTING missing functions','LOC missing functions'),
            }
            for compact, labels in aliases.items():
                if compact in expanded:
                    expanded.update({label:expanded[compact] for label in labels})
            for original_row in table['rows']:
                retained_row=[original_row[0],expanded[original_row[0]]]
                if original_row[0] in ('Limitations','Status'):
                    assert retained_row[0]==original_row[0] and retained_row[1].startswith(original_row[1])
                else:
                    assert retained_row==original_row
        summaries=[t for t in integrated if t['title'].startswith('Complete observed population:')]
        assert len(summaries)==len(value['languages'])
        for summary in summaries:
            assert sum(row[0]=='Sum(CC-1) in enumerated functions' for row in summary['rows'])==1
            assert sum(row[0]=='CC at least 21: functions' for row in summary['rows'])==1
            assert len([row for row in summary['rows'] if row[0].startswith('Function complexity conformance')])==1
        combined=[t for t in integrated if t['title'].endswith('combined descriptive totals')]
        if mixed:
            assert len(combined)==1
            assert integrated.index(combined[0]) > max(integrated.index(t) for t in summaries)
            combined_rows=dict(combined[0]['rows'])
            assert combined_rows['CC>20 absolute violations']==1
            assert combined_rows['Enumerated functions']==2
            assert combined_rows['Sum(CC-1) in enumerated functions']==20
        else:
            assert not combined
            assert summaries[0]['rows'][-1][0]=='Combined descriptive totals'
            assert 'Identical to the python complete population' in dict(summaries[0]['rows'])['Combined descriptive totals']
