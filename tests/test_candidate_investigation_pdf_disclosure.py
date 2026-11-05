from copy import deepcopy
import pytest
from nico.candidate_investigation_pipeline_v1 import investigate_register, capture_sources, fingerprint
from nico.candidate_investigation_report_scope_v1 import KEY, report_identity
from nico.comprehensive_human_review_package_cleanup_v1 import sanitize_client_identity
from nico.report_preview_labels_v1 import retained_coverage_disclosures
from tests.test_candidate_source_observations_v1 import row

SCOPE={'run_id':'comprun_synthetic_pdf_reason_disclosure','repository':'BoneManTGRM/NICO',
       'commit_sha':'d3f1f5ae40bbe42c2c9ff20dcb72f46b5950a26d',
       'customer_id':'default_customer','project_id':'default_project'}


def fixture():
    register={'findings':[row(exact_commit_sha=SCOPE['commit_sha'])]}
    register['candidate_investigation']=investigate_register(register,capture_sources({},SCOPE),SCOPE)
    return {'identity':deepcopy(SCOPE),'assessment':{'canonical_scanner_finding_register':register}}


@pytest.mark.parametrize('spanish',[False,True])
def test_original_scope_and_reason_counts_survive_display_cleanup(spanish):
    original=fixture(); before=deepcopy(original)
    canonical=sanitize_client_identity(original)
    assert canonical['identity']['customer_id']=='Not supplied'
    assert report_identity(canonical)==SCOPE
    text='\n'.join(retained_coverage_disclosures(canonical,spanish=spanish))
    assert ('Candidatos sin resolver: 1' if spanish else 'Unresolved candidates: 1') in text
    assert ('causa desconocida: 1.' if spanish else 'cause unknown: 1.') in text
    assert original==before and sanitize_client_identity(canonical)==canonical


@pytest.mark.parametrize('target',['identity','context','packet'])
@pytest.mark.parametrize('field',list(SCOPE))
def test_every_scope_conflict_withholds_breakdown(target,field):
    canonical=sanitize_client_identity(fixture())
    if target=='identity':canonical['identity'][field]='foreign'
    elif target=='context':canonical[KEY]['identity'][field]='foreign'
    else:canonical['assessment']['canonical_scanner_finding_register']['candidate_investigation']['scope'][field]='foreign'
    text='\n'.join(retained_coverage_disclosures(canonical,spanish=False))
    assert 'Reason breakdown unavailable' in text and 'cause unknown: 1.' not in text


def test_legacy_normalized_identity_is_not_inferred_from_packets():
    canonical=sanitize_client_identity(fixture());canonical.pop(KEY)
    text='\n'.join(retained_coverage_disclosures(canonical,spanish=False))
    assert 'Reason breakdown unavailable' in text


def test_valid_old_producer_measurement_scope_is_checked_not_envelope_inferred():
    from nico.retained_section_measurements_v1 import REPORT_SCOPE_KEY,REPORT_SCOPE_VERSION
    canonical=sanitize_client_identity(fixture());canonical.pop(KEY)
    canonical[REPORT_SCOPE_KEY]={'artifact_schema':REPORT_SCOPE_VERSION,'identity':deepcopy(SCOPE)}
    assert report_identity(canonical)==SCOPE
    assert report_identity(sanitize_client_identity(canonical))==SCOPE
    canonical[REPORT_SCOPE_KEY]['identity']['run_id']='foreign'
    assert report_identity(canonical) is None


@pytest.mark.parametrize('bad',[None,[],{}, {'artifact_schema':'foreign','identity':SCOPE}])
def test_malformed_explicit_context_does_not_fall_back(bad):
    canonical=sanitize_client_identity(fixture());canonical[KEY]=bad
    assert report_identity(canonical) is None


def test_stale_fingerprint_does_not_publish_counts():
    canonical=sanitize_client_identity(fixture())
    canonical['assessment']['canonical_scanner_finding_register']['findings'][0]['line']=99
    assert 'Reason breakdown unavailable' in '\n'.join(retained_coverage_disclosures(canonical,spanish=False))


