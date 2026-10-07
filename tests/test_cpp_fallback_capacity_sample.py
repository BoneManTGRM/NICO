"""Owned inert controls. No source modules, Docker, target or analyzer executes."""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import types
import tempfile
import unittest
from unittest.mock import Mock, mock_open, patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/cpp_fallback_capacity_sample.py'
SPEC = importlib.util.spec_from_file_location('owned_capacity_sample', SOURCE)
SAMPLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SAMPLE)
FIXTURE_ROOT = Path(os.environ.get('CPP_SAMPLE_SOURCE_ROOT', Path(__file__).resolve().parents[1]))


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def owned_inputs():
    required = [digest(i) for i in range(577)]
    contexts = [{'context_id': required[i], 'index': i, 'analysis_file': '/work/source/owned' + str(i) + '.cpp',
        'invocation': ['/usr/lib/llvm-17/bin/clang++', '--analyze', 'owned' + str(i) + '.cpp'],
        'dropped_arguments': [], 'source_dependencies': {'owned.cpp': digest('source')},
        'generated_dependencies': {'owned.h': digest('generated')}} for i in range(576)]
    request = {'schema': 'nico.cpp-clang-fallback-request.v7', 'tool_version': '17.0.6',
        'primary_request_sha256': digest('primary'), 'cppcheck_evidence_sha256': digest('cppcheck'),
        'compiler_evidence_sha256': digest('compiler'), 'compiler_environment_sha256': digest('environment'),
        'required_contexts': required, 'primary_analyzed_contexts': [required[-1]],
        'contexts': contexts, 'limits': dict(SAMPLE.LIMITS),
        'header_tool_manifest_sha256': 'b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8',
        'header_source_targets': {'owned' + str(i) + '.cpp': digest('s' + str(i)) for i in range(3031)},
        'header_generated_files': {'g' + str(i) + '.h': {'bytes': 5, 'sha256': digest('g' + str(i))} for i in range(143)}}
    evidence = {'schema': 'nico.cpp-clang-fallback-evidence.v7', 'request_sha256': SAMPLE.sha(SAMPLE.canonical(request)),
        'records': [{'context_id': r['context_id'], 'invocation': r['invocation'],
                     'dropped_arguments': r['dropped_arguments'], 'execution': None} for r in contexts]}
    summary = {'source_population': 3031, 'snapshot_files': 143, 'generated_units': 42,
        'compiler_contexts': 577, 'historical_required_fallback_contexts': 576}
    return request, evidence, summary


def select_owned(request=None, evidence=None, summary=None):
    original = owned_inputs()
    request = original[0] if request is None else request
    evidence = original[1] if evidence is None else evidence
    summary = original[2] if summary is None else summary
    raw = SAMPLE.canonical(evidence)
    return SAMPLE.select_sample(request, raw, expected_fallback_sha256=SAMPLE.sha(raw), prepared_summary=summary)


def owned_envelope():
    request, binding = select_owned()
    return {'request': request, 'binding': binding}


def source_buffers():
    return {name: (FIXTURE_ROOT / name).read_bytes() for name in SAMPLE.SOURCE_PINS}


def data_only_program(buffers):
    # Reconstruct inert text from immutable source AST; never import or execute it.
    texts = {name: raw.decode() for name, raw in buffers.items()}
    trees = {name: ast.parse(raw) for name, raw in buffers.items()}
    values = {}
    for name in ['nico/assessment_cpp_clang_fallback.py', 'nico/assessment_cpp_clang_header_evidence.py']:
        for node in trees[name].body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in SAMPLE.CONSTANT_NAMES:
                    values[node.targets[0].id] = SAMPLE.static_value(node.value)
    node = next(node for node in trees['nico/assessment_cpp_project_snapshot.py'].body if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'PROJECT_GENERATED_MAX_FILE_BYTES' for t in node.targets))
    values['GENERATED_FILE_LIMIT'] = SAMPLE.static_value(node.value)
    result = 'import base64, hashlib, json, os, plistlib, re, stat, subprocess, time, zlib\n'
    result += 'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n'
    result += ''.join(name + '=' + repr(values[name]) + '\n' for name in SAMPLE.CONSTANT_NAMES)
    for name, file in SAMPLE.FUNCTION_SOURCES:
        path = 'nico/' + file
        node = next(node for node in trees[path].body if isinstance(node, ast.FunctionDef) and node.name == name)
        result += ast.get_source_segment(texts[path], node) + '\n\n'
    return result + 'run_clang_fallback()\n'


