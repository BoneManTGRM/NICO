"""Synthetic full-composition proof; no claims about an unrecovered production run."""
import base64
import io
import os
import re
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Spacer

from nico import comprehensive_report_package as report
from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from tests.test_client_pdf_compose_v2 import _pdf


def source_table():
    return {'structured_tables': [{'title': 'CC distribution test', 'columns': ['Measure', 'Value'],
        'rows': [[f'CC {i}: functions', i] for i in range(1, 41)]}]}


def test_heading_reserves_first_row_not_entire_batch(tmp_path):
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    flowables = report._source_pdf_tables(source_table(), spanish=False, width=doc.width)
    # Leave enough room for a heading/header and many rows, but not a full batch.
    doc.build([Spacer(1, 350), *flowables])
    source = stream.getvalue()
    from tests.test_sparse_reflow_section_flow import assert_text_geometry
    assert_text_geometry(source, tmp_path/'source-tables.pdf')
    source_pages = PdfReader(io.BytesIO(source)).pages
    assert 'CC 1: functions' in source_pages[0].extract_text()
    assert len(source_pages) == 2
    result = compose_compact_client_pdf(source, _pdf(['REGISTER_REQUIRED']), _pdf(['GATE_REQUIRED']),
        review_pdf=_pdf(['REVIEW_REQUIRED']), ci_boundary_pdf=_pdf(['CI_REQUIRED']),
        human_evidence_pdf=_pdf(['HUMAN_EVIDENCE_REQUIRED']))
    pages = PdfReader(io.BytesIO(result)).pages
    text = '\n'.join(page.extract_text() for page in pages)
    assert len(pages) == 7
    for i in range(1,41):
        assert len(re.findall(rf'CC {i}: functions\s+{i}\b', text)) == 1
    for marker in ['REGISTER_REQUIRED','GATE_REQUIRED','REVIEW_REQUIRED','CI_REQUIRED','HUMAN_EVIDENCE_REQUIRED']:
        assert text.count(marker) == 1
    # The compositor retains every source table drawing stream unchanged.
    for original, retained in zip(source_pages,pages):
        assert original.get_contents().get_data() == retained.get_contents().get_data()
    for page in source_pages:
        sizes=[]
        page.extract_text(visitor_text=lambda text,cm,tm,font,size: sizes.append(size) if text.strip() else None)
        assert min(sizes) >= 7.1


def test_short_table_heading_and_note_stay_with_only_row():
    stage={'structured_tables':[{'title':'ONE_ROW_TITLE','columns':['Measure','Value'],'rows':[['ONLY_ROW','VALUE']]}]}
    for space in (630,650):
        stream=io.BytesIO()
        doc=SimpleDocTemplate(stream,pagesize=letter,leftMargin=40,rightMargin=40,topMargin=40,bottomMargin=40)
        doc.build([Spacer(1,space),*report._source_pdf_tables(stage,spanish=False,width=doc.width)])
        for page in PdfReader(io.BytesIO(stream.getvalue())).pages:
            text=page.extract_text()
            if 'ONE_ROW_TITLE' in text:
                assert 'ONLY_ROW' in text and 'Showing all 1 rows in full.' in text


def test_measured_start_preserves_wrapped_first_row():
    # Font registration is process-global: exercise the production embedded fonts
    # in a fresh interpreter, independent of earlier renderer installers.
    root=Path(__file__).resolve().parents[1]
    env={**os.environ, 'PYTHONPATH':os.pathsep.join([str(root),str(root/'tests')])}
    subprocess.run([sys.executable, '-c', """
import io
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Spacer
from nico import comprehensive_report_package as report
from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1

install_comprehensive_pdf_embedded_fonts_v1()
expected='readable evidence '*60
stage={'structured_tables':[{'title':'WRAPPED_TITLE','columns':['Measure','Value'],
    'rows':[['WRAPPED_FIRST', expected],['LAST','final value']]}]}
stream=io.BytesIO()
doc=SimpleDocTemplate(stream,pagesize=letter,leftMargin=40,rightMargin=40,topMargin=40,bottomMargin=40)
doc.build([Spacer(1,600),*report._source_pdf_tables(stage,spanish=False,width=doc.width)])
texts=[page.extract_text() for page in PdfReader(io.BytesIO(stream.getvalue())).pages]
assert len(texts)==2
assert 'WRAPPED_TITLE' in texts[1] and 'WRAPPED_FIRST' in texts[1]
assert all('WRAPPED_FIRST' in text for text in texts if 'WRAPPED_TITLE' in text)
ordered=' '.join(' '.join(texts).split())
assert ordered.count('WRAPPED_FIRST')==ordered.count('LAST')==1
first_cell=ordered.split('WRAPPED_FIRST',1)[1].split('LAST',1)[0].strip()
# Extraction may insert line breaks inside a pair. Normalize whitespace only;
# exact equality still rejects any lost, duplicated, reordered or altered words.
assert first_cell==' '.join(expected.split())
assert ordered.split('LAST',1)[1].strip()=='final value Showing all 2 rows in full.'
"""], cwd=root,env=env,check=True,capture_output=True,text=True,timeout=30)


def test_actual_final_client_composition_uses_available_table_space(monkeypatch,tmp_path):
    # Production installers mutate process-global fonts/renderers. Run this
    # complete chain in isolation so its installation cannot affect other tests.
    target=Path(os.environ.get('PACKING_ARTIFACT_DIR',str(tmp_path)))
    root=Path(__file__).resolve().parents[1]
    env={**os.environ, 'MEASUREMENT_ARTIFACT_DIR':str(target),
         'PYTHONPATH':os.pathsep.join([str(root),str(root/'tests')])}
    subprocess.run([sys.executable, '-c', """
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_source_function_measurement_report_v1 import test_english_final_crossformat_and_artifacts
with MonkeyPatch.context() as patch, TemporaryDirectory() as temp:
    test_english_final_crossformat_and_artifacts(patch,Path(temp),40)
"""], cwd=root,env=env,check=True,capture_output=True,text=True,timeout=120)
    pdf=(target/'bins-40'/'report.pdf').read_bytes()
    assert len(PdfReader(io.BytesIO(pdf)).pages) <= 34
