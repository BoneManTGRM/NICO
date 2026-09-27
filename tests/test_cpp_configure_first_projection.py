from copy import deepcopy
import gzip,hashlib
from nico.assessment_cpp_configure_first_projection import _read_artifact,project_configure_first_record
from nico.assessment_worker_jobs import JobIdentity,_digest

def identity():
    return JobIdentity("c","p","r","scan","owner/repo","a"*40,"b"*64,"c"*40)

class Store:
    def __init__(self,raw,key):
        self.raw=raw; self.key=key
    def get(self,artifact_id,limit):
        compressed=gzip.compress(self.raw,mtime=0)
        return {"binding":{"run_id":"r","scan_id":"scan","customer_id":"c","project_id":"p",
            "repository":"owner/repo","commit_sha":"a"*40,"scanner_name":"cppcheck:"+self.key},
            "sha256":hashlib.sha256(self.raw).hexdigest(),"gzip_sha256":hashlib.sha256(compressed).hexdigest(),
            "compressed_bytes":len(compressed),"compressed":compressed}

def ref(raw,key):
    compressed=gzip.compress(raw,mtime=0)
    return {"artifact_id":"scanartifact_"+"d"*64,"key":key,"sha256":hashlib.sha256(raw).hexdigest(),
        "gzip_sha256":hashlib.sha256(compressed).hexdigest(),"retained_bytes":len(raw),
        "gzip_bytes":len(compressed),"storage_backend":"postgres"}

def test_artifact_read_rebinds_exact_job_and_hashes():
    raw=b'{"owned":true}'; key="project-static-evidence"
    assert _read_artifact(Store(raw,key),identity(),ref(raw,key),key)==raw

def test_projection_cannot_turn_incomplete_execution_into_success():
    record={"status":"failed","completed":False}
    receipt={"native":{"complete_execution":False}}
    assert project_configure_first_record(record,identity(),{},receipt,{"analysis":{"complete":False}})==record

def test_projection_preserves_full_canonical_finding_population():
    ident=identity(); finding={"rule_id":"owned","path":"src/a.cpp","line":1,"column":1,
        "context_id":"e"*64,"source_sha256":"f"*64,"classification":"review_required_candidate"}
    record={"status":"partial","completed":False,"verified_complete":False,"verified_for_this_report":False,
        "execution_observed_for_this_report":True,"returncode_valid":True,"findings":[],"finding_count":1,
        "reason":"pending","canonical_findings_projected":False,"cppcheck_source_coverage":{},
        "worker_provenance":{}}
    receipt={"configuration_sha256":"1"*64,"target_hashes":{"src/a.cpp":"f"*64},
        "native":{"complete_execution":True,"compilation_database_sha256":"2"*64,
            "artifacts":{"project-static-evidence":{"artifact_id":"scanartifact_"+"3"*64}}}}
    reconstruction={"analysis":{"complete":True,"required_contexts":["e"*64],"analyzed_contexts":["e"*64],
        "findings":[finding],"limitations":[],"native_evidence_sha256":"4"*64},
        "compiler":{"native_evidence_sha256":"5"*64}}
    out=project_configure_first_record(record,ident,{},receipt,reconstruction)
    assert out["completed"] and out["verified_complete"] and out["canonical_findings_projected"]
    assert out["finding_count"]==len(out["findings"])==1
    assert out["findings"][0]["commit_sha"]=="a"*40


