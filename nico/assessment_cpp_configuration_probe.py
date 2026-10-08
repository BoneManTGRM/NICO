"""Isolated configure-first preparation for the existing full-project worker.

Captures a plan, not a completed assessment, and cannot activate production.
All execution uses the existing full-project sandbox primitives. An explicit
baseline contract uses a separate measured-at-runtime qualification envelope.
"""
from __future__ import annotations

from nico.assessment_cpp_fileapi_membership import runtime_cmake_path

import base64
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from nico.assessment_cpp_full_project_execution import (
    PROFILE, docker_resource_args, _command, _inputs, ANALYSIS_USER,
    ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM, READ_PROGRAM,
    boundary_valid,
)

SCRATCH_PROGRAM = "import json, os; s=os.statvfs('/work'); print(json.dumps({'capacity_bytes':s.f_blocks*s.f_frsize,'available_bytes':s.f_bavail*s.f_frsize}))"

# ctest's console log can exceed the controller stream budget while the process
# is still producing the JUnit file. Keep that log on the work tmpfs and let
# the test process finish; retain a bounded copy afterwards.
CTEST_EXEC_PROGRAM = r'''
import os, sys
log_path, argv = sys.argv[1], sys.argv[2:]
if (not argv or os.path.basename(argv[0]) != 'ctest' or not log_path.startswith('/work/build/')
        or os.path.basename(log_path) != 'nico-baseline-ctest.log'):
    raise SystemExit(2)
fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
os.dup2(fd, 1)
os.dup2(fd, 2)
if fd > 2: os.close(fd)
os.execvp(argv[0], argv)
'''

