from copy import deepcopy
import hashlib
import io
import math

import pytest
from pypdf import PdfReader

from nico import comprehensive_pdf_layout_polish_v1 as polish
from nico import comprehensive_client_review_companion_v5 as v5
from tests.test_comprehensive_pdf_layout_polish_v1 import _review_canonical


LIST_FIELDS = ('evidence','findings','can_conclude','cannot_conclude','limitations','required_input','questions')


@pytest.mark.parametrize('spanish',[False,True])
def test_evidence_can_quote_decision_record_heading(spanish):
    canonical=_review_canonical()
    marker='Registro de decisión' if spanish else 'Decision record'
    evidence=f'Retained source contains literal {marker} for human review.'
    canonical['stage_summaries'][0]['evidence'].append(evidence)
    before=deepcopy(canonical)
    sections=v5.substantive_review_sections(canonical,spanish=spanish)
    assert any(evidence in section['evidence'] for section in sections)
    pdf=polish._render_polished_review_pdf(canonical,spanish=spanish)
    reader=PdfReader(io.BytesIO(pdf))
    text=' '.join(' '.join(page.extract_text() for page in reader.pages).split())
    assert evidence in text
    assert text.count(marker)==v5.SECTION_COUNT+1
    assert len(reader.outline)==v5.SECTION_COUNT
    assert canonical==before


@pytest.mark.parametrize('spanish',[False,True])
@pytest.mark.parametrize('damage',['omit','duplicate','wrong_section'])
def test_renderer_owned_decision_structure_remains_required(monkeypatch,spanish,damage):
    from reportlab.platypus import SimpleDocTemplate
    build=SimpleDocTemplate.build
    def damaged_build(document,story,*args,**kwargs):
        index=next(i for i,item in enumerate(story) if hasattr(item,'review_decision_section'))
        if damage=='omit':
            del story[index]
        elif damage=='duplicate':
            story.insert(index,story[index])
        else:
            story[index].review_decision_section='wrong_section'
        return build(document,story,*args,**kwargs)
    monkeypatch.setattr(SimpleDocTemplate,'build',damaged_build)
    with pytest.raises(ValueError,match='omitted or reordered a section decision record'):
        polish._render_polished_review_pdf(_review_canonical(),spanish=spanish)


def dense_sections(spanish):
    sections = deepcopy(v5.substantive_review_sections(_review_canonical(),spanish=spanish))
    for index, section in enumerate(sections):
        for field in ('summary','recommended_decision',*LIST_FIELDS):
            prefix=f'S{index}_{field}'
            long = prefix+'_BEGIN '+('evidencia íntegra café año revisión ' * 40)+prefix+'_END'
            section[field] = ([long]+[f'{prefix}_ITEM{item} finding-ID-{index}-{item}' for item in range(1,6)]
                              if field in LIST_FIELDS else long)
    sections[0]['evidence'].append('<literal attr="x"> & </literal> café año — “revisión”')
    sections[0]['evidence'].append('UNBROKEN_'+('Z'*1500)+'_ENDTOKEN')
    sections[0]['summary'] += ' '+('Long paragraph remains complete. '*180)+'PARAGRAPH_END'
    return sections


def compact(text):
    return ''.join(text.split())