def test_configure_first_runtime_evidence_renders_in_both_languages():
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    digest='a'*64
    identity={'run_id':'run','commit_sha':'b'*40}
    record={
        'commit_sha':'b'*40,'raw_artifact_retention_complete':True,'raw_artifact_sha256':digest,
        'current_run':True,'exact_commit_match':True,'execution_observed_for_this_report':True,
        'worker_provenance':{'profile':'cpp-configure-first-v2','receipt_sha256':digest,
            'identity':{'run_id':'run','revision':'b'*40}},
        'cppcheck_source_coverage':{'header_context_verified':True},
        'cpp_build_evidence':{'profile':'cpp-configure-first-v2','compiled':True,
            'runtime_scope':{'complete':True,
                'functional':{'required':['feature_a.py','p2p_a.py'],'executed':['feature_a.py','p2p_a.py'],
                    'passed':['feature_a.py','p2p_a.py'],'failed':[],'skipped':[]},
                'sanitizers':[{'kind':'address','required':['unit_a'],'executed':['unit_a'],'passed':['unit_a'],'skipped':[]},
                    {'kind':'undefined','required':['unit_a'],'executed':['unit_a'],'passed':['unit_a'],'skipped':[]}],
                'fuzz':{'target':'connect_block','replay_count':2,'campaign_completed':True,
                    'campaign_executions':256,'campaign_coverage_signal':31,'campaign_duration_ms':1234,
                    'corpus_sha256':['c'*64,'d'*64]}}}
    }
    for language, terms in [('en',('Functional runtime tests: 2/2 passed.','Sanitizer / address: 1/1 passed.',
            'Bounded fuzz / connect_block: corpus replays=2; campaign executions=256; tool coverage signal=31.')),
        ('es-MX',('Pruebas funcionales en ejecución: 2/2 aprobadas.','Sanitizador / address: 1/1 aprobadas.',
            'Fuzzing acotado / connect_block: repeticiones del corpus=2; ejecuciones de campaña=256; señal de cobertura de la herramienta=31.'))]:
        canonical={'report_language':language,'identity':identity,'scanner_execution_records':[record]}
        out=enrich_scanner_stage(canonical,{'summary':'','evidence':[],'unavailable':[]})
        rendered=' '.join([out['summary'],*out['evidence'],*out['unavailable']])
        for term in terms: assert term in rendered
        assert ('not exhaustive vulnerability or source coverage' in rendered if language=='en'
                else 'no representa cobertura exhaustiva de vulnerabilidades ni del código' in rendered)


def test_partial_runtime_evidence_is_projected_without_promoting_scanner():
    record = {'status': 'partial', 'completed': False, 'verified_complete': False,
              'finding_count': 0, 'findings': [], 'reason': 'incomplete execution',
              'cpp_build_evidence': {'profile': 'cpp-configure-first-v2', 'compiled': True}}
    original = deepcopy(record)
    summary = {'complete': False, 'error': 'worker_runtime_sanitizer_failed',
               'sanitizers_not_executed': ['undefined'], 'fuzz': {'state': 'not_executed'}}
    receipt = {'native': {'complete_execution': False}}
    reconstruction = {'analysis': {'complete': False}, 'runtime': {'summary': summary}}
    result = project_configure_first_record(record, identity(), {}, receipt, reconstruction)
    assert result['cpp_build_evidence']['runtime_scope'] == summary
    assert result['status'] == 'partial'
    assert result['completed'] is False and result['verified_complete'] is False
    assert result['finding_count'] == 0 and result['findings'] == []
    result['cpp_build_evidence']['runtime_scope']['sanitizers_not_executed'].clear()
    assert summary['sanitizers_not_executed'] == ['undefined']
    assert record == original


import pytest

@pytest.mark.parametrize('locale,terms', [
    ('en', ('Sanitizer / undefined: not executed.',
            'Bounded fuzz / connect_block: not executed; required corpus replays=2.',
            'Declared runtime scope is incomplete.')),
    ('es-MX', ('Sanitizador / undefined: no ejecutado.',
              'Fuzzing acotado / connect_block: no ejecutado; repeticiones requeridas del corpus=2.',
              'El alcance de ejecución declarado está incompleto.')),
])
def test_failed_runtime_report_names_unexecuted_scope_in_each_locale(locale, terms):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    digest = 'a' * 64
    record = {'commit_sha': 'b' * 40, 'raw_artifact_retention_complete': True,
        'raw_artifact_sha256': digest, 'current_run': True, 'exact_commit_match': True,
        'execution_observed_for_this_report': True,
        'worker_provenance': {'profile': 'cpp-configure-first-v2', 'receipt_sha256': digest,
            'identity': {'run_id': 'run', 'revision': 'b' * 40}},
        'cppcheck_source_coverage': {'header_context_verified': True},
        'cpp_build_evidence': {'profile': 'cpp-configure-first-v2', 'compiled': True,
            'runtime_scope': {'complete': False, 'error': 'worker_runtime_sanitizer_failed',
                'functional': {'required': ['feature_a.py'], 'passed': ['feature_a.py']},
                'sanitizers': [{'kind': 'address', 'required': ['unit_a'],
                               'executed': [], 'passed': [], 'skipped': ['unit_a']}],
                'sanitizers_not_executed': ['undefined'],
                'fuzz': {'state': 'not_executed', 'target': 'connect_block',
                         'required_replay_count': 2, 'replay_count': 0,
                         'campaign_completed': False, 'campaign_executions': None,
                         'campaign_coverage_signal': None, 'campaign_duration_ms': None}}}}
    canonical = {'report_language': locale, 'identity': {'run_id': 'run', 'commit_sha': 'b' * 40},
                 'scanner_execution_records': [record]}
    rendered = enrich_scanner_stage(canonical, {'summary': '', 'evidence': [], 'unavailable': []})
    text = ' '.join([rendered['summary'], *rendered['evidence'], *rendered['unavailable']])
    for term in terms:
        assert term in text
    assert 'None' not in text


