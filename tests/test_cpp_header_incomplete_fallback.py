"""Current installed header-only fallback controls; native proof is separate."""
import base64
from copy import deepcopy
import hashlib
import json
from xml.etree import ElementTree as ET

import pytest
from nico import assessment_cpp_clang_fallback as clang
from nico import assessment_cpp_project_static as static
from nico import assessment_cpp_static_environment as env
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_clang_fallback import fallback_native
from tests.test_cpp_clang_header_transport import fixture as tool_fixture
from tests.test_cpp_completed_static_collection import fixture, validate
from tests.test_cpp_static_environment import evidence as environment_evidence, observed


def owned_header_gap(tmp_path):
    req, compiler, raw, _, inputs = fixture(tmp_path, failing=False, include_inputs=True)
    data = json.loads(raw)
    row = data['records'][0]
    doc = ET.fromstring(static._decode_xml(row['header_trace'], row['header_trace_sha256'], row['header_trace_encoding']))
    cfg = doc.find('configuration')
    cfg.set('completed', 'false'); cfg.set('preprocessing_had_output', 'true')
    cfg.insert(len(cfg) - 2, ET.Element('include', file='vector', parent=row['invocation'][0], kind='missing', entered='false'))
    row['header_trace'], row['header_trace_sha256'], row['header_trace_encoding'] = static._encode_xml(ET.tostring(doc), compact=True)
    raw = _canonical(data)
    primary = static.validate_project_static(raw, req)
    assert primary['complete'] and not primary['header_context_evidence_complete']
    return req, compiler, raw, primary, inputs


def native_response(tmp_path, req, primary):
    freq = clang.clang_fallback_request(req, primary, extended_budget=True, contention_aware=True, multi_file_diagnostics=True)
    value = fallback_native(freq)
    scratch = tmp_path / 'tool'; scratch.mkdir()
    _, _, _, shape = tool_fixture(scratch)
    value.update({k: shape[k] for k in ('header_tool_receipt', 'header_tool_receipt_sha256')})
    for context, row in zip(freq['contexts'], value['records']):
        trace = {'schema': 'nico.clang-header-observer.v1', 'clang_version': '17.0.6',
            'source': context['analysis_file'], 'context_id': context['context_id'],
            'standard': clang._clang_standard(context), 'translation_unit_started': True,
            'translation_unit_ended': True, 'diagnostic_errors': False, 'observation_overflow': False,
            'files': [{'path': context['analysis_file'], 'entered': 1, 'ast_decl_nodes': 1,
                'ast_stmt_nodes': 1, 'ast_body_callbacks': 1, 'initially_system': False,
                'system_header_pragma_observed': False}]}
        row['header_trace'], row['header_trace_sha256'] = clang._encode_plist(_canonical(trace))
    return freq, value


def test_current_header_only_gap_dispatches_exact_context_with_fixed_budget(tmp_path):
    req, _, _, primary, _ = owned_header_gap(tmp_path)
    freq = clang.clang_fallback_request(req, primary, extended_budget=True, contention_aware=True, multi_file_diagnostics=True)
    assert [c['context_id'] for c in freq['contexts']] == [req['contexts'][0]['context_id']]
    assert freq['schema'] == 'nico.cpp-clang-fallback-request.v7'
    assert freq['primary_analyzed_contexts'] == primary['analyzed_contexts']
    assert freq['limits'] == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
    assert freq['primary_request_sha256'] == hashlib.sha256(_canonical(req)).hexdigest()
    historical = deepcopy(req); historical['schema'] = 'nico.cpp-project-static-request.v3'; historical.pop('compiler_collection')
    old = clang.clang_fallback_request(historical, primary, extended_budget=True, contention_aware=True, multi_file_diagnostics=True)
    assert old['schema'] == 'nico.cpp-clang-fallback-request.v5' and old['contexts'] == []


def test_current_valid_header_fallback_retains_primary_truth_and_completes_collection(tmp_path):
    req, compiler, raw, primary, _ = owned_header_gap(tmp_path)
    freq, value = native_response(tmp_path, req, primary)
    assert len(freq['contexts']) == 1
    proof = validate(req, compiler, raw, _canonical(value))
    chosen = proof['analysis']['header_context_evidence'][0]
    assert proof['collection_complete'] and proof['analysis']['header_context_evidence_complete']
    assert chosen['native_execution_verified'] and chosen['normal_pass_completed']
    assert chosen['primary_observation'] == primary['header_context_evidence'][0]
    assert chosen['primary_observation']['normal_pass_completed'] is False
    assert proof['analysis']['findings'] == primary['findings']
    assert proof['analysis']['modeled_inputs'] == primary['modeled_inputs']


