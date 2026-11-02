"""Synthetic exact-byte reviewer proof integration; no retained artifact inputs."""
from copy import deepcopy
import json
import socket
import sqlite3

import pytest
from nico import candidate_investigation_pipeline_v1 as pipeline
from nico import candidate_technical_triage_v1 as triage
from tests.test_candidate_call_resolution_v1 import capture, row, SCOPE


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('external/default access prohibited')
    monkeypatch.setattr(triage, 'load_default_technical_triage', deny)
    monkeypatch.setattr(socket, 'socket', deny)
    monkeypatch.setattr(sqlite3, 'connect', deny)
    yield
    assert not attempts


def project(candidate, retained):
    register = {'findings': [candidate], 'overall_score': 73, 'client_delivery_allowed': False}
    before = deepcopy(register)
    result = pipeline.investigate_register(register, retained, SCOPE)
    assert register == before
    view = pipeline.display_investigation({**register, 'candidate_investigation': result}, SCOPE)
    return result, view


@pytest.mark.parametrize('rule', ['B603', 'B607'])
@pytest.mark.parametrize('source,api', [
    ('import subprocess\nsubprocess.run([])\n', 'subprocess.run'),
    ('import subprocess as sp\nsp.Popen(**options)\n', 'subprocess.Popen'),
    ('from subprocess import call as invoke\ninvoke(arguments)\n', 'subprocess.call'),
])
def test_qualified_binding_visible_without_disposition_or_argument_claims(rule, source, api):
    candidate = row(); candidate['rule_id'] = rule
    retained = capture(source, candidate)
    result, view = project(candidate, retained)
    proof = view['packets'][0]['lexical_binding']
    assert proof['api'] == api and proof['scope'] == SCOPE
    assert proof['import_line'] == 1 and proof['line'] == 2
    assert proof['candidate_input_sha256'] == pipeline.fingerprint(candidate)
    assert set(proof) == pipeline.BINDING_FIELDS
    assert set(result['packets'][0]['argument_observations']) == set(pipeline.ARGUMENT_ENUMS)
    assert 'argument_observations' not in view['packets'][0]
    assert result['human_review_required'] and not result['client_delivery_allowed']
    assessed = triage.apply_candidate_technical_triage({'findings': [candidate]},
        triage={'synthetic': True}, source_capture=retained, source_scope=SCOPE)['findings'][0]
    assert assessed['technical_triage_verdict'] == 'needs_review'
    assert assessed['disposition'] == 'review_required'
    assert not assessed['technical_triage_client_delivery_allowed']


@pytest.mark.parametrize('source,line', [
    ('import subprocess as sp\nsp=other\nsp.run([])\n', 3),
    ('import subprocess as sp\nf=exec\nf(code)\nsp.run([])\n', 4),
    ('import subprocess as sp\nother=sp\nother.run=replacement\nsp.run([])\n', 4),
    ('import subprocess as sp\nsp.run([]); sp.call([])\n', 2),
])
def test_ambiguous_binding_not_projected(source, line):
    candidate = row(line)
    _, view = project(candidate, capture(source, candidate))
    assert 'lexical_binding' not in view['packets'][0]


@pytest.mark.parametrize('mutation', ['tenant', 'sha', 'path', 'line', 'warnings', 'partial', 'decoded', 'injected'])
def test_unqualified_capture_or_candidate_cannot_issue_proof(mutation):
    candidate = row(); source = 'import subprocess as sp\nsp.run([])\n'
    retained = capture(source, candidate)
    if mutation == 'tenant': retained['scope']['customer_id'] = 'other'
    if mutation == 'sha': candidate['source_commit_sha'] = 'b'*40
    if mutation == 'path': candidate['source_path'] = 'other.py'
    if mutation == 'line': candidate['line'] = 1
    if mutation == 'warnings': retained['observations']['app.py']['parse_warning_count'] = 1
    if mutation == 'partial': retained['observations']['app.py']['complete_source_blob'] = False
    if mutation == 'decoded': retained = pipeline.capture_sources({'app.py': source}, SCOPE)
    if mutation == 'injected':
        candidate['lexical_binding'] = {'api': 'subprocess.run'}
        retained = {}
    _, view = project(candidate, retained)
    assert 'lexical_binding' not in view['packets'][0]


