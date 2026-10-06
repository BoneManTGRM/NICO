"""Bind collection claims to the complete retained controller transport."""
import ast
from nico.assessment_cpp_fileapi_membership import runtime_cmake_path
import base64
import hashlib

from nico.assessment_cpp_full_project import _json, CMAKE_VERSION, MAX_SOURCE_BYTES
from nico.assessment_cpp_configuration import COMPILER_VERSION
from nico.assessment_cpp_full_project_execution import (
    ANALYSIS_USER, ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM,
    READ_PROGRAM, boundary_valid,
)
from nico.assessment_cpp_configuration_probe import SCRATCH_PROGRAM, UNIT_TEST_DATA_PROGRAM
from nico.assessment_cpp_project_snapshot import PROJECT_SNAPSHOT_PROGRAM, PROJECT_RESTORE_PROGRAM
from nico.assessment_cpp_project_compiler import PROGRAM as COMPILER_PROGRAM
from nico.assessment_cpp_static_environment import ENV_PROGRAM
from nico.assessment_cpp_project_static import PROGRAM as STATIC_PROGRAM, STAGE_WALL_SECONDS
from nico.assessment_cpp_clang_fallback import PROGRAM as FALLBACK_PROGRAM, _DROP_EXACT, LOW_CONTENTION_LIMITS
from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, docker_resource_args, resources_for


def _fallback_program_equal(actual, expected):
    """Historical frozenset repr order varies by Python hash seed; code may not."""
    if not isinstance(actual, str) or len(actual) != len(expected):
        return False
    left, right = actual.splitlines(keepends=True), expected.splitlines(keepends=True)
    if len(left) != len(right):
        return False
    prefix = '_DROP_EXACT=frozenset('
    for observed, required in zip(left, right):
        if observed == required:
            continue
        if not (required.startswith(prefix) and observed.startswith(prefix)
                and observed.endswith(')\n') and len(observed) <= 1024):
            return False
        try:
            values = ast.literal_eval(observed[len(prefix):-2])
        except (ValueError, SyntaxError):
            return False
        if type(values) is not set or values != _DROP_EXACT:
            return False
    return True