def unknown_group():
    return {'scope': 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT',
        'observation_ms': 0.1, 'files': {name: {'status': 'UNKNOWN', 'values': None} for name in SAMPLE.CGROUP_FILES}}


def child(user, system):
    return {'status': 'OBSERVED', 'user_seconds': user, 'system_seconds': system,
        'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER', 'observation_ms': 0.1}


def measured_owned(*, failure=None, allocation=480000, write_failure=False):
    envelope = owned_envelope();result = {'schema': 'owned-result', 'findings': ['owned-genuine-finding']}
    collector = Mock(return_value=result, side_effect=failure)
    group = unknown_group();opened = mock_open()
    # Separate explicit contexts avoid clever patch expressions hiding semantics.
    with patch.object(SAMPLE, 'cgroup_snapshot', side_effect=[group, group]), \
         patch.object(SAMPLE, 'children_snapshot', side_effect=[child(1.0, 2.0), child(4.0, 2.5)]), \
         patch.object(Path, 'open', side_effect=OSError('owned-private-path')) if write_failure else patch.object(Path, 'open', opened):
        if failure is None:
            returned = SAMPLE.measure_collector(collector, envelope, wall_budget_ms=allocation)
        else:
            try:
                SAMPLE.measure_collector(collector, envelope, wall_budget_ms=allocation)
            except BaseException as caught:
                returned = caught
    chunks = [call.args[0] for call in opened().write.call_args_list]
    raw = b''.join(chunks)
    return envelope, result, collector, returned, raw