@pytest.mark.parametrize('field,value', [('version','old'), ('resolver_version','old'), ('api','private.data'),
    ('api', []), ('import_line', True), ('line', 99), ('scope', {}), ('path','other.py'),
    ('source_sha256','b'*64), ('blob_oid','bad'), ('candidate_input_sha256','b'*64), ('raw_arguments','SECRET')])
def test_saved_malformed_or_injected_extension_fails_closed(field, value):
    candidate = row(); result, _ = project(candidate, capture('import subprocess\nsubprocess.run([])\n',candidate))
    result['packets'][0]['lexical_binding'][field] = value
    view = pipeline.display_investigation({'findings':[candidate], 'candidate_investigation':result},SCOPE)
    assert 'lexical_binding' not in view['packets'][0]
    assert 'SECRET' not in json.dumps(view)


def test_read_never_issues_or_acquires_and_stale_rows_fail_closed(monkeypatch):
    candidate = row(); result, _ = project(candidate, capture('import subprocess\nsubprocess.run([])\n',candidate))
    monkeypatch.setattr(pipeline, 'candidate_call_fact', lambda *a: pytest.fail('GET performed analysis'))
    register = {'findings':[candidate], 'candidate_investigation':result}
    assert pipeline.display_investigation(register,SCOPE)['packets'][0]['lexical_binding']
    candidate['severity'] = 'high'
    assert not pipeline.display_investigation(register,SCOPE)['available']


def test_duplicate_ids_keep_index_and_row_fingerprint_and_limits(monkeypatch):
    a = row(); b = dict(a, severity='high')
    retained = capture('import subprocess\nsubprocess.run([])\n',a)
    register = {'findings':[a,b]}
    result = pipeline.investigate_register(register,retained,SCOPE)
    view = pipeline.display_investigation({**register,'candidate_investigation':result},SCOPE)
    assert [p['record_index'] for p in view['packets']] == [0,1]
    assert len({p['candidate_input_sha256'] for p in view['packets']}) == 2
    size = pipeline._binding_size(result['packets'][0]['lexical_binding'])
    monkeypatch.setattr(pipeline,'BINDING_TOTAL_BYTES',size)
    limited = pipeline.investigate_register(register,retained,SCOPE)
    assert sum('lexical_binding' in p for p in limited['packets']) == 1
    assert limited['candidate_count'] == 2
    assert sum('lexical_binding' in p for p in pipeline.display_investigation({**register,'candidate_investigation':result},SCOPE)['packets']) == 1
    monkeypatch.setattr(pipeline,'BINDING_MAX_BYTES',1)
    assert 'lexical_binding' not in pipeline.investigate_register(register,retained,SCOPE)['packets'][0]


def test_conflicting_claim_still_requires_review():
    candidate = row(executable_code=False, comment_or_string=True)
    retained = capture('import subprocess\nsubprocess.run([])\n',candidate)
    project(candidate,retained)
    assessed = triage.apply_candidate_technical_triage({'findings':[candidate]},triage={'synthetic':True},source_capture=retained,source_scope=SCOPE)['findings'][0]
    assert assessed['technical_triage_verdict'] == 'needs_review'
    assert 'conflicting_executable_source_evidence' in assessed['technical_triage_proof_gaps']