@pytest.mark.parametrize('spanish',[False,True])
def test_all_projected_content_is_readable_ordered_and_continues(monkeypatch,spanish,tmp_path):
    sections=dense_sections(spanish);saved=deepcopy(sections)
    canonical=_review_canonical();before=deepcopy(canonical)
    monkeypatch.setattr(v5,'substantive_review_sections',lambda *a,**k:deepcopy(sections))
    pdf=polish._render_polished_review_pdf(canonical,spanish=spanish)
    (tmp_path/'dense.pdf').write_bytes(pdf)
    reader=PdfReader(io.BytesIO(pdf))
    pages=[page.extract_text() or '' for page in reader.pages]
    continuation='continuación' if spanish else 'continued'
    content=[]
    for page in pages:
        lines=page.splitlines()
        header_end=next((index for index,line in enumerate(lines[:6]) if continuation in line),None)
        if header_end is not None: lines=lines[header_end+1:]
        content.extend(line for line in lines if not line.startswith(('NICO |','Review page ','Página de revisión ','Human decision pending |','Decisión humana pendiente |')))
    text=compact(' '.join(content))
    # Every supplied field/item survives, including duplicates and material past
    # each former per-field character and list-population cap.
    for section in sections:
        for key,value in section.items():
            values=value if isinstance(value,list) else [value]
            cursor=0
            for item in values:
                item=str(item).lower() if isinstance(item,bool) else str(item)
                position=text.find(compact(item),cursor)
                assert position>=0,(section['id'],key,item[-80:])
                cursor=position+len(compact(item))
    assert sections==saved and canonical==before
    assert len(reader.pages)>8
    continuation='continuación' if spanish else 'continued'
    assert any(continuation in page for page in pages)
    for index,page in enumerate(pages,1):
        assert ('Decisión humana pendiente | Entrega bloqueada' if spanish else
                'Human decision pending | Client delivery blocked') in page
        assert (f'Página de revisión {index} de {len(pages)}' if spanish else
                f'Review page {index} of {len(pages)}') in page
        if continuation in page:
            header=page.split(continuation)[0]
            assert any(section['id'] in header and section['title'] in ' '.join(header.split()) for section in sections)
    for destination,section in zip(reader.outline,sections):
        index=reader.get_destination_page_number(destination)
        assert destination.title==section['title']
        assert f"ID: {section['id']}" in pages[index]
    assert len(reader.outline)==8
    effective=[]
    def visit(text,cm,tm,font,size):
        if text.strip():
            a,b=tm[0]*cm[0]+tm[1]*cm[2],tm[0]*cm[1]+tm[1]*cm[3]
            c,d=tm[2]*cm[0]+tm[3]*cm[2],tm[2]*cm[1]+tm[3]*cm[3]
            effective.append(size*min(math.hypot(a,b),math.hypot(c,d)))
    for page in reader.pages: page.extract_text(visitor_text=visit)
    assert effective and min(effective)>=9
    assert polish._render_polished_review_pdf(canonical,spanish=spanish)==pdf


def test_installer_and_late_rebinding_keep_flowing_renderer():
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v6 as v6
    from nico import comprehensive_client_review_companion_v7 as v7
    from nico.comprehensive_client_review_companion_v7_rebind import install_comprehensive_review_companion_v7_rebind
    polish.install_comprehensive_pdf_layout_polish_v1()
    state=install_comprehensive_review_companion_v7_rebind()
    assert state["page_count"] is None and state["sections_per_page"] is None
    assert completion.render_comprehensive_review_companion_pdf is polish._render_polished_review_pdf
    assert v6.render_compact_substantive_review_pdf is polish._render_polished_review_pdf
    assert v7.render_paired_substantive_review_pdf is polish._render_polished_review_pdf


def test_final_composition_accepts_60_and_rejects_61_without_dropping_review_pages():
    from tests.test_client_pdf_compose_v2 import _pdf
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    base,register,gate=_pdf(['Primary evidence']),_pdf(['Register']),_pdf(['Gate'])
    review=_pdf(*[[f'Review continuation {index}'] for index in range(57)])
    combined=compose_compact_client_pdf(base,register,gate,review_pdf=review)
    reader=PdfReader(io.BytesIO(combined))
    assert len(reader.pages)==60
    text=' '.join(page.extract_text() for page in reader.pages)
    assert all(f'Review continuation {index}' in text for index in range(57))
    with pytest.raises(ValueError,match='60-page boundary'):
        compose_compact_client_pdf(base,register,gate,review_pdf=_pdf(
            *[[f'Review continuation {index}'] for index in range(58)]))