@pytest.mark.parametrize('locale,expected', [('en','passed=unknown/1'),('es-MX','aprobadas=desconocido/1')])
def test_timed_out_sanitizer_without_junit_never_reports_zero_passes(locale,expected):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    digest='a'*64
    native={'commit_sha':'b'*40,'raw_artifact_retention_complete':True,
        'raw_artifact_sha256':digest,'current_run':True,'exact_commit_match':True,
        'execution_observed_for_this_report':True,
        'worker_provenance':{'profile':'cpp-configure-first-v2','receipt_sha256':digest,
            'identity':{'run_id':'run','revision':'b'*40}},
        'cppcheck_source_coverage':{'header_context_verified':True},
        'cpp_build_evidence':{'profile':'cpp-configure-first-v2','compiled':True,
            'runtime_scope':{'complete':False,
                'functional':{'required':['feature_a.py'],'passed':['feature_a.py']},
                'sanitizers':[{'kind':'address','state':'timed_out','required':['unit_a'],
                    'executed':None,'passed':None,'skipped':None}],
                'sanitizers_not_executed':['undefined'],
                'fuzz':{'state':'not_executed','target':'connect_block','required_replay_count':2}}}}
    canonical={'report_language':locale,'identity':{'run_id':'run','commit_sha':'b'*40},
               'scanner_execution_records':[native]}
    out=enrich_scanner_stage(canonical,{'summary':'','evidence':[],'unavailable':[]})
    text=' '.join([out['summary'],*out['evidence'],*out['unavailable']])
    assert expected in text
    assert 'None' not in text


