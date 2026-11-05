"""Synthetic state-bound display regressions, not full retained-run replay."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest


def fixture(language='es-MX'):
    from nico.comprehensive_engagement_metadata_v1 import build_comprehensive_engagement_metadata
    from nico.comprehensive_human_evidence_report_v1 import _client_summary_stage
    metadata=build_comprehensive_engagement_metadata(client_name='Synthetic client',project_name='Synthetic project',
        human_evidence={'stakeholder_context':{'evidence':{}}},field_states={
        key:dict(state='excluded_from_scope',source='user_action',reason='Exact supplied rationale NOT_ASSESSED')
        for key in ('primary_technical_contact','access_method','authorized_scope')})
    stage=_client_summary_stage({'engagement_metadata':metadata},spanish=False)
    from nico.comprehensive_human_evidence_report_v1 import _translate_client_literal_line
    stage['evidence']=[_translate_client_literal_line(line) for line in stage['evidence']]
    return metadata,stage


def _worker():
    import base64,io
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package
    from pypdf import PdfReader
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    from nico.comprehensive_spanish_function_measurement_copy_v1 import COPY_ES
    for literal in ('NOT_ASSESSED', *COPY_ES):
        line='Dato aportado por el cliente · Contacto técnico principal: '+literal
        assert spanish._localize_tree({'stage_id':'client_human_evidence_stakeholder_context','evidence':[line]})['evidence']==[line]
    metadata,stage=fixture(); package=_package('es-MX')
    package['json']['engagement_metadata']=metadata
    package['json']['stage_summaries']=[stage]
    package['json']['assessment']['stage_summaries']=[deepcopy(stage)]
    before=deepcopy(package)
    result=rebuild_client_artifacts(package);_validate_exact_artifact_hashes(result)
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages).split())
    for label in ('Contacto técnico principal','Método de acceso','Alcance autorizado'):
        assert f'Dato aportado por el cliente · {label}: Excluido del alcance' in text
        assert f'{label}: Excluded from scope' not in text
    assert package==before
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False


def test_installed_final_exclusion_sentinels_are_localized(tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c','from tests.test_retained_exclusion_display import _worker; _worker()'],cwd=root,
        env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=120)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.parametrize('literal',['NOT_ASSESSED','Excluded from scope',
    'A verified collection contract from trusted server persistence, complete bound acquisition and measured function histograms are required.'])
def test_protected_client_literal_suffix_is_exact(literal):
    from nico.comprehensive_human_evidence_report_v1 import _translate_client_literal_line
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    original='Client-supplied data · Primary technical contact: '+literal
    assert _translate_client_literal_line(original)=='Dato aportado por el cliente · Contacto técnico principal: '+literal

@pytest.mark.parametrize('shape',['missing','tampered','supplied'])
def test_exclusion_text_requires_verified_empty_excluded_field(shape):
    from nico.comprehensive_human_evidence_report_v1 import localize_engagement_state_lines
    from nico.comprehensive_engagement_metadata_v1 import build_comprehensive_engagement_metadata
    metadata,stage=fixture()
    if shape=='missing':metadata={}
    elif shape=='tampered':metadata['primary_technical_contact']='tampered'
    else:
        metadata=build_comprehensive_engagement_metadata(client_name='Synthetic client',project_name='Synthetic project',
            human_evidence={'stakeholder_context':{'evidence':{'primary_technical_contact':'Excluded from scope'}}})
    before=deepcopy((metadata,stage))
    result=localize_engagement_state_lines(stage,metadata,spanish=True)
    assert 'Dato aportado por el cliente · Contacto técnico principal: Excluded from scope' in result['evidence']
    assert (metadata,stage)==before


@pytest.mark.parametrize('metadata',[None,{}, {'engagement_metadata_sha256':'invalid'}])
def test_structured_evidence_survives_missing_or_invalid_metadata(metadata):
    from nico.comprehensive_human_evidence_report_v1 import localize_engagement_state_lines
    stage={'stage_id':'client_evidence_summary','evidence':[
        {'source':'literal','values':['NOT_ASSESSED','Excluded from scope']},
        ['nested',{'reason':'Exact supplied reason'}], None, 7]}
    before=deepcopy(stage)
    assert localize_engagement_state_lines(stage,metadata,spanish=True)==before
    assert stage==before