def test_finalizer_refreshes_actual_counts_hashes_without_changing_review_authority(monkeypatch):
    import base64
    from tests.test_client_report_completion_v2 import _package
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v7_rebind as rebind
    from nico import comprehensive_client_review_companion_v7 as v7
    polish.install_comprehensive_pdf_layout_polish_v1()
    observed=[]
    def render(canonical,*,spanish):
        before=deepcopy(canonical)
        pdf=polish._render_polished_review_pdf(canonical,spanish=spanish)
        assert canonical==before
        observed.append((pdf,before))
        return pdf
    for module,name in ((completion,'render_comprehensive_review_companion_pdf'),
                        (rebind,'render_paired_substantive_review_pdf'),(v7,'render_paired_substantive_review_pdf')):
        monkeypatch.setattr(module,name,render)
    package=_package();saved=deepcopy(package)
    result=completion.finalize_client_report_package(package)
    assert package==saved
    body=base64.b64decode(result['pdf_base64'])
    assert result['pdf_sha256']==hashlib.sha256(body).hexdigest()
    assert body!=base64.b64decode(package['pdf_base64'])
    assert result['pdf_page_count']==len(PdfReader(io.BytesIO(body)).pages)
    assert result['client_report_completion']['comprehensive_review_companion_page_count']==len(PdfReader(io.BytesIO(observed[-1][0])).pages)
    assert all(result['json']['identity'][key]==value for key,value in observed[-1][1]['identity'].items())
    assert all(result['json']['assessment'][key]==value for key,value in observed[-1][1]['assessment'].items())
    assert result['json']['canonical_findings']==observed[-1][1]['canonical_findings']
    assert result['human_review_required'] is True
    assert result['human_review_completed'] is False
    assert result['client_delivery_allowed'] is False
    assert result['report_finality']=='automated_draft'


def test_unsupported_unicode_rejects_instead_of_silent_missing_glyph(monkeypatch):
    sections=dense_sections(False)
    sections[0]['evidence'].append('Unrenderable source glyph: 漢')
    monkeypatch.setattr(v5,'substantive_review_sections',lambda *a,**k:sections)
    with pytest.raises(ValueError,match=r'Unicode U\+6F22'):
        polish._render_polished_review_pdf(_review_canonical(),spanish=False)


@pytest.mark.parametrize('spanish',[False,True])
def test_dense_pdf_text_has_no_clipping_overlap_or_footer_collision(monkeypatch,tmp_path,spanish):
    import shutil,subprocess,xml.etree.ElementTree as ET
    binary=shutil.which('pdftotext')
    if binary is None: pytest.skip('Poppler geometry diagnostic unavailable')
    sections=dense_sections(spanish)
    monkeypatch.setattr(v5,'substantive_review_sections',lambda *a,**k:sections)
    path=tmp_path/'dense.pdf'
    path.write_bytes(polish._render_polished_review_pdf(_review_canonical(),spanish=spanish))
    result=subprocess.run([binary,'-bbox-layout',str(path),'-'],capture_output=True,text=True,check=True)
    for page in ET.fromstring(result.stdout).findall('.//{*}page'):
        boxes=[]
        for line in page.findall('.//{*}line'):
            box=tuple(float(line.attrib[k]) for k in ('xMin','yMin','xMax','yMax'))
            assert 41.9<=box[0]<box[2]<=570.1
            assert 0<=box[1]<box[3]<=774
            if box[1]>744: assert box[1]>=750
            for prior in boxes:
                assert (min(box[2],prior[2])-max(box[0],prior[0])<=.1 or
                        min(box[3],prior[3])-max(box[1],prior[1])<=.1)
            boxes.append(box)


@pytest.mark.parametrize('spanish',[False,True])
def test_final_navigation_targets_section_start_not_continuation(spanish):
    from pypdf import PdfWriter
    from tests.test_client_pdf_compose_v2 import _pdf
    from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline
    polish.install_comprehensive_pdf_layout_polish_v1()
    canonical=_review_canonical()
    sections=v5.substantive_review_sections(canonical,spanish=spanish)
    review=polish._render_polished_review_pdf(canonical,spanish=spanish)
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(_pdf(['NICO Comprehensive']))))
    writer.append(PdfReader(io.BytesIO(review)),import_outline=False)
    buffer=io.BytesIO();writer.write(buffer)
    final=PdfReader(io.BytesIO(semantic_renumber_and_outline(buffer.getvalue())))
    destinations={item.title:final.get_destination_page_number(item) for item in final.outline if not isinstance(item,list)}
    for section in sections:
        page=final.pages[destinations[section['title']]]
        assert 'ID: '+section['id'] in page.extract_text()
