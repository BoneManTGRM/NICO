"""Exercise the installed same-run pipeline, including late PDF sanitization."""
import subprocess
import sys

import pytest


@pytest.mark.parametrize('language',['en','es-MX'])
def test_installed_composition_preserves_complete_projected_worksheets(language):
    script = r'''
import base64,copy,io,math
from pypdf import PdfReader
from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
_install_production_wrappers()
from tests.test_comprehensive_report_package_v2 import _package
from nico import comprehensive_same_run_locale_report_v1 as route
from nico import comprehensive_client_review_companion_v5 as v5
from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
original=v5.substantive_review_sections
observed=[]
def projected(*args,**kwargs):
    sections=copy.deepcopy(original(*args,**kwargs))
    # Controlled projection fixture: add ordered evidence to each of the real
    # eight sections, without changing canonical truth or production selection.
    for index,section in enumerate(sections):
        section['evidence'].extend(f'WORKSHEET_{index}_EVIDENCE_{item}' for item in range(3))
    observed.append(copy.deepcopy(sections))
    return sections
v5.substantive_review_sections=projected
canonical=copy.deepcopy(_package()['report_package']['json'])
canonical.update(report_language=LANG,locale=LANG,generated_at='2026-08-04T16:15:00Z',generation_timestamp='2026-08-04T16:15:00Z')
canonical['identity'].update(report_language=LANG,locale=LANG,generated_at='2026-08-04T16:15:00Z')
canonical['assessment']['report_language']=LANG
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
canonical=rebuild_client_artifacts({'json':canonical})['json']
before=copy.deepcopy(canonical)
result=route._render_target(canonical,LANG)
assert canonical==before
_validate_exact_artifact_hashes(result)
reader=PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64'])))
assert len(reader.pages)<=60
assert result['pdf_page_count']==len(reader.pages)
assert result['human_review_required'] is True
assert result['client_delivery_allowed'] is False
assert result['report_finality']=='automated_draft'
lines=[];sizes=[]
for page in reader.pages:
    text=page.extract_text() or ''
    for line in text.splitlines():
        if line.startswith(('Document page ','Página del documento ','Review page ','Página de revisión ','NICO |','Human decision pending |','Decisión humana pendiente |')) or '— continued' in line or '— continuación' in line:
            continue
        lines.append(line)
    def visitor(text,cm,tm,font,size):
        if text.strip() and 'Vera' in str((font or {}).get('/BaseFont','')):
            a,b=tm[0]*cm[0]+tm[1]*cm[2],tm[0]*cm[1]+tm[1]*cm[3]
            c,d=tm[2]*cm[0]+tm[3]*cm[2],tm[2]*cm[1]+tm[3]*cm[3]
            sizes.append(size*min(math.hypot(a,b),math.hypot(c,d)))
    page.extract_text(visitor_text=visitor)
compact=lambda value: ''.join(str(value).split())
text=compact(' '.join(lines))
assert observed and len(observed[-1])==8
cursor=0
for index,section in enumerate(observed[-1]):
    for item in range(3):
        marker=f'WORKSHEET_{index}_EVIDENCE_{item}'
        position=text.find(marker,cursor)
        assert position>=0,('missing/reordered projected evidence',marker)
        cursor=position+len(marker)
    for key,value in section.items():
        for item in value if isinstance(value,list) else [value]:
            if isinstance(item,bool): item=str(item).lower()
            assert compact(item) in text,('missing projected field',section['id'],key,item)
assert sizes and min(sizes)>=9
'''
    result=subprocess.run([sys.executable,'-c','LANG='+repr(language)+'\n'+script],capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('spanish',[False,True])
def test_sanitizer_preserves_owned_worksheet_streams_but_removes_internal_pages(spanish):
    import io
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject
    from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_review_pdf
    from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
    from tests.test_comprehensive_pdf_layout_polish_v1 import _review_canonical
    from tests.test_client_pdf_status_sanitizer_v1 import _pdf
    review=PdfReader(io.BytesIO(_render_polished_review_pdf(_review_canonical(),spanish=spanish)))
    writer=PdfWriter();writer.append(review,import_outline=False)
    # Old raw appendix pages remain removable, even if text copies the marker
    # or a malformed PDF value uses its spelling.
    internal=PdfReader(io.BytesIO(_pdf(['Evidence appendix','report_contract_reason',
        '/NICOFlowingReviewWorksheet true'])))
    internal.pages[0][NameObject('/NICOFlowingReviewWorksheet')]=TextStringObject('true')
    writer.add_page(internal.pages[0]);buffer=io.BytesIO();writer.write(buffer)
    sanitized=PdfReader(io.BytesIO(sanitize_client_pdf_status(buffer.getvalue())))
    assert len(sanitized.pages)==len(review.pages)
    for before,after in zip(review.pages,sanitized.pages):
        assert before.extract_text()==after.extract_text()
        assert before.get_contents().get_data()==after.get_contents().get_data()