def validate_transport(probe, operations, targets, *, snapshot=None, runtime_plan=None, baseline_only=False):
    """Exact membership/argv and returned source/config/artifact relationships.

    Runtime and baseline test operations have their own result validators.
    Transport rows alone cannot assert any compiler/static analysis outcome.
    """
    def require(condition):
        if not condition:
            raise ValueError('qualification_collection_transport_invalid')

    static = snapshot is not None
    image = probe['image_config_digest']
    tag = 'static-' if static else ''
    create = operations[tag + 'create'][0]['invocation']
    name = create[create.index('--name') + 1]
    require(isinstance(name, str) and name.startswith('nico-project-static-' if static else 'nico-project-configure-'))
    profile = BASELINE_QUALIFICATION_PROFILE
    prefix = ['docker', 'exec', name]
    program = lambda value: [*prefix, 'python3', '-I', '-S', '-c', value]
    private = lambda value, interactive=False: ['docker', 'exec', '--user='+ANALYSIS_USER,
        *(['--interactive'] if interactive else []), name, 'python3', '-I', '-S', '-c', value]
    specs = {
        tag + 'image': ['docker', 'image', 'inspect', image],
        tag + 'create': ['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(profile, executable=not static), '--log-driver=none',
            '--env=HOME=/work', '--env=TMPDIR=/work', '--entrypoint=sleep', image,
            str(STAGE_WALL_SECONDS + 5 if static else 1800 + (runtime_plan or {}).get('total_seconds', 0) + 15)],
        tag + 'start': ['docker', 'start', name],
        'static-private' if static else 'analyst-setup': private(ANALYSIS_SETUP_PROGRAM),
        tag + 'boundary-before': program(BOUNDARY_PROGRAM),
        'static-boundary' if static else 'boundary-after': program(BOUNDARY_PROGRAM),
        'static-storage' if static else 'scratch-capacity': program(SCRATCH_PROGRAM),
    }
    source_key = 'static-source' if static else 'source-transfer'
    source_argv = operations[source_key][0]['invocation']
    require(isinstance(source_argv[-1], str) and source_argv[-1].isdigit()
            and 0 < int(source_argv[-1]) <= 2 * MAX_SOURCE_BYTES)
    specs[source_key] = ['docker', 'exec', '--user=0:0', '--interactive', name,
        'python3', '-I', '-S', '-c', INPUT_PROGRAM, source_argv[-1]]
    references = {}
    if static:
        specs.update({'static-restore': private(PROJECT_RESTORE_PROGRAM, True),
            'project-static-environment': private(ENV_PROGRAM, True),
            'project-static-evidence': private(STATIC_PROGRAM, True)})
        references = {'project-static-environment': probe['compiler_environment']['artifact'],
                      'project-static-evidence': probe['analysis']['artifact']}
        if probe['analysis'].get('fallback_artifact') is not None:
            specs['project-static-clang-fallback'] = private(FALLBACK_PROGRAM, True)
            fallback_native = _json(operations['project-static-clang-fallback'][1])
            if 'wall_budget_ms' in fallback_native:
                allocated = fallback_native['wall_budget_ms']
                require(type(allocated) is int
                    and 0 < allocated <= LOW_CONTENTION_LIMITS['wall_seconds'] * 1000)
                specs['project-static-clang-fallback'].append(str(allocated))
            references['project-static-clang-fallback'] = probe['analysis']['fallback_artifact']
        require(_json(operations['static-restore'][1]) == {
            'file_population_sha256': snapshot['file_population_sha256'],
            'files': {path: {k: row[k] for k in ('sha256', 'bytes')} for path, row in snapshot['files'].items()}})
        population = set(specs)
    else:
        options = probe['project_options']
        specs.update({'cmake-version': [*prefix, 'cmake', '--version'],
            'gcc-version': [*prefix, 'gcc', '-dumpfullversion'],
            'g++-version': [*prefix, 'g++', '-dumpfullversion'],
            'configure': [*prefix, 'cmake', '-S', '/work/source', '-B', '/work/build',
                '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DCMAKE_C_COMPILER=/usr/local/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
                *['-D'+key+'='+value for key, value in sorted(options.items())]],
            'configuration-cache': [*program(READ_PROGRAM), '/work/build/CMakeCache.txt', str(1024*1024)],
            'compilation-database': [*program(READ_PROGRAM), '/work/build/compile_commands.json', str(4*1024*1024)],
            'post-build-database': [*program(READ_PROGRAM), '/work/build/compile_commands.json', str(4*1024*1024)],
            'project-generated-context': private(PROJECT_SNAPSHOT_PROGRAM, True),
            'project-compiler-evidence': private(COMPILER_PROGRAM, True)})
        if baseline_only:
            specs.pop('project-generated-context')
            specs.pop('project-compiler-evidence')
        else:
            references = {'project-generated-context': probe['generated_context']['artifact'],
                          'project-compiler-evidence': probe['project_compiler']['artifact']}
        if 'fileapi_client' in probe:
            from nico.assessment_cpp_fileapi_membership import QUERY_PROGRAM, CAPTURE_PROGRAM, EMPTY_SHA, QUERY_NAMES, configured_target_membership
            from nico.assessment_worker_receipts import canonical_bytes
            client=probe['fileapi_client']
            specs['fileapi-query']=[*program(QUERY_PROGRAM),'/work/build',client]
            specs['project-enabled-targets']=['docker','exec','--interactive',name,'python3','-I','-S','-c',CAPTURE_PROGRAM]
            references['project-enabled-targets']=probe['enabled_target_capture']
            require(_json(operations['fileapi-query'][1])=={'client':client,'query':{q:EMPTY_SHA for q in QUERY_NAMES}})
            db=base64.b64decode(probe['compilation_database'],validate=True)
            membership=configured_target_membership(operations['project-enabled-targets'][1],db,targets,
                source_root='/work/source',build_root='/work/build',client=client,
                cache_sha256=probe['configuration_cache_sha256'],
                compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path('native_command_capture' in probe))
            require(membership['execution_authorized'] is False and membership['context_argv_binding_verified'] is False)
            if probe.get('native_command_capture') is not None:
                from nico.assessment_cpp_native_commands import (CAPTURE_PROGRAM as NATIVE_CAPTURE_PROGRAM,
                    configured_native_commands, native_capture_request)
                native_argv=['docker','exec','--interactive',name,'python3','-I','-S','-c',NATIVE_CAPTURE_PROGRAM]
                specs['project-native-commands']=native_argv
                specs['project-native-commands-post-build']=native_argv
                specs['project-enabled-targets-post-build']=specs['project-enabled-targets']
                references['project-native-commands']=probe['native_command_capture']
                for key in ('project-native-commands-post-build','project-enabled-targets-post-build'):
                    references[key]=operations[key][0]['output_artifact']
                request=native_capture_request(operations['project-enabled-targets'][1],membership)
                expected_input=hashlib.sha256(canonical_bytes(request)).hexdigest()
                for key in ('project-native-commands','project-native-commands-post-build'):
                    require(operations[key][0].get('input_sha256')==expected_input)
                fileapi_request={'source_root':'/work/source','build_root':'/work/build','client':client,
                    'source_targets':targets,'database_sha256':hashlib.sha256(db).hexdigest(),
                    'cache_sha256':probe['configuration_cache_sha256']}
                require(operations['project-enabled-targets-post-build'][0].get('input_sha256')
                    ==hashlib.sha256(canonical_bytes(fileapi_request)).hexdigest())
                require(operations['project-enabled-targets-post-build'][1]==operations['project-enabled-targets'][1])
                from nico.assessment_cpp_native_commands import validate_native_plan_freeze
                freeze=validate_native_plan_freeze(operations['project-native-commands'][1],
                    operations['project-native-commands-post-build'][1],operations['project-enabled-targets'][1],db,targets,
                    source_root='/work/source',build_root='/work/build',client=client,
                    cache_sha256=probe['configuration_cache_sha256'],
                    compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                    compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path('native_command_capture' in probe))
                require(probe.get('native_command_freeze')==freeze)
                plan=configured_native_commands(operations['project-native-commands'][1],operations['project-enabled-targets'][1],db,targets,
                    source_root='/work/source',build_root='/work/build',client=client,
                    cache_sha256=probe['configuration_cache_sha256'],
                    compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                    compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path('native_command_capture' in probe))
                require(probe['analysis_compilation_database_sha256']==plan['analysis_database_sha256']
                    and probe['analysis_invocations']==plan['context_count'])
                if 'generated_input_materialization' in probe:
                    from nico.assessment_cpp_generated_inputs import OBSERVE_PROGRAM, validate_generation_evidence
                    from nico.assessment_cpp_project_snapshot import project_snapshot_request
                    from nico.assessment_cpp_full_project import _database
                    contexts=_database(base64.b64decode(plan['analysis_database'],validate=True),None,
                        '/work/build',nested=True,source_targets=targets)
                    materialization=probe['generated_input_materialization']
                    require(isinstance(materialization,dict))
                    generation=validate_generation_evidence(canonical_bytes({k:v for k,v in materialization.items() if k!='artifact'}),
                        operations['project-native-commands'][1],operations['project-enabled-targets'][1],membership,
                        plan,project_snapshot_request(contexts),operations,image,probe['baseline_execution'])
                    specs['generation-inputs-before']=private(OBSERVE_PROGRAM,True)
                    specs['generation-inputs-after']=private(OBSERVE_PROGRAM,True)
                    for i,target in enumerate(generation['plan']['selected_targets']):
                        specs['generation-target-'+str(i).zfill(3)]=[*prefix,'cmake','--build','/work/build',
                            '--target',target['target_name'],'--parallel',str(probe['baseline_execution']['parallel'])]
        if probe.get('unit_test_data') is not None:
            argv = operations['unit-test-data'][0]['invocation']
            require(isinstance(argv[-1], str) and argv[-1].isdigit() and 0 < int(argv[-1]) <= 128*1024*1024)
            specs['unit-test-data'] = ['docker', 'exec', '--user=0:0', '--interactive', name,
                'python3', '-I', '-S', '-c', UNIT_TEST_DATA_PROGRAM, argv[-1]]
            require(_json(operations['unit-test-data'][1]) == probe['unit_test_data'])
        asset = (runtime_plan or {}).get('unit_test_data')
        require(probe.get('unit_test_data') == ({asset['name']: asset['sha256']} if asset else None))
        require(operations['cmake-version'][1].splitlines()[0] == ('cmake version '+CMAKE_VERSION).encode()
                and all(operations[key][1].strip() == COMPILER_VERSION.encode() for key in ('gcc-version', 'g++-version')))
        cache = _json(operations['configuration-cache'][1])
        require(set(cache) == {'data', 'truncated'} and cache['truncated'] is False
                and cache['data'] == probe['configuration_cache'])
        raw_cache = base64.b64decode(cache['data'], validate=True)
        require(hashlib.sha256(raw_cache).hexdigest() == probe['configuration_cache_sha256']
                and probe['effective_project_options'] == options)
        seen = {}
        for line in raw_cache.decode().splitlines():
            key_type, separator, value = line.partition('=')
            key, colon, kind = key_type.partition(':')
            if key in options:
                require(separator and colon and kind in {'BOOL', 'STRING', 'PATH', 'FILEPATH'} and key not in seen)
                seen[key] = value
        require(seen == options)
        population = set(specs) | {'baseline-build', 'baseline-test-discovery', 'baseline-tests', 'baseline-junit', 'baseline-test-log'}
    require(set(operations) == population)
    for key, expected in specs.items():
        actual = operations[key][0]['invocation']
        program_index = actual.index('-c') + 1 if key == 'project-static-clang-fallback' and '-c' in actual else -1
        require(actual == expected or (key == 'project-static-clang-fallback'
            and len(actual) == len(expected) and program_index == expected.index('-c') + 1
            and actual[:program_index] == expected[:program_index]
            and actual[program_index + 1:] == expected[program_index + 1:]
            and _fallback_program_equal(actual[program_index], expected[program_index])))
    for key, reference in references.items():
        require(operations[key][0].get('output_artifact') == reference)
    require(_json(operations[source_key][1]) == targets)
    require(_json(operations['static-private' if static else 'analyst-setup'][1]) == {'uid':1001, 'gid':1001, 'private':True})
    require(boundary_valid(_json(operations[tag+'boundary-before'][1]), source_required=False,
                           profile=profile, executable=not static))
    storage = _json(operations['static-storage' if static else 'scratch-capacity'][1])
    require(type(storage['capacity_bytes']) is int and storage['capacity_bytes'] == resources_for(profile)['tmpfs_bytes']
            and type(storage['available_bytes']) is int and 0 < storage['available_bytes'] <= storage['capacity_bytes'])