@pytest.mark.parametrize('fault', ['consistent-legacy-receipt', 'legacy-primary'])
def test_current_header_policy_cannot_be_downgraded_by_matching_receipt_hashes(tmp_path, fault):
    req, _, _, primary, _ = owned_header_gap(tmp_path)
    freq, value = native_response(tmp_path, req, primary)
    assert clang.validate_clang_fallback(_canonical(value), freq, req)['complete']
    if fault == 'consistent-legacy-receipt':
        freq['schema'] = 'nico.cpp-clang-fallback-request.v5'
        value['schema'] = 'nico.cpp-clang-fallback-evidence.v5'
        value['request_sha256'] = hashlib.sha256(_canonical(freq)).hexdigest()
    else:
        req['schema'] = 'nico.cpp-project-static-request.v3'; req.pop('compiler_collection')
    with pytest.raises(ValueError, match='worker_clang_fallback_header_policy_invalid'):
        clang.validate_clang_fallback(_canonical(value), freq, req)


@pytest.mark.parametrize('fault', ['legacy', 'missing-trace', 'incomplete-trace', 'native-failed'])
def test_current_missing_or_downgraded_header_fallback_cannot_close_collection(tmp_path, fault):
    req, compiler, raw, primary, _ = owned_header_gap(tmp_path)
    freq, value = native_response(tmp_path, req, primary)
    assert len(freq['contexts']) == 1
    row = value['records'][0]
    if fault == 'legacy': value['schema'] = 'nico.cpp-clang-fallback-evidence.v5'
    elif fault == 'missing-trace': row.update(header_trace='', header_trace_sha256=None)
    elif fault == 'native-failed': row['execution']['exit_code'] = 1
    else:
        trace = json.loads(clang._decode_plist(row['header_trace'], row['header_trace_sha256']))
        trace['translation_unit_ended'] = False
        row['header_trace'], row['header_trace_sha256'] = clang._encode_plist(_canonical(trace))
    with pytest.raises(ValueError): validate(req, compiler, raw, _canonical(value))


def test_installed_stage_dispatches_header_only_gap_before_collection_validation(tmp_path):
    from tests.test_cpp_project_static_stage import StaticDocker
    req, _, raw, primary, (database, targets, snapshot, craw) = owned_header_gap(tmp_path)
    _, value = native_response(tmp_path, req, primary)
    class OwnedDocker(StaticDocker):
        def __call__(self, argv, **kwargs):
            if env.ENV_PROGRAM in argv:
                er = json.loads(kwargs['input_bytes']); data = environment_evidence(er); data['schema'] = 'nico.cpp-static-environment.v2'
                for q in data['queries'].values(): q['predefines'] = observed(base64.b64decode(q['predefines']['output']) + b'#define __cplusplus 202002L\n')
                output = _canonical(data)
            elif static.PROGRAM in argv:
                assert json.loads(kwargs['input_bytes']) == req; output = raw
            elif clang.PROGRAM in argv:
                assert hashlib.sha256(kwargs['input_bytes']).hexdigest() == value['request_sha256']
                value['wall_budget_ms'] = int(argv[-1]); output = _canonical(value)
            else: return super().__call__(argv, **kwargs)
            self.calls.append((argv, kwargs)); return dict(exit_code=0, timed_out=False, output_truncated=False, output=output)
    source = tmp_path / 'source'; source.mkdir(); (source / 'unit.cpp').write_bytes(b'int value(){return VALUE;}\n')
    artifacts = {}
    def sink(key, output):
        artifacts[key] = output; sha = hashlib.sha256(output).hexdigest()
        return dict(path='artifacts/' + key + '-' + sha + '.json', sha256=sha, bytes=len(output))
    result = static.run_project_static_stage(source, targets, 'sha256:' + 'a'*64, database, snapshot, craw,
        compiler_environment=True, header_provenance=True, collect_completed_compiler_failures=True,
        command=OwnedDocker(targets), retain_artifact=sink)
    assert 'project-static-clang-fallback' in artifacts
    assert result['collection_complete'], result['error']
    assert result['execution_budget_seconds'] == 1020 and result['wall_budget_seconds'] == 1030
    assert result['cleanup_verified']