UNIT_TEST_DATA_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, sys
limit = int(sys.argv[1])
raw = sys.stdin.buffer.read(limit + 1)
if len(raw) > limit: raise SystemExit('input_limit')
files = json.loads(raw)
if os.getuid() != 0: raise SystemExit('provisioning_identity')
root = pathlib.Path('/work/unit_test_data')
root.mkdir(mode=0o755)
result = {}
for name, value in files.items():
    if '/' in name or name in ('', '.', '..') or len(name) > 80:
        raise SystemExit('input_path')
    data = base64.b64decode(value['base64'], validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if digest != value['sha256']: raise SystemExit('input_digest')
    output = root / name
    with output.open('xb') as handle: handle.write(data)
    output.chmod(0o444)
    result[name] = digest
print(json.dumps(result, sort_keys=True))
'''


def probe_project_configuration(source, targets, image, *, project_options,
                                retain=lambda result: None, command=None, baseline_execution=None,
                                unit_test_data=None, capture_generated_context=False,
                                retain_artifact=None, project_compiler_evidence=False, project_static_analysis=False,
                                extended_compiler_budget=False, compiler_environment=False, runtime_plan=None,
                                external_checkpoint=None, capture_enabled_targets=False,
                                capture_native_commands=False, materialize_generated_inputs=False,
                                collect_completed_compiler_failures=False):
    """Capture a real CMake plan before freezing a large execution population.

    This is preparation evidence, NOT a worker completion receipt. It cannot
    pass validate_receipt or activate a production profile. All assessed CMake
    commands use the existing disposable boundary. The optional frozen
    baseline contract adds build/test stages without claiming full assessment.
    Returned records survive later failure through the caller's atomic sink.
    """
    if external_checkpoint is not None and not callable(external_checkpoint):
        raise ValueError('worker_configuration_probe_checkpoint_invalid')
    owner_checkpoint = external_checkpoint or (lambda: None)
    import re
    from pathlib import PurePosixPath
    from nico.assessment_cpp_full_project import CMAKE_VERSION, MAX_SOURCE_BYTES, _json, _database
    from nico.assessment_cpp_configuration import COMPILER_VERSION
    from nico.assessment_worker_receipts import canonical_bytes
    if (not isinstance(image, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', image) is None
            or not isinstance(targets, dict) or not 1 <= len(targets) <= 20000
            or 'CMakeLists.txt' not in targets
            or any(not isinstance(path, str) or not path or len(path) > 1000
                or PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path
                or any(part in {'', '.', '..', '.git'} for part in path.split('/'))
                or ':' in path or '\\' in path or any(ord(c) < 32 for c in path)
                or not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None
                for path, digest in targets.items())):
        raise ValueError('worker_configuration_probe_identity_invalid')
    if (not isinstance(project_options, dict) or len(project_options) > 64
            or any(not isinstance(key, str) or re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key) is None
                or key.startswith('CMAKE_') or not isinstance(value, str)
                or re.fullmatch(r'[A-Za-z0-9_./+-]{1,120}', value) is None
                for key, value in project_options.items())):
        raise ValueError('worker_configuration_probe_options_invalid')
    if (type(capture_generated_context) is not bool
            or (capture_generated_context and (baseline_execution is None or not callable(retain_artifact)))):
        raise ValueError('worker_configuration_probe_capture_contract_invalid')
    if (type(capture_enabled_targets) is not bool
            or (capture_enabled_targets and not callable(retain_artifact))):
        raise ValueError('worker_configuration_probe_capture_contract_invalid')
    if (type(capture_native_commands) is not bool
            or capture_native_commands and not (capture_enabled_targets and project_compiler_evidence)):
        raise ValueError('worker_configuration_probe_native_plan_invalid')
    if (type(materialize_generated_inputs) is not bool
            or materialize_generated_inputs and not (capture_native_commands and capture_generated_context)):
        raise ValueError('worker_configuration_probe_generation_contract_invalid')
    if type(project_compiler_evidence) is not bool or (project_compiler_evidence and not capture_generated_context):
        raise ValueError('worker_configuration_probe_compiler_contract_invalid')
    if (type(collect_completed_compiler_failures) is not bool
            or collect_completed_compiler_failures and not project_compiler_evidence):
        raise ValueError('worker_configuration_probe_compiler_collection_invalid')
    if type(project_static_analysis) is not bool or (project_static_analysis and not project_compiler_evidence):
        raise ValueError('worker_configuration_probe_static_contract_invalid')
    if type(compiler_environment) is not bool or (compiler_environment and not project_static_analysis):
        raise ValueError('worker_configuration_probe_environment_contract_invalid')
    if type(extended_compiler_budget) is not bool or (extended_compiler_budget and not project_compiler_evidence):
        raise ValueError('worker_configuration_probe_compiler_contract_invalid')
    if (runtime_plan is not None and (baseline_execution is None or not isinstance(runtime_plan,dict)
            or runtime_plan.get('schema') not in ('nico.cpp-runtime-plan.v1','nico.cpp-runtime-plan.v2','nico.cpp-runtime-plan.v3','nico.cpp-runtime-plan.v4') or runtime_plan.get('total_seconds')!=6000)):
        raise ValueError('worker_configuration_probe_runtime_contract_invalid')
    from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, resources_for
    if baseline_execution is not None:
        fixed_fields = {'schema', 'profile', 'compilation_database_sha256', 'build_seconds',
                        'test_seconds', 'test_case_seconds', 'parallel'}
        freeze_fields = {'schema', 'profile', 'freeze_compilation_database', 'build_seconds',
                         'test_seconds', 'test_case_seconds', 'parallel'}
        schema = baseline_execution.get('schema') if isinstance(baseline_execution, dict) else None
        fixed = schema == 'nico.cpp-baseline-execution.v1'
        freeze = schema == 'nico.cpp-baseline-execution.v2'
        if (not isinstance(baseline_execution, dict)
                or set(baseline_execution) != (fixed_fields if fixed else freeze_fields if freeze else set())
                or baseline_execution.get('profile') != BASELINE_QUALIFICATION_PROFILE
                or (fixed and (not isinstance(baseline_execution['compilation_database_sha256'], str)
                    or re.fullmatch(r'[a-f0-9]{64}', baseline_execution['compilation_database_sha256']) is None))
                or (freeze and baseline_execution['freeze_compilation_database'] != 'after_configuration_before_build')
                or any(type(baseline_execution[k]) is not int or not 1 <= baseline_execution[k] <= maximum
                       for k, maximum in (('build_seconds', 1200), ('test_seconds', 900),
                                          ('test_case_seconds', 300), ('parallel', 4)))):
            raise ValueError('worker_configuration_probe_execution_contract_invalid')
    staged_data = None
    if unit_test_data is not None:
        if (baseline_execution is None or not isinstance(unit_test_data, dict)
                or not 1 <= len(unit_test_data) <= 4
                or any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name) is None
                    or not isinstance(blob, (bytes, bytearray)) or not 1 <= len(blob) <= 20_000_000
                    for name, blob in unit_test_data.items())):
            raise ValueError('worker_configuration_probe_unit_test_data_invalid')
        staged_data = {name: bytes(blob) for name, blob in sorted(unit_test_data.items())}
    profile = BASELINE_QUALIFICATION_PROFILE if baseline_execution is not None else PROFILE
    resources = resources_for(profile)
    execution_seconds = (1800 + (runtime_plan['total_seconds'] if runtime_plan is not None else 0) if baseline_execution is not None else 80)
    command = command or _command
    start = time.monotonic()
    deadline = start + execution_seconds
    name = 'nico-project-configure-' + uuid4().hex
    created = False
    result = {'schema': 'nico.cpp-project-configuration-probe.v3', 'status': 'UNPROVEN',
        'preparation_mode': 'baseline_execution' if baseline_execution is not None else 'configuration_only',
        'compilation_contexts': None,
        'image_config_digest': image, 'source_population_sha256': hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        'project_options': dict(project_options), 'operations': [], 'boundary': None,
        'boundary_verified': False, 'memory_peak_bytes': None, 'cleanup_verified': False,
        'compilation_database': None, 'compilation_database_sha256': None,
        'configuration_cache': None, 'configuration_cache_sha256': None, 'effective_project_options': {},
        'configured_translation_units': [], 'configured_generated_units': [], 'configured_invocations': 0,
        'compiled': False, 'tests_executed': False, 'full_project_qualified': False,
        'error': None, 'wall_budget_seconds': 90, 'execution_budget_seconds': 80, 'duration_ms': 0}

    if capture_generated_context:
        result.update(schema='nico.cpp-project-configuration-probe.v4',
            generated_context=None, generated_context_verified=False)

    if project_compiler_evidence:
        result.update(schema='nico.cpp-project-configuration-probe.v5', project_compiler=None)
    if project_static_analysis:
        result.update(schema='nico.cpp-project-configuration-probe.v6', project_static=None,
            project_static_stage=None, aggregate_execution_budget_seconds=execution_seconds+1020,
            aggregate_wall_budget_seconds=execution_seconds+1040, aggregate_duration_ms=0)

    if baseline_execution is not None:
        result.update(baseline_execution=dict(baseline_execution), baseline_execution_frozen=None,
            tests_discovered=[], tests_passed=False, scratch_capacity_verified=False, scratch_capacity_bytes=None,
            tests_result=None, native_test_discovery=None, unit_test_data=None, runtime_evidence=None, runtime_summary=None,
            wall_budget_seconds=execution_seconds+10, execution_budget_seconds=execution_seconds)

    if extended_compiler_budget:
        result.update(schema='nico.cpp-project-configuration-probe.v7',
                      project_compiler_budget_version='v2')
    if capture_enabled_targets:
        result.update(schema='nico.cpp-project-configuration-probe.v8',
            fileapi_client='client-nico-membership-' + uuid4().hex,
            enabled_target_capture=None, enabled_target_membership=None)
    if capture_native_commands:
        result.update(schema='nico.cpp-project-configuration-probe.v9',
            native_command_capture=None, native_command_plan=None,
            analysis_compilation_database=None, analysis_compilation_database_sha256=None,
            analysis_invocations=0)
    if materialize_generated_inputs:
        result.update(schema='nico.cpp-project-configuration-probe.v10', generated_input_materialization=None)
    if collect_completed_compiler_failures:
        result.update(schema='nico.cpp-project-configuration-probe.v11',
            project_compiler_collection=None, independent_collection_error=None)

    def save():
        result['duration_ms'] = int((time.monotonic() - start) * 1000)
        if project_static_analysis:
            # Include failures before the separate static stage starts.
            result['aggregate_duration_ms'] = result['duration_ms']
        retain(result)

    def checkpoint():
        owner_checkpoint()
        if time.monotonic() >= deadline:
            raise ValueError('worker_configuration_probe_deadline')

    def observe(key, argv, *, data=None, limit=65536, seconds=15, external=False):
        checkpoint()
        before = time.monotonic()
        observed = command(argv, checkpoint=checkpoint, timeout=min(seconds, deadline-before),
                           input_bytes=data, limit=limit, native_exit=True)
        raw = observed['output']
        entry = {'id': key, 'invocation': argv,
            'exit_code': observed['exit_code'], 'timed_out': observed['timed_out'],
            'output_truncated': observed['output_truncated'], 'duration_ms': int((time.monotonic()-before)*1000),
            'output': None if external else base64.b64encode(raw).decode('ascii'),
            'output_sha256': hashlib.sha256(raw).hexdigest()}
        if external:
            entry['output_artifact'] = None
        if key in {'project-native-commands','project-native-commands-post-build',
                   'project-enabled-targets-post-build', 'generation-inputs-before', 'generation-inputs-after'}:
            entry['input_sha256'] = hashlib.sha256(data).hexdigest()
        result['operations'].append(entry)
        save()  # Preserve the returned native outcome, even if artifact storage fails.
        if external:
            try:
                reference = retain_artifact(key, raw)
            except Exception as exc:
                raise ValueError('worker_configuration_probe_artifact_retention_failed') from exc
            expected = {'path': 'artifacts/' + key + '-' + entry['output_sha256'] + '.json',
                        'sha256': entry['output_sha256'], 'bytes': len(raw)}
            if reference != expected or type(reference.get('bytes')) is not int:
                raise ValueError('worker_configuration_probe_artifact_reference_invalid')
            entry['output_artifact'] = reference
            save()  # Artifact bytes and identity are retained before parsing or promotion.
        checkpoint()  # Returned-byte retention is part of the parent phase.
        return observed

    def invoke(key, argv, *, data=None, limit=65536, seconds=15, allow_failure=False):
        observed = observe(key, argv, data=data, limit=limit, seconds=seconds)
        if ((observed['exit_code'] != 0 and not allow_failure) or observed['timed_out']
                or observed['output_truncated']):
            raise ValueError('worker_configuration_probe_operation_failed')
        return observed['output']

    save()
    try:
        files = _inputs({'targets': targets, 'configuration': {'source_byte_limit': MAX_SOURCE_BYTES}},
                        Path(source), checkpoint)
        metadata = _json(invoke('image', ['docker', 'image', 'inspect', image]))
        if not isinstance(metadata, list) or len(metadata) != 1 or metadata[0].get('Id') != image:
            raise ValueError('worker_configuration_probe_image_mismatch')
        created = True  # Docker can succeed before its response is interrupted.
        invoke('create', ['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(profile, executable=True), '--log-driver=none',
            '--env=HOME=/work', '--env=TMPDIR=/work', '--entrypoint=sleep', image, str(execution_seconds + 15)])
        invoke('start', ['docker', 'start', name])
        setup = _json(invoke('analyst-setup', ['docker', 'exec', '--user='+ANALYSIS_USER,
            name, 'python3', '-I', '-S', '-c', ANALYSIS_SETUP_PROGRAM]))
        if setup != {'uid':1001, 'gid':1001, 'private':True}:
            raise ValueError('worker_configuration_probe_boundary_invalid')
        prefix = ['docker', 'exec', name]
        before = _json(invoke('boundary-before', [*prefix, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        if not boundary_valid(before, source_required=False, profile=profile):
            raise ValueError('worker_configuration_probe_boundary_invalid')
        if baseline_execution is not None:
            scratch = _json(invoke('scratch-capacity', [*prefix, 'python3', '-I', '-S', '-c', SCRATCH_PROGRAM]))
            if (not isinstance(scratch, dict) or set(scratch) != {'capacity_bytes', 'available_bytes'}
                    or type(scratch['capacity_bytes']) is not int
                    or scratch['capacity_bytes'] != resources['tmpfs_bytes']
                    or type(scratch['available_bytes']) is not int
                    or not 0 <= scratch['available_bytes'] <= scratch['capacity_bytes']):
                raise ValueError('worker_configuration_probe_scratch_capacity_invalid')
            result.update(scratch_capacity_verified=True, scratch_capacity_bytes=scratch['capacity_bytes'])
            save()
        payload = canonical_bytes(files)
        transferred = _json(invoke('source-transfer', ['docker', 'exec', '--user=0:0', '--interactive',
            name, 'python3', '-I', '-S', '-c', INPUT_PROGRAM, str(len(payload))], data=payload,
            limit=4*1024*1024, seconds=20))
        if transferred != targets:
            raise ValueError('worker_configuration_probe_source_mismatch')
        # Avoid retaining a second full copy of the already committed source input.
        del files, payload
        result['boundary'] = _json(invoke('boundary-after', [*prefix, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        result['boundary_verified'] = boundary_valid(result['boundary'], profile=profile)
        if not result['boundary_verified']:
            raise ValueError('worker_configuration_probe_boundary_invalid')
        cmake = invoke('cmake-version', [*prefix, 'cmake', '--version'])
        if cmake.splitlines()[0] != ('cmake version '+CMAKE_VERSION).encode():
            raise ValueError('worker_configuration_probe_tool_mismatch')
        for compiler in ('gcc', 'g++'):
            if invoke(compiler+'-version', [*prefix, compiler, '-dumpfullversion']).strip() != COMPILER_VERSION.encode():
                raise ValueError('worker_configuration_probe_tool_mismatch')
        options = ['-D'+key+'='+value for key, value in sorted(project_options.items())]
        if capture_enabled_targets:
            from nico.assessment_cpp_fileapi_membership import QUERY_PROGRAM, EMPTY_SHA, QUERY_NAMES
            query = _json(invoke('fileapi-query', [*prefix, 'python3', '-I', '-S', '-c', QUERY_PROGRAM,
                '/work/build', result['fileapi_client']]))
            if query != {'client': result['fileapi_client'], 'query': {q: EMPTY_SHA for q in QUERY_NAMES}}:
                raise ValueError('worker_configuration_probe_fileapi_invalid')
        invoke('configure', [*prefix, 'cmake', '-S', '/work/source', '-B', '/work/build',
            '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_COMPILER=/usr/local/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
            *options], seconds=50, limit=262144)
        cache = _json(invoke('configuration-cache', [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/CMakeCache.txt', str(1024*1024)], limit=2*1024*1024))
        if not isinstance(cache, dict) or set(cache) != {'data', 'truncated'} or cache['truncated'] is not False:
            raise ValueError('worker_configuration_probe_cache_truncated')
        cache_bytes = base64.b64decode(cache['data'], validate=True)
        if not 0 < len(cache_bytes) <= 1024*1024:
            raise ValueError('worker_configuration_probe_cache_invalid')
        result.update(configuration_cache=cache['data'],
                      configuration_cache_sha256=hashlib.sha256(cache_bytes).hexdigest())
        observed_options = {}
        for line in cache_bytes.decode('utf-8').splitlines():
            # A -D argument alone becomes UNINITIALIZED even when the project
            # never consumes it. Require an observed, typed project cache entry.
            if not line or line.startswith(('#', '//')):
                continue
            match = re.fullmatch(r'([^:]+):([A-Z_]+)=(.*)', line)
            if match and match[1] in project_options:
                key, kind, value = match.groups()
                if (key in observed_options or kind not in {'BOOL', 'STRING', 'PATH', 'FILEPATH'}
                        or value != project_options[key]):
                    raise ValueError('worker_configuration_probe_option_unverified')
                observed_options[key] = value
        if observed_options != project_options:
            raise ValueError('worker_configuration_probe_option_unverified')
        result['effective_project_options'] = observed_options
        save()
        artifact = _json(invoke('compilation-database', [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/compile_commands.json', str(4*1024*1024)], limit=6*1024*1024))
        if not isinstance(artifact, dict) or set(artifact) != {'data', 'truncated'} or artifact['truncated'] is not False:
            raise ValueError('worker_configuration_probe_database_truncated')
        raw = base64.b64decode(artifact['data'], validate=True)
        if not 0 < len(raw) <= 4*1024*1024:
            raise ValueError('worker_configuration_probe_database_invalid')
        try:
            contexts = _database(raw, None, '/work/build', nested=True, source_targets=targets)
        except ValueError as exc:
            raise ValueError('worker_configuration_probe_contexts_invalid') from exc
        result.update(compilation_database=artifact['data'], compilation_database_sha256=contexts['database_sha256'],
            configured_translation_units=contexts['original_units'], configured_generated_units=contexts['generated_units'],
            configured_invocations=contexts['context_count'], compilation_contexts=contexts)
        if capture_enabled_targets:
            from nico.assessment_cpp_fileapi_membership import (
                CAPTURE_PROGRAM, STREAM_LIMIT as FILEAPI_STREAM_LIMIT, configured_target_membership)
            capture = observe('project-enabled-targets', ['docker', 'exec', '--interactive', name,
                'python3', '-I', '-S', '-c', CAPTURE_PROGRAM],
                data=canonical_bytes({'source_root': '/work/source', 'build_root': '/work/build',
                    'client': result['fileapi_client'], 'source_targets': targets,
                    'database_sha256': result['compilation_database_sha256'],
                    'cache_sha256': result['configuration_cache_sha256']}),
                limit=FILEAPI_STREAM_LIMIT, external=True)
            result['enabled_target_capture'] = result['operations'][-1]['output_artifact']
            save()
            if capture['exit_code'] != 0 or capture['timed_out'] or capture['output_truncated']:
                raise ValueError('worker_configuration_probe_fileapi_failed')
            membership = configured_target_membership(capture['output'], raw, targets,
                source_root='/work/source', build_root='/work/build', client=result['fileapi_client'],
                cache_sha256=result['configuration_cache_sha256'],
                compiler_versions={'C': COMPILER_VERSION, 'CXX': COMPILER_VERSION},
                compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(capture_native_commands))
            result['enabled_target_membership'] = {**membership,
                'artifact': result['enabled_target_capture']}
            save()
            if capture_native_commands:
                from nico.assessment_cpp_native_commands import (
                    CAPTURE_PROGRAM as NATIVE_CAPTURE_PROGRAM,
                    configured_native_commands, native_capture_request, validate_native_plan_freeze)
                native_request = canonical_bytes(native_capture_request(capture['output'], membership))
                native_capture = observe('project-native-commands',
                    ['docker', 'exec', '--interactive', name, 'python3', '-I', '-S', '-c', NATIVE_CAPTURE_PROGRAM],
                    data=native_request, limit=FILEAPI_STREAM_LIMIT, external=True)
                result['native_command_capture'] = result['operations'][-1]['output_artifact']
                save()
                if native_capture['exit_code'] != 0 or native_capture['timed_out'] or native_capture['output_truncated']:
                    raise ValueError('worker_configuration_probe_native_plan_failed')
                try:
                    plan = configured_native_commands(native_capture['output'], capture['output'], raw, targets,
                        source_root='/work/source', build_root='/work/build', client=result['fileapi_client'],
                        cache_sha256=result['configuration_cache_sha256'],
                        compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                        compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(capture_native_commands))
                except ValueError as exc:
                    raise ValueError('worker_configuration_probe_native_plan_invalid') from exc
                analysis_raw = base64.b64decode(plan['analysis_database'], validate=True)
                # The original DB/freeze identity remains immutable. Complete
                # native contexts have a distinct analysis database identity.
                contexts = _database(analysis_raw, None, '/work/build', nested=True, source_targets=targets)
                result.update(native_command_plan={**plan,'artifact':result['native_command_capture']},
                    analysis_compilation_database=plan['analysis_database'],
                    analysis_compilation_database_sha256=plan['analysis_database_sha256'],
                    analysis_invocations=contexts['context_count'])
                save()
        result['status'] = 'CONFIGURATION_CAPTURED'
        if baseline_execution is not None:
            if baseline_execution['schema'] == 'nico.cpp-baseline-execution.v1':
                if result['compilation_database_sha256'] != baseline_execution['compilation_database_sha256']:
                    raise ValueError('worker_configuration_probe_frozen_database_mismatch')
            else:
                result['baseline_execution_frozen'] = {
                    'schema': 'nico.cpp-baseline-execution-freeze.v1',
                    'source_population_sha256': result['source_population_sha256'],
                    'project_options': dict(result['effective_project_options']),
                    'compilation_database_sha256': result['compilation_database_sha256'],
                    'configured_invocations': result['configured_invocations'],
                    'freeze_point': 'after_configuration_before_build',
                }
                save()
            if staged_data is not None:
                payload = canonical_bytes({name: {
                    'base64': base64.b64encode(blob).decode('ascii'),
                    'sha256': hashlib.sha256(blob).hexdigest()} for name, blob in staged_data.items()})
                transferred = _json(invoke('unit-test-data', ['docker', 'exec', '--user=0:0', '--interactive',
                    name, 'python3', '-I', '-S', '-c', UNIT_TEST_DATA_PROGRAM, str(len(payload))],
                    data=payload, limit=65536, seconds=30))
                expected = {item: hashlib.sha256(blob).hexdigest() for item, blob in staged_data.items()}
                if transferred != expected:
                    raise ValueError('worker_configuration_probe_unit_test_data_invalid')
                result['unit_test_data'] = expected
                save()
                del payload
            build_started = time.monotonic()
            invoke('baseline-build', [*prefix, 'cmake', '--build', '/work/build', '--parallel',
                str(baseline_execution['parallel'])], seconds=baseline_execution['build_seconds'],
                limit=1024*1024)
            result['compiled'] = True
            save()
            if materialize_generated_inputs:
                from nico.assessment_cpp_generated_inputs import (
                    OBSERVE_PROGRAM, generated_input_plan, validate_observation,
                )
                from nico.assessment_cpp_project_snapshot import project_snapshot_request
                generation_request = project_snapshot_request(contexts)
                generation_bytes = canonical_bytes(generation_request)
                generation_argv = ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive',
                    name, 'python3', '-I', '-S', '-c', OBSERVE_PROGRAM]
                def remaining_build_seconds():
                    remaining = baseline_execution['build_seconds'] - (time.monotonic()-build_started)
                    if remaining <= 0:
                        raise ValueError('worker_configuration_probe_generation_budget_exhausted')
                    return remaining
                before_inputs = _json(invoke('generation-inputs-before', generation_argv,
                    data=generation_bytes, limit=4*1024*1024, seconds=min(15,remaining_build_seconds())))
                try:
                    generation_plan = generated_input_plan(native_capture['output'], capture['output'],
                        membership, plan, generation_request, before_inputs)
                except ValueError as exc:
                    raise ValueError('worker_configuration_probe_generation_plan_invalid') from exc
                for index, target in enumerate(generation_plan['selected_targets']):
                    # All and utility targets consume ONE original build budget.
                    # Metadata work also consumes this elapsed envelope.
                    invoke('generation-target-'+str(index).zfill(3), [*prefix, 'cmake', '--build',
                        '/work/build', '--target', target['target_name'], '--parallel',
                        str(baseline_execution['parallel'])], seconds=remaining_build_seconds(), limit=1024*1024)
                after_inputs = _json(invoke('generation-inputs-after', generation_argv,
                    data=generation_bytes, limit=4*1024*1024, seconds=min(15,remaining_build_seconds())))
                validate_observation(after_inputs, generation_request)
                remaining_build_seconds()
                materialization = {'schema':'nico.cpp-generated-input-evidence.v1',
                    'image_config_digest':image, 'request':generation_request, 'plan':generation_plan,
                    'before':before_inputs, 'after':after_inputs,
                    'build_elapsed_ms':int((time.monotonic()-build_started)*1000),
                    'complete':all(row['state']=='readable' for row in after_inputs['files'].values())}
                generation_raw = canonical_bytes(materialization)
                digest = hashlib.sha256(generation_raw).hexdigest()
                reference = retain_artifact('project-generation-evidence', generation_raw)
                if reference != {'path':'artifacts/project-generation-evidence-'+digest+'.json',
                                 'sha256':digest, 'bytes':len(generation_raw)}:
                    raise ValueError('worker_configuration_probe_artifact_reference_invalid')
                result['generated_input_materialization'] = {**materialization, 'artifact':reference}
                save()
                if not materialization['complete']:
                    raise ValueError('worker_configuration_probe_generation_incomplete')
            # CMake may regenerate as part of the build. It must not change the
            # frozen command population, including generated and repeated units.
            after = _json(invoke('post-build-database', [*prefix, 'python3', '-I', '-S', '-c',
                READ_PROGRAM, '/work/build/compile_commands.json', str(4*1024*1024)], limit=6*1024*1024))
            if (not isinstance(after, dict) or set(after) != {'data','truncated'} or after['truncated']
                    or hashlib.sha256(base64.b64decode(after['data'], validate=True)).hexdigest()
                       != result['compilation_database_sha256']):
                raise ValueError('worker_configuration_probe_frozen_database_mismatch')
            if capture_native_commands:
                current_fileapi = observe('project-enabled-targets-post-build',
                    ['docker','exec','--interactive',name,'python3','-I','-S','-c',CAPTURE_PROGRAM],
                    data=canonical_bytes({'source_root':'/work/source','build_root':'/work/build',
                        'client':result['fileapi_client'],'source_targets':targets,
                        'database_sha256':result['compilation_database_sha256'],
                        'cache_sha256':result['configuration_cache_sha256']}), limit=FILEAPI_STREAM_LIMIT, external=True)
                current_native = observe('project-native-commands-post-build',
                    ['docker','exec','--interactive',name,'python3','-I','-S','-c',NATIVE_CAPTURE_PROGRAM],
                    data=native_request, limit=FILEAPI_STREAM_LIMIT, external=True)
                if (any(row['exit_code'] != 0 or row['timed_out'] or row['output_truncated']
                        for row in (current_fileapi,current_native))
                    or hashlib.sha256(current_fileapi['output']).hexdigest() != membership['capture_sha256']):
                    raise ValueError('worker_configuration_probe_frozen_native_plan_mismatch')
                try:
                    result['native_command_freeze'] = validate_native_plan_freeze(
                        native_capture['output'],current_native['output'],capture['output'],raw,targets,
                        source_root='/work/source',build_root='/work/build',client=result['fileapi_client'],
                        cache_sha256=result['configuration_cache_sha256'],
                        compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                        compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(capture_native_commands))
                except ValueError as exc:
                    raise ValueError('worker_configuration_probe_frozen_native_plan_mismatch') from exc
                save()
            # Generated CTest includes (secp256k1 discover_tests) only expand
            # after the test binaries exist. Freeze that runnable population
            # before testing. A leftover DISCOVERY_FAILURE is not a test.
            discovered = invoke('baseline-test-discovery', [*prefix, 'ctest', '--test-dir',
                '/work/build', '--show-only=json-v1'], limit=4*1024*1024, seconds=60)
            names = _json(discovered)
            rows = names.get('tests') if isinstance(names, dict) else None
            if (not isinstance(rows, list) or not 1 <= len(rows) <= 10000
                    or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
                        or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:/+-]{0,249}', row['name']) is None
                        for row in rows)):
                raise ValueError('worker_configuration_probe_tests_invalid')
            names = sorted(row['name'] for row in rows)
            if len(set(names)) != len(names):
                raise ValueError('worker_configuration_probe_tests_duplicate')
            if any('DISCOVERY_FAILURE' in item for item in names):
                raise ValueError('worker_configuration_probe_tests_incomplete')
            result.update(status='UNPROVEN', tests_discovered=names,
                          native_test_discovery=base64.b64encode(discovered).decode('ascii'))
            save()
            # The command is fixed: execute every post-build CTest entry. No
            # regex exclusion, chosen passing subset or arbitrary command.
            # Stdout stays in the container so a verbose failure cannot kill
            # ctest before it writes JUnit.
            test_argv = ['docker', 'exec']
            if result['unit_test_data'] is not None:
                test_argv += ['-e', 'DIR_UNIT_TEST_DATA=/work/unit_test_data']
            test_argv += [name, 'python3', '-I', '-S', '-c', CTEST_EXEC_PROGRAM,
                '/work/build/nico-baseline-ctest.log', 'ctest', '--test-dir', '/work/build',
                '--parallel', str(baseline_execution['parallel']), '--timeout',
                str(baseline_execution['test_case_seconds']), '--output-on-failure',
                '--output-junit', '/work/build/nico-baseline-junit.xml']
            observed = observe('baseline-tests', test_argv, seconds=baseline_execution['test_seconds'],
                               limit=65536)
            result['tests_executed'] = True
            native_success = observed['exit_code'] == 0 and not observed['timed_out'] and not observed['output_truncated']
            save()

            def bounded_artifact(key, path, file_limit, stream_limit):
                artifact_observed = observe(key, [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
                    path, str(file_limit)], limit=stream_limit)
                if (artifact_observed['exit_code'] != 0 or artifact_observed['timed_out']
                        or artifact_observed['output_truncated']):
                    return None
                parsed = _json(artifact_observed['output'])
                if not isinstance(parsed, dict) or set(parsed) != {'data', 'truncated'}:
                    return None
                return parsed

            log = bounded_artifact('baseline-test-log', '/work/build/nico-baseline-ctest.log',
                                   1024*1024, 2*1024*1024)
            junit = bounded_artifact('baseline-junit', '/work/build/nico-baseline-junit.xml',
                                     2*1024*1024, 4*1024*1024)
            log_ok = bool(log and log['truncated'] is False)
            from nico.assessment_cpp_full_project import _junit
            executed, passed, skipped, junit_data = [], [], [], None
            if junit and junit['truncated'] is False:
                junit_data = junit['data']
                try:
                    executed, passed, skipped = _junit(base64.b64decode(junit_data, validate=True), names)
                except ValueError:
                    executed, passed, skipped = [], [], []
            result['tests_result'] = {'executed': executed, 'passed': passed, 'skipped': skipped,
                                      'junit': junit_data, 'log_truncated': not log_ok,
                                      'junit_truncated': junit_data is None}
            result['tests_passed'] = (native_success and log_ok and junit_data is not None
                                      and passed == names and not skipped)
            # CTest's failed-test exit and a complete matching JUnit population
            # are target evidence. Missing/truncated or contradictory evidence
            # still stops the probe; a valid target failure must not prevent
            # generated-source, compiler, static, or runtime collection.
            from nico.assessment_cpp_runtime_execution import _completed_sanitizer_test_failure
            target_failure = bool(log_ok and junit_data is not None
                and _completed_sanitizer_test_failure(observed,
                    {'required':names,'executed':executed,'passed':passed,'skipped':skipped},
                    base64.b64decode(junit_data, validate=True)))
            if not result['tests_passed'] and not target_failure:
                raise ValueError('worker_configuration_probe_native_tests_failed')
            if capture_generated_context:
                from nico.assessment_cpp_project_snapshot import (PROJECT_SNAPSHOT_PROGRAM,
                    PROJECT_GENERATED_STREAM_LIMIT, project_snapshot_request, validate_project_snapshot)
                snapshot_observed = observe('project-generated-context',
                    ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name,
                     'python3', '-I', '-S', '-c', PROJECT_SNAPSHOT_PROGRAM],
                    data=canonical_bytes(project_snapshot_request(contexts)),
                    limit=PROJECT_GENERATED_STREAM_LIMIT, seconds=30, external=True)
                if (snapshot_observed['exit_code'] != 0 or snapshot_observed['timed_out']
                        or snapshot_observed['output_truncated']):
                    from nico.assessment_cpp_project_snapshot import is_project_snapshot_capacity_failure
                    if not snapshot_observed['timed_out'] and not snapshot_observed['output_truncated']:
                        try:
                            capacity = is_project_snapshot_capacity_failure(_json(snapshot_observed['output']))
                        except (ValueError, TypeError):
                            capacity = False
                        if capacity:
                            raise ValueError('worker_configuration_probe_snapshot_capacity_exceeded')
                    raise ValueError('worker_configuration_probe_snapshot_failed')
                try:
                    snapshot = validate_project_snapshot(_json(snapshot_observed['output']), contexts)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_snapshot_invalid') from exc
                result['generated_context'] = {
                    **{k: v for k, v in snapshot.items() if k != 'files'},
                    'files': {p: {'sha256': v['sha256'], 'bytes': v['bytes']}
                              for p, v in snapshot['files'].items()},
                    'artifact': result['operations'][-1]['output_artifact']}
                result['generated_context_verified'] = True
                save()
            if project_compiler_evidence:
                from nico.assessment_cpp_project_compiler import (PROGRAM, STREAM_LIMIT,
                    project_compiler_request, validate_project_compiler)
                try:
                    request = project_compiler_request(analysis_raw if capture_native_commands else raw,
                        targets, snapshot, extended_budget=extended_compiler_budget)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_compiler_plan_invalid') from exc
                compiler_observed = observe('project-compiler-evidence',
                    ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name,
                     'python3', '-I', '-S', '-c', PROGRAM],
                    data=canonical_bytes(request), limit=STREAM_LIMIT,
                    seconds=request['limits']['wall_seconds'] + 10, external=True)
                if (compiler_observed['exit_code'] != 0 or compiler_observed['timed_out']
                        or compiler_observed['output_truncated']):
                    raise ValueError('worker_configuration_probe_compiler_failed')
                try:
                    proof = validate_project_compiler(compiler_observed['output'], request)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_compiler_evidence_invalid') from exc
                result['project_compiler'] = {**proof, 'artifact': result['operations'][-1]['output_artifact']}
                save()
                checkpoint()  # Validation and proof retention belong to this phase.
                if collect_completed_compiler_failures:
                    from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
                    try:
                        result['project_compiler_collection'] = validate_project_compiler_collection(
                            compiler_observed['output'], request, snapshot)
                    except (ValueError, TypeError, KeyError) as exc:
                        raise ValueError('worker_configuration_probe_compiler_collection_invalid') from exc
                    save()
                if not proof['complete']:
                    if not (result.get('project_compiler_collection') or {}).get('collection_complete'):
                        raise ValueError('worker_configuration_probe_compiler_incomplete')
                    # Preserve failed compilation and its original first error.
                    # Only a separately reconstructed, fully captured target
                    # directive failure permits independently ready collection.
                    result['error'] = 'worker_configuration_probe_compiler_incomplete'
            if runtime_plan is not None:
                from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence
                runtime=execute_runtime_plan(observe,name,runtime_plan,project_options)
                result['runtime_evidence']=runtime
                result['runtime_summary']=validate_runtime_evidence(runtime,runtime_plan,project_options=project_options)
                save()
            result['status'] = 'BASELINE_EXECUTED'

    except (Exception, KeyboardInterrupt) as exc:
        # No arbitrary exception/tool text enters an unsanitized controller error.
        allowed = str(exc) if isinstance(exc, ValueError) else ''
        captured_error = (allowed if re.fullmatch(r'worker_configuration_probe_[a-z_]+', allowed)
                           else 'worker_configuration_probe_interrupted' if isinstance(exc, KeyboardInterrupt)
                           else 'worker_configuration_probe_failed')
        if collect_completed_compiler_failures and result.get('error'):
            result['independent_collection_error'] = captured_error
        else:
            result['error'] = captured_error
    finally:
        if created:
            try:
                raw = command(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'],
                    checkpoint=lambda: None, timeout=2, limit=1024, native_exit=True)
                if raw['exit_code'] == 0 and not raw['timed_out'] and not raw['output_truncated']:
                    peak = int(raw['output'].strip())
                    if 0 <= peak <= resources['memory_bytes']: result['memory_peak_bytes'] = peak
            except (Exception, KeyboardInterrupt):
                pass  # Unavailable measurement remains unknown, not zero.
            try:
                removed = command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                                  timeout=5, limit=4096, native_exit=True)
                result['cleanup_verified'] = (removed['exit_code'] == 0 and not removed['timed_out']
                                             and not removed['output_truncated'])
            except (Exception, KeyboardInterrupt):
                pass
        if not result['cleanup_verified'] or result['error']:
            result['status'] = 'UNPROVEN'
        save()
    completed_target_failure = bool(collect_completed_compiler_failures
        and (result.get('project_compiler_collection') or {}).get('collection_complete') is True
        and (result.get('project_compiler') or {}).get('complete') is False
        and all(result.get(key) is True for key in
            ('compiled', 'generated_context_verified', 'boundary_verified', 'cleanup_verified')))
    if project_static_analysis and (result['status'] == 'BASELINE_EXECUTED' or completed_target_failure):
        # The build sandbox is already destroyed. Its original deadline and
        # duration remain unchanged; static analysis owns a separately bounded
        # noexec sandbox and a distinct receipt. No build code is replayed.
        from nico.assessment_cpp_project_static import run_project_static_stage
        def retain_static(value):
            result.update(project_static_stage=value, project_static=value.get('analysis'),
                          aggregate_duration_ms=int((time.monotonic()-start)*1000))
            if not value.get('complete'):
                result['status'] = 'UNPROVEN'
            retain(result)
        try:
            static = run_project_static_stage(source, targets, image,
                base64.b64decode(result['analysis_compilation_database'] if capture_native_commands
                    else result['compilation_database'], validate=True),
                snapshot, compiler_observed['output'], retain=retain_static,
                extended_compiler_budget=extended_compiler_budget, compiler_environment=compiler_environment,
                header_provenance=capture_native_commands,
                collect_completed_compiler_failures=collect_completed_compiler_failures,
                retain_artifact=retain_artifact, command=command, checkpoint=owner_checkpoint)
            result['status'] = ('BASELINE_EXECUTED' if static['complete'] and not completed_target_failure
                                else 'UNPROVEN')
            if not static['complete']:
                if not completed_target_failure:
                    result['error'] = 'worker_configuration_probe_static_incomplete'
                elif not static.get('collection_complete'):
                    result['independent_collection_error'] = 'worker_configuration_probe_static_incomplete'
        except (Exception, KeyboardInterrupt):
            result['status'] = 'UNPROVEN'
            if completed_target_failure:
                result['independent_collection_error'] = 'worker_configuration_probe_static_failed'
            else:
                result['error'] = 'worker_configuration_probe_static_failed'
        result['aggregate_duration_ms'] = int((time.monotonic()-start)*1000)
        retain(result)
    if runtime_plan is not None and not (result.get('runtime_summary') or {}).get('complete'):
        result['status']='UNPROVEN'
        result['error']=result.get('error') or 'worker_configuration_probe_runtime_incomplete'
        result['aggregate_duration_ms']=int((time.monotonic()-start)*1000)
        retain(result)
    return result