class Controls(unittest.TestCase):
    def reject(self, code, function, *args, **kwargs):
        with self.assertRaisesRegex(ValueError, '^' + code + '$'):
            function(*args, **kwargs)

    def test_selection_preserves_original_indices_all_maps_and_full_obligations(self):
        request, evidence, summary = owned_inputs();before = SAMPLE.canonical(request)
        selected, binding = select_owned(request, evidence, summary)
        self.assertEqual([row['index'] for row in selected['contexts']], [0, 58, 154, 186])
        self.assertEqual(selected['contexts'], [request['contexts'][i] for i in SAMPLE.SELECTED_INDICES])
        self.assertEqual({k:v for k,v in selected.items() if k != 'contexts'}, {k:v for k,v in request.items() if k != 'contexts'})
        self.assertEqual(SAMPLE.canonical(request), before)
        self.assertEqual(binding['obligations']['unsampled_status'], 'UNMEASURED')
        self.assertEqual(binding['obligations']['full_fallback_contexts'], 576)
        self.assertFalse(binding['full_native_qualified'])
        SAMPLE.check_envelope({'request': selected, 'binding': binding})

    def test_wrong_independent_raw_anchor_and_reconstructed_request_hash_reject(self):
        request, evidence, summary = owned_inputs();raw = SAMPLE.canonical(evidence)
        self.reject('sample_evidence_anchor', SAMPLE.select_sample, request, raw,
            expected_fallback_sha256='0' * 64, prepared_summary=summary)
        request['contexts'][58]['generated_dependencies']['owned.h'] = digest('different')
        self.reject('sample_reconstructed_request_binding', SAMPLE.select_sample, request, raw,
            expected_fallback_sha256=SAMPLE.sha(raw), prepared_summary=summary)

    def test_exact_invocations_and_dropped_flags_cannot_be_changed(self):
        for key, value in [('invocation', ['owned-other-command']), ('dropped_arguments', ['owned-drop'])]:
            request, evidence, summary = owned_inputs();evidence['records'][58][key] = value
            raw = SAMPLE.canonical(evidence)
            self.reject('sample_context_binding', SAMPLE.select_sample, request, raw,
                expected_fallback_sha256=SAMPLE.sha(raw), prepared_summary=summary)

    def test_selected_original_index_is_not_renumbered_list_position(self):
        request, evidence, summary = owned_inputs()
        request['contexts'][186]['index'], request['contexts'][187]['index'] = 187,186
        evidence['request_sha256'] = SAMPLE.sha(SAMPLE.canonical(request))
        self.reject('sample_selected_original_indices', select_owned, request, evidence, summary)

    def test_full_population_header_generated_and_policy_cannot_shrink(self):
        for mutate, code in [(lambda r:r['contexts'].pop(), 'sample_full_population'),
                (lambda r:r['header_source_targets'].pop('owned0.cpp'), 'sample_full_header_population'),
                (lambda r:r['header_generated_files'].pop('g0.h'), 'sample_full_header_population'),
                (lambda r:r['limits'].update(parallel=1), 'sample_request_policy'),
                (lambda r:r['limits'].update(case_seconds=121), 'sample_request_policy')]:
            request, evidence, summary = owned_inputs();mutate(request)
            evidence['request_sha256'] = SAMPLE.sha(SAMPLE.canonical(request))
            self.reject(code, select_owned, request, evidence, summary)

    def test_duplicate_contexts_and_boolean_preparation_counts_reject(self):
        request, evidence, summary = owned_inputs();request['contexts'][1] = copy.deepcopy(request['contexts'][0])
        evidence['records'][1] = copy.deepcopy(evidence['records'][0]);evidence['request_sha256'] = SAMPLE.sha(SAMPLE.canonical(request))
        self.reject('sample_context_binding', select_owned, request, evidence, summary)
        request,evidence,summary=owned_inputs();summary['generated_units']=True
        self.reject('sample_prepared_population', select_owned, request, evidence, summary)

    def test_exact_program_function_buffers_and_source_pins_are_bound(self):
        buffers = source_buffers();program = data_only_program(buffers)
        prefix = SAMPLE.verified_program_prefix(program, buffers)
        expected = SAMPLE.sha(SOURCE.read_bytes())
        new, proof = SAMPLE.build_worker_program(program, buffers, expected_sample_sha256=expected)
        self.assertEqual(proof['sample_module_sha256'], expected)
        self.assertTrue(new.startswith(prefix));self.assertTrue(new.endswith('\nrun_capacity_sample()\n'))
        self.assertEqual(proof['original_program_sha256'], SAMPLE.sha(program.encode()))
        self.assertTrue(proof['original_function_buffers_verified'])
        self.assertEqual(sum(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name)
            and n.value.func.id=='run_capacity_sample' for n in ast.parse(new).body),1)

    def test_changed_source_body_top_level_call_and_constant_are_rejected(self):
        buffers = source_buffers();program = data_only_program(buffers)
        changed = dict(buffers);changed['nico/assessment_cpp_compiler_evidence.py'] += b'# mutation\n'
        self.reject('sample_program_source_pin', SAMPLE.verified_program_prefix, program, changed)
        self.reject('sample_program_top_level', SAMPLE.verified_program_prefix, program + 'owned_call()\n', buffers)
        self.reject('sample_program_constant_binding', SAMPLE.verified_program_prefix,
            program.replace("LOW_CONTENTION_LIMITS={'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}",
                            "LOW_CONTENTION_LIMITS={'wall_seconds': 481, 'case_seconds': 120, 'parallel': 2}"), buffers)

    def test_wrong_independent_instrumentation_source_hash_rejects(self):
        buffers = source_buffers();program = data_only_program(buffers)
        self.reject('sample_instrumentation_source_binding', SAMPLE.build_worker_program,
            program, buffers, expected_sample_sha256='0' * 64)

    def test_same_length_changed_instrumentation_reread_rejects(self):
        buffers = source_buffers();program = data_only_program(buffers)
        original = SOURCE.read_bytes();expected = SAMPLE.sha(original)
        changed = original.replace(b'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER',
                                   b'BLL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER')
        self.assertNotEqual(original, changed);self.assertEqual(len(original),len(changed))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'owned-mutated-sample.py';path.write_bytes(changed)
            with patch.object(SAMPLE,'__file__',str(path)):
                self.reject('sample_instrumentation_source_binding', SAMPLE.build_worker_program,
                    program, buffers, expected_sample_sha256=expected)

    def test_changed_run_body_and_duplicate_terminal_reject_without_self_pin(self):
        buffers=source_buffers();program=data_only_program(buffers)
        self.reject('sample_program_function_binding', SAMPLE.verified_program_prefix,
            program.replace('start_new_session=True, shell=False', 'start_new_session=True, shell=True'), buffers)
        self.reject('sample_program_top_level', SAMPLE.verified_program_prefix,
            program + 'run_clang_fallback()\n', buffers)

    def test_cgroup_counter_pressure_and_bound_parsers_preserve_values(self):
        self.assertEqual(SAMPLE.parse_cgroup('memory.events', b'low 0\nhigh 1\nmax 2\noom 3\noom_kill 4\n')['oom_kill'],4)
        self.assertEqual(SAMPLE.parse_cgroup('cpu.stat', b'usage_usec 10\nuser_usec 8\nsystem_usec 2\n')['usage_usec'],10)
        self.assertEqual(SAMPLE.parse_cgroup('memory.peak', b'12884901888\n')['bytes'],12*1024**3)
        self.assertEqual(SAMPLE.parse_cgroup('memory.pressure', b'some avg10=1.00 avg60=2.00 avg300=3.00 total=123\n')['some']['total'],123)

    def test_malformed_duplicate_missing_nonfinite_and_oversized_cgroup_reject(self):
        for name, raw in [('cpu.stat', b'usage_usec 1\nusage_usec 2\n'), ('memory.events', b'oom 1\n'),
                ('cpu.stat', b'usage_usec -1\nuser_usec 0\nsystem_usec 0\n'),
                ('cpu.pressure', b'some avg10=NaN avg60=0 avg300=0 total=1\n'),
                ('memory.peak', b'1' * 32769)]:
            with self.subTest(name=name), self.assertRaises(ValueError): SAMPLE.parse_cgroup(name,raw)

    def test_missing_snapshots_stay_unknown_and_counter_reset_is_not_zero(self):
        before=unknown_group();after=copy.deepcopy(before)
        self.assertTrue(all(row['values'] is None for row in SAMPLE.counter_deltas(before,after).values()))
        before['files']['cpu.stat']={'status':'OBSERVED','values':{'usage_usec':10,'user_usec':8,'system_usec':2}}
        after['files']['cpu.stat']={'status':'OBSERVED','values':{'usage_usec':5,'user_usec':4,'system_usec':1}}
        self.assertEqual(SAMPLE.counter_deltas(before,after)['cpu.stat'],{'status':'UNKNOWN','values':None})

    def test_child_usage_scope_includes_version_and_is_not_per_context(self):
        envelope,result,collector,returned,raw=measured_owned()
        self.assertIs(returned,result);collector.assert_called_once_with(envelope['request'],wall_budget_ms=480000)
        telemetry=json.loads(raw)
        self.assertEqual(telemetry['children']['scope'],'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER')
        self.assertEqual(telemetry['children']['delta'],{'user_seconds':3.0,'system_seconds':0.5,'total_seconds':3.5})
        self.assertTrue(telemetry['children']['includes_version_probe'])
        self.assertFalse(telemetry['children']['per_context_cpu_available'])
        self.assertIsNone(telemetry['cgroup']['delta']['cpu.stat']['values'])

    def test_actual_parent_remaining_allocation_is_forwarded_without_growth(self):
        envelope,result,collector,returned,raw=measured_owned(allocation=479123)
        collector.assert_called_once_with(envelope['request'],wall_budget_ms=479123)
        self.assertEqual(json.loads(raw)['actual_wall_budget_ms'],479123)
        for invalid in [0,480001,True]:
            self.reject('sample_runtime_allocation', SAMPLE.measure_collector, Mock(), envelope, wall_budget_ms=invalid)

    def test_original_collector_exception_is_preserved_with_unproven_telemetry(self):
        error=ValueError('worker_clang_fallback_tool_version')
        envelope,result,collector,caught,raw=measured_owned(failure=error)
        self.assertIs(caught,error);telemetry=json.loads(raw)
        self.assertEqual(telemetry['status'],'UNPROVEN');self.assertIsNone(telemetry['evidence_sha256'])
        self.assertEqual(telemetry['collector_error_type'],'ValueError')

    def test_sidecar_failure_keeps_genuine_result_and_error(self):
        envelope,result,collector,returned,raw=measured_owned(write_failure=True)
        self.assertIs(returned,result);self.assertTrue(SAMPLE.TELEMETRY_WRITE_FAILED)
        error=ValueError('worker_clang_fallback_tool_version')
        _,_,_,caught,_=measured_owned(failure=error,write_failure=True)
        self.assertIs(caught,error);self.assertTrue(SAMPLE.TELEMETRY_WRITE_FAILED)

    def test_closed_telemetry_validator_binds_actual_raw_and_allocation(self):
        envelope,result,collector,returned,raw=measured_owned()
        value=SAMPLE.validate_sample_telemetry(raw,envelope,SAMPLE.canonical(result)+b'\n',actual_wall_budget_ms=480000)
        self.assertEqual(value['status'],'COLLECTOR_RETURNED')
        self.reject('sample_telemetry_identity',SAMPLE.validate_sample_telemetry,raw,envelope,b'{"different":true}',actual_wall_budget_ms=480000)
        self.reject('sample_telemetry_identity',SAMPLE.validate_sample_telemetry,raw,envelope,SAMPLE.canonical(result),actual_wall_budget_ms=479999)

    def test_telemetry_scope_deltas_and_extra_private_fields_reject(self):
        envelope,result,collector,returned,raw=measured_owned();value=json.loads(raw)
        changed=copy.deepcopy(value);changed['private_path']='/owned/private'
        self.reject('sample_telemetry_identity',SAMPLE.validate_sample_telemetry,SAMPLE.canonical(changed),envelope,SAMPLE.canonical(result),actual_wall_budget_ms=480000)
        changed=copy.deepcopy(value);changed['children']['per_context_cpu_available']=True
        self.reject('sample_telemetry_children_scope',SAMPLE.validate_sample_telemetry,SAMPLE.canonical(changed),envelope,SAMPLE.canonical(result),actual_wall_budget_ms=480000)
        changed=copy.deepcopy(value);changed['children']['delta']['total_seconds']=999
        self.reject('sample_telemetry_children_delta',SAMPLE.validate_sample_telemetry,SAMPLE.canonical(changed),envelope,SAMPLE.canonical(result),actual_wall_budget_ms=480000)
        changed=copy.deepcopy(value);changed['cgroup']['delta']['cpu.stat']={'status':'OBSERVED_DELTA','values':{'usage_usec':0}}
        self.reject('sample_telemetry_cgroup_delta',SAMPLE.validate_sample_telemetry,SAMPLE.canonical(changed),envelope,SAMPLE.canonical(result),actual_wall_budget_ms=480000)

    def test_runtime_envelope_rejects_dependency_mutation_and_fake_scope(self):
        envelope=owned_envelope();envelope['request']['contexts'][0]['source_dependencies']['owned.cpp']=digest('changed')
        self.reject('sample_runtime_binding',SAMPLE.check_envelope,envelope)
        envelope=owned_envelope();envelope['binding']['obligations']['unsampled_status']='UNSTARTED'
        self.reject('sample_runtime_scope',SAMPLE.check_envelope,envelope)
        envelope=owned_envelope();envelope['binding']['private_history']='forbidden'
        self.reject('sample_runtime_binding',SAMPLE.check_envelope,envelope)


if __name__ == '__main__':
    unittest.main()