def test_real_review_projection_keeps_binding_and_all_gates():
    from nico.comprehensive_review_work_v2 import review_work_projection, assert_ready_for_approval
    candidate = row(); retained = capture('import subprocess\nsubprocess.run([])\n', candidate)
    register = {'candidate_record_count': 1, 'findings': [candidate], 'review_workload_clusters': [{'cluster_id':'synthetic','candidate_ids':['candidate']}]}
    register['candidate_investigation'] = pipeline.investigate_register(register, retained, SCOPE)
    identity = {**SCOPE, 'evidence_ledger_id':'synthetic-ledger'}
    canonical = {'identity':identity,'assessment':{'canonical_scanner_finding_register':register}}
    record = {'identity':identity,'stage_results':{'final_comprehensive_report_generation':{'report_package':{'json':canonical}}}}
    before = deepcopy(record)
    projection = review_work_projection(record)
    packets = projection['review_assistance']['source_investigation']['packets']
    assert packets[0]['lexical_binding']['api'] == 'subprocess.run'
    assert len(projection['review_assistance']['queue']) == 1
    assert not projection['client_delivery_allowed']
    with pytest.raises(ValueError, match='review_work_not_ready'):
        assert_ready_for_approval(record)
    assert record == before


@pytest.mark.parametrize('call,expected', [
    ('sp.run(["/synthetic/tool"])', ('sequence_expression', 'absolute_literal', 'unspecified')),
    ('sp.run(["tool"], **options)', ('sequence_expression', 'relative_literal', 'unspecified')),
    ('sp.run(arguments, shell=flag)', ('dynamic_or_absent', 'unknown', 'dynamic')),
    ('sp.run(**options)', ('dynamic_or_absent', 'unknown', 'unspecified')),
    ('sp.run("tool", shell=False, **options)', ('literal_text', 'relative_literal', 'false')),
    ('sp.run("tool", shell=True)', ('literal_text', 'relative_literal', 'true')),
])
def test_argument_enum_round_trip_is_syntax_only_and_not_ui_contract(call, expected):
    candidate = row()
    result, _ = project(candidate, capture('import subprocess as sp\n'+call+'\n', candidate))
    restored = json.loads(json.dumps(result))
    assert restored['packets'][0]['argument_observations'] == dict(zip(pipeline.ARGUMENT_ENUMS, expected))
    assert len(json.dumps(restored['packets'][0]['argument_observations'])) < 160
    # Existing GET contract never exposed arguments; this change is lexical assistance.
    view = pipeline.display_investigation({'findings':[candidate], 'candidate_investigation':restored}, SCOPE)
    assert 'argument_observations' not in view['packets'][0]
    assert restored['human_review_required'] and not restored['client_delivery_allowed']


@pytest.mark.parametrize('field,value', [('argument_form','RAW_SOURCE_SENTINEL'),
    ('executable_path',['absolute_literal']), ('shell_keyword',False), ('shell_keyword','FALSE'),
    ('shell_keyword',None)])
def test_malformed_argument_enum_omitted_without_inventing_value(field, value):
    candidate = row()
    retained = capture('import subprocess as sp\nsp.run([])\n',candidate)
    call = retained['observations']['app.py']['calls']['2'][0]
    call[field] = value
    call['raw_arguments'] = 'RAW_ARGUMENT_SENTINEL'
    call['source_prose'] = 'RAW_SOURCE_SENTINEL'
    result, view = project(candidate,retained)
    args = result['packets'][0]['argument_observations']
    assert field not in args
    assert set(args) == set(pipeline.ARGUMENT_ENUMS)-{field}
    assert 'api_binding' not in args
    assert 'SENTINEL' not in json.dumps(result)
    assert 'argument_observations' not in view['packets'][0]


@pytest.mark.parametrize('arguments', [None, [], {'shell_keyword':'unspecified', 'api_binding':{'api':'RAW_SENTINEL'}, 'raw':'RAW_SENTINEL'}])
def test_legacy_packet_argument_extras_never_leak_into_projection(arguments):
    candidate = row(); result,_ = project(candidate,capture('import subprocess\nsubprocess.run([])\n',candidate))
    result['packets'][0].pop('lexical_binding')
    result['packets'][0]['argument_observations'] = arguments
    view = pipeline.display_investigation({'findings':[candidate], 'candidate_investigation':json.loads(json.dumps(result))}, SCOPE)
    assert view['available']
    assert 'lexical_binding' not in view['packets'][0]
    assert 'argument_observations' not in view['packets'][0]
    assert 'RAW_SENTINEL' not in json.dumps(view)