def _failed_runtime_complete_static_fixture():
    """Owned receipt-to-report seam; native reconstruction data is synthetic.

    Artifact-store/native parser behavior is covered separately. These cases
    deliberately obtain the preliminary flags from the actual receipt producer
    rather than pre-setting an observed-execution flag in a renderer fixture.
    """
    from dataclasses import asdict
    from nico.assessment_cpp_configure_first_execution import summarize_probe
    from nico.assessment_worker_receipts import validate_receipt
    from tests.test_cpp_configure_first_contract import contract
    from tests.test_cpp_configure_first_execution import proof, ref as native_ref

    plan = contract()
    plan['configuration'].pop('project_options')
    plan['configuration'].update(schema='nico.cpp-configure-first-contract.v3',
        project_option_policy='conservative-cmake-v1', runtime_scope={
            'schema':'nico.cpp-runtime-scope.v1', 'total_seconds':6000,
            'functional_policy':'source-declared-functional-v1', 'functional_seconds':900,
            'sanitizers':['address','undefined'], 'sanitizer_build_seconds':1200,
            'sanitizer_test_seconds':600, 'sanitizer_test_case_seconds':120,
            'fuzz_policy':'source-declared-libfuzzer-v1', 'fuzz_replay_runs':1,
            'fuzz_campaign_runs':256, 'fuzz_campaign_seconds':300, 'parallel':4})
    plan['limits'] = {'max_attempts':1, 'wall_seconds':9000, 'lease_seconds':300}
    ident = JobIdentity('c','p','r','scan','owner/repo','a'*40,_digest(plan),'c'*40)
    targets = {'CMakeLists.txt':'d'*64, 'src/a.cpp':'e'*64}
    findings = [
        {'rule_id':'owned-rule', 'path':'src/a.cpp', 'line':1, 'column':1,
         'context_id':context, 'source_sha256':'e'*64,
         'classification':'review_required_candidate', 'analyzer':analyzer}
        for context, analyzer in [('c1','cppcheck'), ('c2','clang-static-analyzer')]
    ]
    probe = proof()
    probe.update(status='UNPROVEN', error='worker_configuration_probe_runtime_incomplete')
    probe['project_static'].update(findings=findings, native_evidence_sha256='4'*64)
    artifacts = {key:native_ref(key) for key in (
        'project-compilation-database','project-generated-context','project-compiler-evidence',
        'project-static-environment','project-static-evidence','project-static-clang-fallback',
        'project-runtime-evidence')}
    artifacts['project-static-clang-fallback']['artifact_id'] = 'scanartifact_'+'b'*64
    native = summarize_probe(probe, targets, artifacts)
    runtime_summary = {'complete':False, 'error':'worker_runtime_sanitizer_failed',
        'functional':{'required':['owned.py'], 'executed':['owned.py'], 'passed':['owned.py'],
                      'failed':[], 'skipped':[]},
        'sanitizers':[{'kind':'address','state':'timed_out','required':['owned-unit'],
                      'executed':None,'passed':None,'failed':None,'skipped':None}],
        'sanitizers_not_executed':['undefined'],
        'fuzz':{'state':'not_executed','target':'owned','required_replay_count':2,'replay_count':0,
                'campaign_completed':False,'campaign_executions':None,
                'campaign_coverage_signal':None,'campaign_duration_ms':None}}
    native.update(schema='nico.cpp-configure-first-native.v2', runtime_complete=False,
        runtime_plan_sha256='6'*64, runtime_summary_sha256=_digest(runtime_summary), runtime_duration_ms=600,
        project_option_policy='conservative-cmake-v1', project_options={}, project_options_sha256=_digest({}))
    receipt = {'schema':'nico.worker-native-receipt.v7', 'identity':asdict(ident),
        'lease_id':'owned-lease','worker_id':'owned-worker','image_digest':plan['image_digest'],
        'tool_version':plan['tool_version'],'configuration_sha256':_digest(plan['configuration']),
        'target_hashes':targets,'native':native,'native_sha256':_digest(native)}
    encoded, record, _ = validate_receipt(ident,plan,'owned-lease','owned-worker',receipt)
    reconstruction = {'analysis':deepcopy(probe['project_static']),
        'compiler':{'native_evidence_sha256':'5'*64},
        'runtime':{'summary':runtime_summary,'native_evidence_sha256':'7'*64}}
    return ident, plan, receipt, encoded, record, reconstruction


def test_verified_static_findings_survive_failed_runtime_without_completion_credit():
    ident, plan, receipt, _, record, reconstruction = _failed_runtime_complete_static_fixture()
    originals = deepcopy((record, receipt, reconstruction))
    assert record['execution_observed_for_this_report'] is False
    projected = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    assert projected['finding_count'] == len(projected['findings']) == 2
    assert projected['canonical_findings_projected'] is True
    assert projected['execution_observed_for_this_report'] is True
    assert projected['status'] == 'failed' and projected['reason'] == record['reason']
    for key in ('completed','verified_complete','verified_for_this_report','returncode_valid'):
        assert projected[key] is False
    assert projected['human_review_required'] is True
    assert projected['client_delivery_allowed'] is False
    assert [f['context_id'] for f in projected['findings']] == ['c1','c2']
    assert len({f['observation_id'] for f in projected['findings']}) == 2
    for value, key in zip(projected['findings'], ('project-static-evidence','project-static-clang-fallback')):
        assert value['evidence_reference'] == 'worker_artifact:'+receipt['native']['artifacts'][key]['artifact_id']
        assert value['commit_sha'] == ident.revision
        assert value['configuration_sha256'] == receipt['configuration_sha256']
    assert projected == project_configure_first_record(record,ident,plan,receipt,reconstruction)
    assert (record, receipt, reconstruction) == originals


