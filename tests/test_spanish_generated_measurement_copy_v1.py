"""Owned generated copy through the installed worker translation surfaces."""
from copy import deepcopy
import pytest

from nico import comprehensive_spanish_canonical_report_v87 as spanish
from nico.source_function_measurement_report_v1 import LIMITS, UNAVAILABLE

CASES = [
    (LIMITS, 'Las observaciones se refieren'),
    (UNAVAILABLE, 'Mediciones de funciones no disponibles'),
    ('Function measurement scope', 'Alcance de las mediciones de funciones'),
    ('CC measured functions', 'Funciones medidas de CC'),
    ('NESTING at least 5: functions', 'ANIDAMIENTO de al menos 5: funciones'),
    ('CC 21: functions', 'CC 21: funciones'),
    ('CC distribution — Complete observed population: python / python_ast', 'Distribución de CC — Población observada completa: python / python_ast'),
    ('Excluded from scope', 'Excluido del alcance'),
]
def check_installed_worker_translates_authored_copy(source, expected):
    result = spanish._translate_presentation(source)
    assert expected in result
    if source == LIMITS:
        for token in ('CC<=20', 'sum(CC-1)', 'Python'):
            assert token in result
        for english in ('Observations concern', 'Whole-source decision burden', 'Existing scored-subset'):
            assert english not in result


def check_stage_limitation_survives_spanish_render_input_projection():
    canonical={'identity':{},'assessment':{},'stage_summaries':[
        {'stage_id':'functional_qa','title':'Functional QA','status':'complete',
         'summary':'Repository tests do not establish production user journeys.',
         'unavailable':['Repository tests do not establish production user journeys.']},
    ]}
    before=deepcopy(canonical)
    _,_,stages,_=spanish._render_inputs(canonical)
    heading=spanish._translate_presentation(stages[0]['status'].upper())
    assert heading=='PROCESAMIENTO COMPLETO · EVIDENCIA LIMITADA'
    assert canonical==before


def check_supplied_literals_remain_exact_even_when_equal_to_registered_copy():
    values={'customer_name':'Excluded from scope','authorized_scope':LIMITS,
            'source_excerpt':'CC 21: functions', 'path':'Function measurement scope'}
    assert spanish._localize_tree(values)==values
    line='Client-supplied data · Statement: pdf_page_count=7'
    canonical={'identity':{},'assessment':{},'stage_summaries':[
        {'stage_id':'client_human_evidence_functional_qa','status':'complete',
         'evidence':[line],
         'unavailable':['Repository tests do not establish production user journeys.']},
    ]}
    original=deepcopy(canonical)
    _,_,stages,_=spanish._render_inputs(canonical)
    assert stages[0]['evidence'][0].endswith('Statement: pdf_page_count=7')
    assert 'PDF page count' not in stages[0]['evidence'][0]
    assert canonical==original


def test_status_projection_never_rewrites_supplied_evidence_or_summary(monkeypatch):
    canonical={'identity':{},'assessment':{},'stage_summaries':[
        {'stage_id':'client_human_evidence_functional_qa','status':'complete',
         'summary':'Owned summary pdf_page_count=7',
         'evidence':['Client-supplied data · Statement: pdf_page_count=7',
                     'Deployments: 2/3 successful.'],
         'unavailable':['Owned limitation'], 'findings':['Owned finding pdf_page_count=7']},
    ]}
    original=deepcopy(canonical)
    # Isolate the pre-localization projection: unrelated authored translators
    # must receive the original values, including adversarial page-count copy.
    monkeypatch.setattr(spanish,'_localize_tree',lambda value, **kwargs: deepcopy(value))
    _,_,stages,_=spanish._render_inputs(canonical)
    expected=deepcopy(original['stage_summaries'])
    expected[0]['status']='processing complete · evidence limited'
    assert stages==expected
    assert canonical==original


def check_real_spanish_markdown_pdf_preserve_authored_qualifiers_and_client_literals():
    import io
    from pypdf import PdfReader
    from tests.test_v2_premium_report_renderer import _package
    canonical = _package('es-MX')['json']
    canonical['identity']['customer_name'] = 'Excluded from scope'
    canonical['stage_summaries'] = [{
        'stage_id':'functional_qa','title':'Functional QA','status':'complete',
        'summary':'Repository tests do not establish production user journeys.',
        'evidence':[LIMITS, 'Excluded from scope', 'Function measurement scope'], 'findings':[],
        'unavailable':['Repository tests do not establish production user journeys.'],
        'structured_tables':[{'title':'Function measurement scope','columns':['Measure','Value'],
            'rows':[['Limitations',LIMITS], ['Status','Excluded from scope'],
                    ['CC 21: functions',3]]}],
    }]
    before = deepcopy(canonical)
    markdown = spanish.render_spanish_markdown(canonical)
    pdf, pages = spanish.render_spanish_pdf(canonical)
    reader = PdfReader(io.BytesIO(pdf))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert pages == len(reader.pages)
    for output in (markdown,text):
        compact = ' '.join(output.split())
        assert 'PROCESAMIENTO COMPLETO · EVIDENCIA LIMITADA' in compact
        assert 'Alcance de las mediciones de funciones' in compact
        assert 'Las observaciones se refieren' in compact
        assert 'Excluido del alcance' in compact
        assert 'Excluded from scope' in compact  # explicitly supplied client name
    assert canonical == before


def test_installed_worker_generated_copy_and_rendering_in_isolation(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    script = """
from nico.api import final_report_worker_bootstrap
import runpy
suite = runpy.run_path('tests/test_spanish_generated_measurement_copy_v1.py')
for source, expected in suite['CASES']:
    suite['check_installed_worker_translates_authored_copy'](source, expected)
suite['check_stage_limitation_survives_spanish_render_input_projection']()
suite['check_supplied_literals_remain_exact_even_when_equal_to_registered_copy']()
suite['check_real_spanish_markdown_pdf_preserve_authored_qualifiers_and_client_literals']()
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=root,
                            env=owned_worker_environment(root, tmp_path, os.environ),
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_pdf_tables_translate_only_authored_measurement_cells():
    import io
    from reportlab.platypus import SimpleDocTemplate
    from pypdf import PdfReader
    from nico.comprehensive_report_package import _source_pdf_tables
    stage = {'structured_tables':[{
        'title':'Function measurement scope', 'columns':['Measure','Value'],
        'literal_value_labels':['Supplied literal'],
        'rows':[['Limitations',LIMITS],['Status','Excluded from scope'],
                ['CC 21: functions',3],['Supplied literal','Excluded from scope']],
    }]}
    original=deepcopy(stage)
    output=io.BytesIO()
    SimpleDocTemplate(output).build(_source_pdf_tables(stage,spanish=True,width=450))
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(output.getvalue())).pages).split())
    assert 'Alcance de las mediciones de funciones' in text
    assert 'Las observaciones se refieren' in text
    assert 'Excluido del alcance' in text
    assert 'Excluded from scope' in text
    assert 'CC 21: funciones' in text
    assert 'Observations concern' not in text
    assert stage==original
