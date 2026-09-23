"""Frozen, bounded libFuzzer plans and canonical reconstruction of native results.

Replay of retained seed files and a coverage-guided campaign are different
observations. libFuzzer counters are tool-reported, not source coverage. Older
contracts do not acquire fuzz execution or qualification through this module.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

CLANG = '/usr/lib/llvm-17/bin/clang'
CLANGXX = '/usr/lib/llvm-17/bin/clang++'
VERSION = '17.0.6'
LIMITATION = 'Bounded libFuzzer results cover the selected immutable binaries and corpus only; counters are tool-reported, not exhaustive vulnerability or source coverage.'


from nico.comprehensive_coverage_reconciliation_v1 import COPY_ES
COPY_ES[LIMITATION] = 'Los resultados acotados de libFuzzer abarcan solo los binarios inmutables y el corpus seleccionados; los contadores provienen de la herramienta y no representan cobertura exhaustiva de vulnerabilidades ni del código.'


def _path(value):
    return (isinstance(value, str) and len(value) <= 500
        and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*', value) is not None
        and all(p not in {'', '.', '..', '.git'} for p in value.split('/')))


def fuzz_plan(*, build_targets, cmake_options, targets, runs=256, seconds=2, seed=1):
    return {'schema': 'nico.cpp-bounded-fuzz-plan.v1', 'compiler_version': VERSION,
        'build_targets': sorted(build_targets), 'cmake_options': dict(cmake_options),
        'targets': deepcopy(targets), 'runs': runs, 'seconds': seconds, 'seed': seed,
        'max_len': 4096, 'rss_limit_mb': 768}


def validate_plan(plan, source_hashes):
    fields = {'schema', 'compiler_version', 'build_targets', 'cmake_options', 'targets',
              'runs', 'seconds', 'seed', 'max_len', 'rss_limit_mb'}
    if (not isinstance(plan, dict) or set(plan) != fields
            or plan['schema'] != 'nico.cpp-bounded-fuzz-plan.v1' or plan['compiler_version'] != VERSION):
        raise ValueError('worker_fuzz_plan_invalid')
    for key, minimum, maximum in [('runs', 64, 4096), ('seconds', 1, 10), ('seed', 1, 2147483647),
                                  ('max_len', 1, 4096), ('rss_limit_mb', 64, 768)]:
        if type(plan[key]) is not int or not minimum <= plan[key] <= maximum:
            raise ValueError('worker_fuzz_budget_invalid')
    names = plan['build_targets']
    if (not isinstance(names, list) or not 1 <= len(names) <= 2
            or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_+-]{0,100}', n) for n in names)
            or names != sorted(set(names))):
        raise ValueError('worker_fuzz_build_targets_invalid')
    options = plan['cmake_options']
    if (not isinstance(options, dict) or len(options) > 32
            or any(not isinstance(k, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', k)
                or k.startswith('CMAKE_') or not isinstance(v, str)
                or not re.fullmatch(r'[A-Za-z0-9_./+-]{1,120}', v) for k, v in options.items())):
        raise ValueError('worker_fuzz_options_invalid')
    rows = plan['targets']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2:
        raise ValueError('worker_fuzz_targets_invalid')
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'name', 'binary', 'corpus', 'environment'}
                or not isinstance(row['name'], str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_+-]{0,100}', row['name'])
                or not _path(row['binary']) or not isinstance(row['corpus'], list)
                or not 1 <= len(row['corpus']) <= 8 or any(not _path(p) or p not in source_hashes for p in row['corpus'])
                or row['corpus'] != sorted(set(row['corpus']))
                or not isinstance(row['environment'], dict) or not set(row['environment']) <= {'FUZZ'}
                or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_+-]{1,100}', v) for v in row['environment'].values())):
            raise ValueError('worker_fuzz_target_binding_invalid')
    if [r['name'] for r in rows] != sorted({r['name'] for r in rows}):
        raise ValueError('worker_fuzz_target_population_invalid')
    # Per-input replay ceilings plus campaigns are also bounded in aggregate.
    if sum(len(r['corpus']) * 2 + plan['seconds'] + 2 for r in rows) > 60:
        raise ValueError('worker_fuzz_aggregate_budget_invalid')
    return deepcopy(plan)


def phase_name(index, phase, seed_index=None):
    if phase == 'campaign': return f't{index}-campaign'
    if phase == 'replay' and type(seed_index) is int and 0 <= seed_index < 8:
        return f't{index}-seed{seed_index}'
    raise ValueError('worker_fuzz_phase_invalid')


def runtime_user(index, phase, seed_index=None):
    phase_name(index, phase, seed_index)
    uid = 3000 + index * 16 + (8 if phase == 'campaign' else seed_index)
    return f'{uid}:{uid}'


def target_arguments(plan, index, *, phase, seed_index=None):
    name = phase_name(index, phase, seed_index)
    path = f'/work/fuzz-snapshots/t{index}/program'
    args = [path, '-runs=' + str(plan['runs'] if phase == 'campaign' else 1),
        '-max_total_time=' + str(plan['seconds'] if phase == 'campaign' else 2),
        '-timeout=1', '-rss_limit_mb=' + str(plan['rss_limit_mb']), '-malloc_limit_mb=256',
        '-max_len=' + str(plan['max_len']), '-seed=' + str(plan['seed']), '-jobs=0',
        '-workers=1', '-fork=0', '-reload=0', '-print_final_stats=1', '-detect_leaks=0',
        '-exact_artifact_path=/work/fuzz-runs/' + name + '/failure.bin']
    if phase == 'campaign':
        args += ['/work/fuzz-runs/' + name + '/corpus', f'/work/fuzz-snapshots/t{index}/seeds']
    else:
        args += [f'/work/fuzz-snapshots/t{index}/s{seed_index}']
    return args


def build_steps(plan):
    flags = '-fsanitize=fuzzer-no-link,address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -fno-pie'
    configure = ['cmake', '-S', '/work/source', '-B', '/work/fuzz-build', '-G', 'Unix Makefiles',
        '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_C_COMPILER=' + CLANG, '-DCMAKE_CXX_COMPILER=' + CLANGXX,
        '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
        '-DCMAKE_C_FLAGS=' + flags, '-DCMAKE_CXX_FLAGS=' + flags,
        '-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=fuzzer,address,undefined -no-pie']
    configure += ['-D' + k + '=' + v for k, v in sorted(plan['cmake_options'].items())]
    return [( 'fuzz-compiler-version', [CLANG, '-dumpversion'], ()),
            ('fuzz-configure', configure, ('cmake-version', 'fuzz-compiler-version')),
            ('fuzz-build', ['cmake', '--build', '/work/fuzz-build', '--parallel', '1', '--target', *plan['build_targets']], ('fuzz-configure',))]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def inspect_symbols(value):
    if not isinstance(value, dict) or set(value) != {'symbols', 'nm_sha256', 'nm_bytes', 'dynamic', 'interpreter'}:
        raise ValueError('worker_fuzz_inspection_invalid')
    from nico.assessment_cpp_configuration import decode_stream
    from nico.assessment_cpp_native_tests import inspect_dynamic_paths
    if (not isinstance(value['symbols'], list) or any(not isinstance(v, str) for v in value['symbols'])
            or value['symbols'] != sorted(set(value['symbols']))
            or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', v) for v in value['symbols'])
            or not isinstance(value['nm_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', value['nm_sha256'])
            or type(value['nm_bytes']) is not int or not 0 < value['nm_bytes'] <= 2097152):
        raise ValueError('worker_fuzz_inspection_invalid')
    dynamic = decode_stream(value['dynamic']); interpreter = decode_stream(value['interpreter'])
    symbols = set(value['symbols'])
    required = {'LLVMFuzzerTestOneInput', 'LLVMFuzzerRunDriver', '__sanitizer_cov_8bit_counters_init', '__asan_init'}
    loaders = re.findall(rb'Requesting program interpreter: ([^\]]+)\]', interpreter)
    return (required <= symbols and inspect_dynamic_paths(dynamic)
            and loaders == [b'/lib64/ld-linux-x86-64.so.2'])


def validate_evidence(value, plan, source_hashes):
    """Reconstruct flags, identities, outcomes, and tool-reported work separately."""
    from nico.assessment_cpp_fuzz_runtime import operation_specs, SNAPSHOT_PROGRAM
    from nico.assessment_cpp_configuration import decode_stream
    from nico.assessment_cpp_full_project import _json
    plan = validate_plan(plan, source_hashes)
    if (not isinstance(value, dict) or set(value) != {'schema', 'plan_sha256', 'operations', 'error'}
            or value['schema'] != 'nico.cpp-fuzz-native.v1' or value['plan_sha256'] != _digest(plan)
            or not isinstance(value['operations'], list) or value['error'] not in (
                None, 'worker_fuzz_controller_failed', 'worker_fuzz_native_failed', 'worker_fuzz_interrupted')):
        raise ValueError('worker_fuzz_evidence_invalid')
    specs = operation_specs(plan, source_hashes)
    if len(value['operations']) != len(specs): raise ValueError('worker_fuzz_operation_population_invalid')
    outputs, okay, rows = {}, {}, {}
    for row, spec in zip(value['operations'], specs):
        if (not isinstance(row, dict) or set(row) != {'id', 'invocation', 'user', 'input_sha256', 'attempted',
                'exit_code', 'timed_out', 'output_truncated', 'duration_ms', 'output', 'output_sha256'}
                or row['id'] != spec['id'] or row['invocation'] != spec['argv'] or row['user'] != spec['user']
                or ('snapshot_input' not in spec and row['input_sha256'] != spec['input_sha256'])
                or (row['input_sha256'] is not None and (not isinstance(row['input_sha256'], str)
                    or re.fullmatch(r'[0-9a-f]{64}', row['input_sha256']) is None))
                or any(type(row[k]) is not bool for k in ('attempted', 'timed_out', 'output_truncated'))
                or type(row['duration_ms']) is not int or not 0 <= row['duration_ms'] <= 32000
                or (row['attempted'] and (type(row['exit_code']) is not int or not -255 <= row['exit_code'] <= 255))
                or (not row['attempted'] and (row['exit_code'] is not None or row['duration_ms'] or row['timed_out'] or row['output_truncated']))):
            raise ValueError('worker_fuzz_operation_invalid')
        out = decode_stream(row['output'])
        if (len(out) > 65536 or hashlib.sha256(out).hexdigest() != row['output_sha256']
                or (not row['attempted'] and out)):
            raise ValueError('worker_fuzz_output_binding_invalid')
        outputs[row['id']], rows[row['id']] = out, row
        okay[row['id']] = row['attempted'] and row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated']
    snapshot = _json(outputs['snapshot']) if okay['snapshot'] else None
    if snapshot is not None:
        validate_snapshots(snapshot, plan, source_hashes)
    results = []
    for index, target in enumerate(plan['targets']):
        prefix = f't{index}'
        inspected = bool(snapshot and okay[prefix + '-inspect'] and inspect_symbols(_json(outputs[prefix + '-inspect'])))
        phases = []
        for phase, seed_index in [('replay', i) for i in range(len(target['corpus']))] + [('campaign', None)]:
            name = phase_name(index, phase, seed_index)
            bound = False
            if snapshot and inspected and okay[name + '-probe'] and okay[name + '-after']:
                probe = _json(outputs[name + '-probe']); after = _json(outputs[name + '-after'])
                uid = int(runtime_user(index, phase, seed_index).split(':')[0])
                from nico.assessment_cpp_fuzz_runtime import _json_bytes
                if rows[name + '-after']['input_sha256'] != hashlib.sha256(_json_bytes(snapshot[prefix])).hexdigest():
                    raise ValueError('worker_fuzz_verification_input_invalid')
                expected = {'uid': uid, 'gid': uid, 'write_denied': True,
                    'binary_sha256': snapshot[prefix]['sha256'], 'no_new_privileges': True,
                    'capabilities': 0, 'credential_environment_absent': True}
                bound = (probe == expected and all(type(probe[k]) is int for k in ('uid', 'gid', 'capabilities'))
                    and all(type(probe[k]) is bool for k in ('write_denied', 'no_new_privileges', 'credential_environment_absent'))
                    and after == snapshot[prefix])
            run = rows[name + '-run']; out = outputs[name + '-run']
            telemetry = False; reported = None
            if phase == 'campaign':
                numbers = re.findall(rb'^stat::number_of_executed_units:\s*([0-9]+)\s*$', out, re.M)
                if len(numbers) == 1:
                    reported = int(numbers[0]); telemetry = 0 < reported <= plan['runs'] and bool(re.search(rb'^#[0-9]+\s+DONE\b', out, re.M))
            else:
                expected_path = f'/work/fuzz-snapshots/t{index}/s{seed_index}'.encode()
                telemetry = bool(re.search(rb'^Executed ' + re.escape(expected_path) + rb' in [0-9]+ ms\s*$', out, re.M))
            artifact = None
            if okay[name + '-artifact']:
                artifact = _json(outputs[name + '-artifact'])
                if not isinstance(artifact, dict) or set(artifact) != {'present', 'bytes', 'sha256', 'data'} or type(artifact['present']) is not bool:
                    raise ValueError('worker_fuzz_artifact_invalid')
                data = decode_stream(artifact['data'])
                if (type(artifact['bytes']) is not int or len(data) != artifact['bytes'] or len(data) > plan['max_len']
                        or artifact['sha256'] != (hashlib.sha256(data).hexdigest() if artifact['present'] else None)
                        or (not artifact['present'] and data)):
                    raise ValueError('worker_fuzz_artifact_invalid')
            completed = bool(bound and okay[name + '-run'] and telemetry and artifact and not artifact['present'])
            status = ('not_attempted' if not run['attempted'] else 'timed_out' if run['timed_out'] else
                      'failed' if run['exit_code'] != 0 else 'completed' if completed else 'partial')
            phases.append({'phase': phase, 'seed_path': target['corpus'][seed_index] if phase == 'replay' else None,
                'status': status, 'exit_code': run['exit_code'], 'binary_bound': bool(bound and run['attempted']),
                'tool_reported_executions': reported, 'duration_ms': run['duration_ms'],
                'output_sha256': run['output_sha256'], 'retained_failure_input': artifact,
                'runtime_user': runtime_user(index, phase, seed_index)})
        results.append({'name': target['name'], 'binary_source': target['binary'],
            'binary_sha256': snapshot[prefix]['sha256'] if snapshot else None,
            'corpus_sha256': _digest({p: source_hashes[p] for p in target['corpus']}),
            'corpus_files': target['corpus'], 'instrumentation_observed': inspected,
            'phases': phases, 'completed': all(p['status'] == 'completed' for p in phases)})
    return {'plan_sha256': _digest(plan), 'required_targets': [r['name'] for r in results],
        'executed_targets': [r['name'] for r in results if any(p['binary_bound'] for p in r['phases'])],
        'completed_targets': [r['name'] for r in results if r['completed']], 'targets': results,
        'complete': value['error'] is None and all(r['completed'] for r in results),
        'error': value['error'], 'source_coverage': None, 'scope': LIMITATION,
        'duration_ms': sum(row['duration_ms'] for row in rows.values()),
        'instrumentation_basis': 'Selected libFuzzer and sanitizer symbols in the immutable executed binary; not independently reconstructed link provenance or whole-source coverage'}


def validate_snapshots(value, plan, source_hashes):
    if not isinstance(value, dict) or set(value) != {f't{i}' for i in range(len(plan['targets']))}:
        raise ValueError('worker_fuzz_snapshot_population_invalid')
    for index, target in enumerate(plan['targets']):
        row = value[f't{index}']
        if (not isinstance(row, dict) or set(row) != {'path', 'sha256', 'bytes', 'uid', 'mode', 'corpus'}
                or row['path'] != f'/work/fuzz-snapshots/t{index}/program'
                or not isinstance(row['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', row['sha256'])
                or type(row['bytes']) is not int or not 64 <= row['bytes'] <= 67108864
                or type(row['uid']) is not int or row['uid'] != 0 or type(row['mode']) is not int or row['mode'] != 0o555
                or not isinstance(row['corpus'], dict) or set(row['corpus']) != set(target['corpus'])):
            raise ValueError('worker_fuzz_snapshot_invalid')
        for path, seed in row['corpus'].items():
            if (not isinstance(seed, dict) or set(seed) != {'sha256', 'bytes'} or seed['sha256'] != source_hashes[path]
                    or type(seed['bytes']) is not int or not 1 <= seed['bytes'] <= plan['max_len']):
                raise ValueError('worker_fuzz_corpus_binding_invalid')
    return value