def production_count_fixture():
    from tests.test_candidate_source_observations_v1 import row
    from nico.candidate_source_reason_detail_v1 import path_digest
    groups=[(899,{}),(590,{'source_path':'output.py'}),(5,{'source_path':'absent.py'}),
            (68,{'exact_commit_sha':'f'*40,'category':'secret'}),
            (44,{'source_path':'calls.py','rule_id':'B603'}),(35,{'rule_id':'B999'}),
            (24,{'category':'dependency'}),(16,{'source_path':'assignment.py'})]
    rows=[]
    for count, changes in groups:
        for _ in range(count):
            candidate=row(candidate_id=f'SYNTHETIC-{len(rows)}',exact_commit_sha=SCOPE['commit_sha'])
            candidate.update(scanner='bandit',tool='bandit',disposition='review_required',status='completed',
                evidence='Synthetic retained candidate for bounded-render regression coverage.',
                raw_payload_retention_state='retained',raw_fingerprint='f'*64)
            candidate.update(changes);candidate['path']=candidate['source_path']
            candidate['finding_id']=candidate['candidate_id']
            rows.append(candidate)
    capture=capture_sources({'example.py':'assert permitted\n','calls.py':'one(); two()\n','assignment.py':'x=1\n'},SCOPE)
    capture['path_capture_outcomes']={'artifact_schema':'nico.candidate-path-capture-outcomes.v1',
        'path_sha256_reasons':{path_digest('output.py'):'observation_output_limit'},'recording_truncated':False}
    from collections import Counter
    totals={'raw':len(rows),'review_required':len(rows),'exact_source':len(rows)}
    register={'findings':rows,'candidate_record_count':len(rows),'totals':totals,
        'summary_by_category':{key:{'raw':count,'review_required':count,'exact_source':count}
                               for key,count in Counter(r['category'] for r in rows).items()}}
    register['candidate_investigation']=investigate_register(register,capture,SCOPE)
    return register,capture


def test_production_count_shape_has_all_six_unresolved_classes():
    register,_=production_count_fixture();packet=register['candidate_investigation']
    assert packet['bounded_rule_analysis_completed']==899 and packet['candidate_count']==1681
    assert packet['unresolved_reasons']=={'source_parse_unavailable':595,'source_identity_mismatch':68,
        'ambiguous_call_expression':44,'rule_semantics_require_specialist_review':35,
        'unsupported_or_missing_exact_source_evidence':24,'rule_source_line_mismatch':16}
    assert packet['source_availability_counts']=={'observation_output_limit':590,'source_not_retained':5}


def _installed_worker(locale):
    import base64,io
    from pypdf import PdfReader
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.candidate_investigation_finalization_v1 import final_investigation_scope
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico.candidate_investigation_pipeline_v1 import display_investigation
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    package={'json':_fixed_status(locale)['reports']['json']}
    package['json']['identity'].update(SCOPE)
    seed=_install_finalized_scanner_register(package['json'])
    register,capture=production_count_fixture()
    seed.update(register)
    # Synthetic candidate/source content, actual retained population and scope
    # shape. This is not a replay of private source or historical PDF mutation.
    context={**SCOPE,'prior_stage_results':{'evidence_reconciliation_and_scoring':{
        'candidate_source_observations':capture,'assessment':{'canonical_scanner_finding_register':deepcopy(seed)}}}}
    before=deepcopy((context,package))
    with final_investigation_scope(context):result=rebuild_client_artifacts(package)

    _validate_exact_artifact_hashes(result)
    canonical=result['json']; final=canonical['assessment']['canonical_scanner_finding_register']
    view=display_investigation(final,report_identity(canonical))
    assert canonical['identity']['customer_id']=='Not supplied'
    assert view['available'] and view['completed_count']==899 and view['candidate_count']==1681
    assert view['unresolved_reasons']==register['candidate_investigation']['unresolved_reasons']
    assert view['source_availability_counts']=={'observation_output_limit':590,'source_not_retained':5}
    pdf=' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    expected=(['Unresolved candidates: 782','Source parsing unavailable: 595','Source identity mismatch: 68',
        'Ambiguous call expression: 44','Specialist rule analysis required: 35',
        'Unsupported or missing exact-source evidence: 24','Rule and source line mismatch: 16',
        'Observation exceeded remaining retained output allowance: 590',
        'No observation retained for this candidate path; cause unknown: 5'] if locale=='en' else
        ['Candidatos sin resolver: 782','Análisis sintáctico del código no disponible: 595','La identidad del código no coincide: 68',
         'Expresión de llamada ambigua: 44','Se requiere análisis especializado de la regla: 35',
         'Evidencia del código exacto ausente o no compatible: 24','La regla no coincide con la línea del código: 16',
         'La observación superó el límite restante de salida conservada: 590',
         'No se conservó una observación para esta ruta; causa desconocida: 5'])
    for text in expected:assert ''.join(text.split()) in ''.join(pdf.split()),text
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
    assert (context,package)==before


@pytest.mark.parametrize('locale',['en','es-MX'])
def test_real_installed_pdf_route_discloses_population_and_reasons(locale,tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    code='import sys; from tests.test_candidate_investigation_pdf_disclosure import _installed_worker; _installed_worker(sys.argv[1])'
    result=subprocess.run([sys.executable,'-c',code,locale],cwd=root,
        env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=240)
    assert result.returncode==0,result.stdout+result.stderr


def test_spanish_display_placeholder_is_not_a_new_scope_authority():
    canonical=sanitize_client_identity(fixture())
    canonical['identity']['customer_id']='No proporcionado'
    canonical['identity']['project_id']='No proporcionado'
    assert report_identity(canonical) is None
    assert report_identity(canonical,spanish=True)==SCOPE
    canonical[KEY]['identity']['customer_id']='actual-other-customer'
    assert report_identity(canonical,spanish=True) is None
