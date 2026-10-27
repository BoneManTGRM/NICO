"""Synthetic authored conformance copy; not a replay of the unavailable M3 fixture."""
import os
from pathlib import Path
import subprocess
import sys

from tests.owned_worker_environment import owned_worker_environment


def test_final_worker_pdf_localizes_composed_measurement_contract(tmp_path):
    root=Path(__file__).resolve().parents[1]
    script=r'''
from nico.api import final_report_worker_bootstrap
import base64,copy,io,json,os
from pathlib import Path
from pypdf import PdfReader
from nico.source_function_measurement_report_v1 import measurement_tables, UNAVAILABLE
from nico.source_function_conformance_v1 import build_conformance
from nico.source_function_conformance_report_v1 import integrate_conformance, CONFORMANCE_LIMITATIONS
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
from tests.test_v2_premium_report_renderer import _package
value=build_conformance({}, {}, {})
tables=integrate_conformance(measurement_tables({}, {}, {}),value)
assert tables[0]['rows'][0][1]==UNAVAILABLE+'; function complexity conformance: unavailable'
package=_package('es-MX')
package['json']['stage_summaries']=[{
 'stage_id':'architecture_and_data_flow','title':'Architecture and Data Flow','status':'complete',
 'summary':'Repository tests do not establish production user journeys.',
 'evidence':[], 'findings':[], 'unavailable':[], 'structured_tables':tables,
}]
package['json']['stage_summaries'].append({
 'stage_id':'functional_qa','title':'Functional QA','status':'not_assessed',
 'summary':'Repository tests do not establish production user journeys.',
 'evidence':[], 'findings':[], 'unavailable':[],
})
original=copy.deepcopy(package)
result=rebuild_client_artifacts(package)
assert package==original
_validate_exact_artifact_hashes(result)
assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
pdf=base64.b64decode(result['pdf_base64'],validate=True)
Path(os.environ['NICO_HOME'],'synthetic-conformance-es.pdf').write_bytes(pdf)
text=' '.join(' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages).split())
Path(os.environ['NICO_HOME'],'synthetic-conformance-es.txt').write_text(text)
assert 'Mediciones de funciones no disponibles' in text
assert 'conformidad de complejidad de funciones: no disponible' in text
assert 'La velocidad de entrega no está establecida.' in text
assert 'marginales separados' in text and 'sin inferencia conjunta' in text
assert 'Se requiere un contrato de recopilación verificado' in text
for leak in ('Function measurements','function complexity conformance:', 'Conformance limitations',
             'Conformance qualification', 'A verified collection contract','A verificada',
             'Delivery velocity is not established'):
 assert leak not in text,leak
assert 'CC<=20' in text and 'nesting<=4' in text
assert 'NOT_ASSESSED' not in text
assert 'NO EVALUADO' in text
# Full retained canonical structured evidence remains authored source, not translated.
stages=result['json']['stage_summaries']
assert any(stage.get('structured_tables')==tables for stage in stages)
'''
    result=subprocess.run([sys.executable,'-c',script],cwd=root,
        env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


def test_authored_composition_is_exact_and_unknown_or_supplied_copy_is_not_rewritten():
    from nico.comprehensive_spanish_function_measurement_copy_v1 import translate_function_measurement_copy
    from nico.source_function_measurement_report_v1 import LIMITS, UNAVAILABLE
    from nico.source_function_conformance_report_v1 import CONFORMANCE_LIMITATIONS
    from nico.source_function_conformance_v1 import LIMITATIONS
    combined=translate_function_measurement_copy(LIMITS+' '+CONFORMANCE_LIMITATIONS)
    assert 'CC<=20' in combined and 'nesting<=4' in combined and 'sin inferencia conjunta' in combined
    assert 'no está establecida' in combined
    full=translate_function_measurement_copy(LIMITATIONS)
    for literal in ('CC<=20','Nesting<=4','sum(CC-1)','Python','C++'):
        assert literal in full
    for raw in (UNAVAILABLE+'; function complexity conformance: unexpected',
                'Client supplied: '+UNAVAILABLE,
                CONFORMANCE_LIMITATIONS+' supplied tail'):
        assert translate_function_measurement_copy(raw) is None
