import base64
import hashlib
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
from nico.comprehensive_four_phase_report_v1 import finalize_four_phase_report_package
from tests.test_comprehensive_four_phase_report_v1 import _canonical, _package


def fixture_pdf(spanish, outline=True, dedicated=False):
    qa='QA funcional' if spanish else 'Functional QA'
    professional='Evaluación profesional ampliada' if spanish else 'Broader Professional Assessment'
    toc='Tabla de contenido' if spanish else 'Table of Contents'
    texts=['NICO Comprehensive',toc+'\n'+qa,toc+' 2\n'+qa,
           qa+' unavailable', 'Review-Required Candidate Register',
           professional if dedicated else 'Evidence boundary',qa,
           'Human Review and Exact-Artifact Approval Record']
    stream=io.BytesIO();pdf=canvas.Canvas(stream,invariant=1)
    for text in texts:
        for index,line in enumerate(text.splitlines()): pdf.drawString(50,740-20*index,line)
        pdf.showPage()
    pdf.save()
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(stream.getvalue())))
    if outline:
        parent=writer.add_outline_item('Canonical sections',4)
        writer.add_outline_item(qa,6,parent=parent)
        if dedicated: writer.add_outline_item(professional,5,parent=parent)
    result=io.BytesIO();writer.write(result)
    return result.getvalue()


def destinations(reader):
    found={}
    def visit(items):
        for item in items:
            if isinstance(item,list): visit(item)
            else: found[str(item.title)]=reader.get_destination_page_number(item)
    visit(reader.outline)
    return found


@pytest.mark.parametrize('language',['en','es-MX'])
@pytest.mark.parametrize('outline,dedicated,expected',[(True,False,6),(True,True,5),(False,False,6),(False,True,5)])
def test_phase_three_uses_section_not_summary_or_toc(language,outline,dedicated,expected):
    canonical=_canonical(language=language);before=deepcopy(canonical)
    source=fixture_pdf(language=='es-MX',outline,dedicated)
    rendered=apply_four_phase_pdf(source,canonical)
    reader=PdfReader(io.BytesIO(rendered));targets=destinations(reader)
    title='Evaluación profesional ampliada' if language=='es-MX' else 'Broader Professional Assessment'
    assert targets[title]==expected
    assert len(reader.pages)==8
    original=PdfReader(io.BytesIO(source))
    for index in (0,2,3,4,5,6,7):
        assert reader.pages[index].extract_text()==original.pages[index].extract_text()
    assert canonical==before
    assert apply_four_phase_pdf(rendered,canonical)==rendered
    # All other phase destinations retain the original first-match behavior.
    assert targets['Automated Technical Triage' if language=='en' else 'Triaje técnico automatizado']==4
    assert targets['Human Review by Exception' if language=='en' else 'Revisión humana por excepción']==4
    assert targets['Approval and Client Delivery' if language=='en' else 'Aprobación y entrega al cliente']==7


@pytest.mark.parametrize('language',['en','es-MX'])
def test_finalizer_binds_final_navigation_bytes(language):
    package=_package(_canonical(language=language))
    package['pdf_base64']=base64.b64encode(fixture_pdf(language=='es-MX')).decode()
    result=finalize_four_phase_report_package(package)
    body=base64.b64decode(result['pdf_base64'])
    assert result['pdf_sha256']==hashlib.sha256(body).hexdigest()
    assert result['client_delivery_allowed'] is False
    assert finalize_four_phase_report_package(deepcopy(result))['pdf_base64']==result['pdf_base64']


@pytest.mark.parametrize('spanish',[False,True])
def test_phase_three_rejects_toc_outline_destination(spanish):
    source=fixture_pdf(spanish,outline=False)
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(source)))
    writer.add_outline_item('QA funcional' if spanish else 'Functional QA',2)
    output=io.BytesIO();writer.write(output)
    rendered=apply_four_phase_pdf(output.getvalue(),_canonical(language='es-MX' if spanish else 'en'))
    title='Evaluación profesional ampliada' if spanish else 'Broader Professional Assessment'
    assert destinations(PdfReader(io.BytesIO(rendered)))[title]==6