@pytest.mark.parametrize('locale,terms', [
    ('en', ('Functional runtime tests: 1/1 passed.', 'passed=unknown/1',
            'Sanitizer / undefined: not executed.', 'Declared runtime scope is incomplete.')),
    ('es-MX', ('Pruebas funcionales en ejecución: 1/1 aprobadas.', 'aprobadas=desconocido/1',
              'Sanitizador / undefined: no ejecutado.', 'El alcance de ejecución declarado está incompleto.')),
])
def test_receipt_produced_runtime_failure_reaches_existing_report_gate(locale, terms):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    from nico.production_report_truth_gate_v1 import _canonical_scanners
    ident,plan,receipt,encoded,record,reconstruction = _failed_runtime_complete_static_fixture()
    record = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    # Simulate successful immutable retention of these exact owned receipt bytes;
    # this is not a live database write or production artifact proof.
    digest = hashlib.sha256(encoded).hexdigest()
    record.update(raw_artifact_retention_complete=True,raw_artifact_sha256=digest,artifact_hash=digest)
    canonical = {'report_language':locale, 'identity':{'run_id':ident.run_id,'commit_sha':ident.revision},
                 'scanner_execution_records':[record]}
    rendered = enrich_scanner_stage(canonical, {'summary':'','evidence':[],'unavailable':[]})
    text = ' '.join([rendered['summary'],*rendered['evidence'],*rendered['unavailable']])
    for term in terms:
        assert term in text
    assert 'None' not in text
    normalized = _canonical_scanners(canonical,{})[0]
    assert normalized['status'] == 'failed'
    assert normalized['completed'] is False and normalized['verified_complete'] is False
    assert normalized['finding_count'] == len(normalized['findings']) == 2


@pytest.mark.parametrize('analysis_complete', [False, None, 0, 'true'])
def test_partial_projection_requires_actual_static_completion(analysis_complete):
    ident,plan,receipt,_,record,reconstruction = _failed_runtime_complete_static_fixture()
    reconstruction['analysis']['complete'] = analysis_complete
    projected = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    assert projected['findings'] == [] and projected['canonical_findings_projected'] is False
    assert projected['execution_observed_for_this_report'] is False
    assert projected['completed'] is False


def test_failed_projection_copies_findings_coverage_and_runtime_without_mutating_evidence():
    ident,plan,receipt,_,record,reconstruction = _failed_runtime_complete_static_fixture()
    originals = deepcopy((record,receipt,reconstruction))
    projected = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    projected['findings'][0]['path'] = 'changed.cpp'
    projected['cpp_build_evidence']['runtime_scope']['sanitizers_not_executed'].clear()
    projected['cppcheck_source_coverage']['limitations'].append('changed')
    assert (record,receipt,reconstruction) == originals


def test_runtime_failure_does_not_change_static_observation_identity():
    ident,plan,receipt,_,record,reconstruction = _failed_runtime_complete_static_fixture()
    failed = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    completed_receipt = deepcopy(receipt)
    completed_reconstruction = deepcopy(reconstruction)
    completed_receipt['native']['complete_execution'] = True
    completed_reconstruction['runtime']['summary']['complete'] = True
    # The projection seam receives already-validated reconstruction. This paired
    # case compares observation identity only; it is not native execution proof.
    completed = project_configure_first_record(record,ident,plan,completed_receipt,completed_reconstruction)
    assert completed['findings'] == failed['findings']
    assert completed['worker_provenance']['canonical_projection'] == failed['worker_provenance']['canonical_projection']
    assert completed['completed'] is True and failed['completed'] is False


@pytest.mark.parametrize('change', ['missing_retention','changed_hash','changed_run','changed_revision'])
def test_partial_execution_does_not_relax_retained_report_identity_gate(change):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    ident,plan,receipt,encoded,record,reconstruction = _failed_runtime_complete_static_fixture()
    record = project_configure_first_record(record,ident,plan,receipt,reconstruction)
    record.update(raw_artifact_retention_complete=True,raw_artifact_sha256=hashlib.sha256(encoded).hexdigest())
    if change == 'missing_retention':
        record['raw_artifact_retention_complete'] = False
    elif change == 'changed_hash':
        record['raw_artifact_sha256'] = '0'*64
    elif change == 'changed_run':
        record['worker_provenance']['identity']['run_id'] = 'other-run'
    else:
        record['commit_sha'] = '0'*40
    canonical = {'report_language':'en','identity':{'run_id':ident.run_id,'commit_sha':ident.revision},
                 'scanner_execution_records':[record]}
    rendered = enrich_scanner_stage(canonical,{'summary':'','evidence':[],'unavailable':[]})
    text = ' '.join([rendered['summary'],*rendered['evidence'],*rendered['unavailable']])
    assert 'not bound to a verified retained receipt' in text
    assert 'Functional runtime tests: 1/1 passed.' not in text


@pytest.mark.parametrize('locale,unknown,unexecuted', [
    ('en', 'passed=unknown/1', 'Sanitizer / undefined: not executed.'),
    ('es-MX', 'aprobadas=desconocido/1', 'Sanitizador / undefined: no ejecutado.'),
])
def test_failed_runtime_complete_export_retains_unknowns_and_human_boundary(tmp_path, locale, unknown, unexecuted):
    """Use the public exporter, not only the scanner-stage string helper."""
    import io
    from pypdf import PdfReader
    from scripts.qualify_cpp_full_project_integration import render_result
    ident, plan, receipt, encoded, record, reconstruction = _failed_runtime_complete_static_fixture()
    record = project_configure_first_record(record, ident, plan, receipt, reconstruction)
    digest = hashlib.sha256(encoded).hexdigest()
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=digest, artifact_hash=digest)
    before = deepcopy(record)
    result = render_result({'canonical_record': record}, tmp_path, locale)
    assert result['automated_draft'] is True and result['production_report'] is False
    assert record == before
    assert record['status'] == 'failed'
    assert record['completed'] is False and record['verified_complete'] is False
    assert record['human_review_required'] is True and record['client_delivery_allowed'] is False
    stem = tmp_path / ('owned-project-' + locale)
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(stem.with_suffix('.pdf').read_bytes())).pages)
    for rendered in (text, stem.with_suffix('.md').read_text(), stem.with_suffix('.html').read_text()):
        normalized = ' '.join(rendered.split())
        assert unknown in normalized
        assert unexecuted in normalized
        if locale == 'es-MX':
            assert 'Configure-first execution is incomplete' not in normalized
            assert 'scanner execution(s) remain incomplete' not in normalized
            assert 'Dates, owners, dependencies, and budget require' not in normalized
            assert 'la evidencia nativa conservada requiere reparación' in normalized


@pytest.mark.parametrize('prefix', ['', 'cppcheck: '])
def test_configure_first_failure_translation_is_exact_and_does_not_allow_new_english(prefix):
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    reason = 'Configure-first execution is incomplete; retained native evidence requires repair.'
    translated = _translate_presentation_field(prefix + reason, 'unavailable')
    assert translated == prefix + ('La ejecución con configuración inicial está incompleta; '
                                  'la evidencia nativa conservada requiere reparación.')
    with pytest.raises(ValueError, match='Spanish presentation'):
        _translate_presentation_field(prefix + reason.replace('requires repair', 'has unreviewed new conditions'),
                                      'unavailable')


@pytest.mark.parametrize('count', [0, 1, 4])
@pytest.mark.parametrize('with_candidates', [False, True])
def test_incomplete_scanner_clause_localizes_independently_of_candidate_clause(count, with_candidates):
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    text = f'{count} scanner execution(s) remain incomplete.'
    if with_candidates:
        text += ' 2 resulting candidates remain pending human disposition.'
    translated = _translate_presentation_field(text, 'summary')
    unit = 'ejecución de analizador permanece incompleta' if count == 1 else 'ejecuciones de analizadores permanecen incompletas'
    assert f'{count} {unit}.' in translated
    assert 'scanner execution' not in translated
    if with_candidates:
        assert '2 candidatos resultantes siguen pendientes de disposición humana.' in translated


def test_blank_roadmap_late_companion_localizes_confirmation_requirement():
    from nico.comprehensive_client_review_companion_v2 import review_sections
    canonical = {'assessment': {}, 'roadmap': []}
    original = deepcopy(canonical)
    spanish = next(row for row in review_sections(canonical, spanish=True) if row['id'] == 'six_month_roadmap')
    english = next(row for row in review_sections(canonical, spanish=False) if row['id'] == 'six_month_roadmap')
    assert spanish['limitations'] == ['Las fechas, los responsables, las dependencias y el presupuesto requieren confirmación explícita de las partes interesadas.']
    assert english['limitations'] == ['Dates, owners, dependencies, and budget require explicit stakeholder confirmation.']
    assert canonical == original
