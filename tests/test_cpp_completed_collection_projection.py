"""Installed collection controls; Docker/tool responses are owned substitutions.

These tests exercise real producer, retained artifact and backend validators.
They prove contract behavior, not native execution, production qualification,
physical-device behavior or human report approval.
"""
import base64
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
from xml.etree import ElementTree as ET

import pytest

from nico import assessment_cpp_configuration_probe as probe_api
from nico import assessment_cpp_project_static as static
from nico import assessment_cpp_clang_fallback as clang
from nico import assessment_cpp_static_environment as environment
from nico.assessment_cpp_baseline_evidence import retained_baseline_bytes
from nico.assessment_cpp_configure_first_contract import validate_configuration
from nico.assessment_cpp_configure_first_execution import summarize_probe
from nico.assessment_cpp_configure_first_projection import (
    reconstruct_configure_first, project_configure_first_record,
)
from nico.assessment_cpp_project_compiler import PROGRAM as COMPILER_PROGRAM, _compiler_evidence_schema
from nico.assessment_cpp_generated_inputs import OBSERVE_PROGRAM, observe_generated_inputs
from nico.assessment_cpp_project_snapshot import PROJECT_SNAPSHOT_PROGRAM, capture_project_snapshot
from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import canonical_bytes, validate_contract, validate_receipt
from scripts.qualify_cpp_project_configuration import persist_project_artifact, qualification_probe_receipt
from nico.assessment_cpp_collection import validate_project_collection
from tests.test_cpp_generated_input_materialization import GenerationDocker, FIXTURE, adapted, FILEAPI_CAPTURE
from tests.test_cpp_static_environment import evidence as environment_evidence, observed
from tests.test_cpp_project_static import native
from tests.test_cpp_header_evidence import sample
from tests.test_cpp_header_transport import setup as header_shape
from tests.test_cpp_clang_header_transport import fixture as clang_shape
from tests.test_cpp_project_static_stage import StaticDocker
from tests.test_cpp_configure_first_contract import contract as base_contract


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packed(raw):
    return base64.b64encode(raw).decode()


def compiler_response(request, failing):
    rows = []
    for context in request['contexts']:
        failed = failing and context['origin'] == 'generated'
        output = (context['analysis_file'] + ':1:2: error: #error owned rejection\n').encode() if failed else b''
        dependency = ('nico_unit: ' + context['analysis_file'] + '\n').encode()
        rows.append({'context_id': context['context_id'], 'invocation': context['invocation'],
            'execution': {**observed(output), 'exit_code': 1 if failed else 0},
            'dependency_bytes': '' if failed else packed(dependency),
            'dependency_sha256': None if failed else sha(dependency),
            'source_dependencies': {context['path']: request['targets'][context['path']]}
                if not failed and context['origin'] == 'original' else {},
            'generated_dependencies': {context['path']: request['generated_files'][context['path']]['sha256']}
                if not failed and context['origin'] == 'generated' else {},
            'toolchain_dependencies': [], 'error': None})
    return canonical_bytes({'schema': _compiler_evidence_schema(request),
        'request_sha256': sha(canonical_bytes(request)), 'analyst_uid': 1001,
        'records': rows, 'duration_ms': 5})


def static_response(request, shape, failing):
    output = native(request, 'checkersReport')
    output.update(schema='nico.cpp-project-static-evidence.v4' if request['schema'].endswith('.v4') else
        'nico.cpp-project-static-evidence.v3',
        **{k: shape[k] for k in ('header_tool_receipt', 'header_tool_receipt_sha256')})
    failed = {c['context_id'] for c in request['contexts'] if failing and c['origin'] == 'generated'}
    for context, row in zip(request['contexts'], output['records']):
        document = ET.fromstring(sample()[0]); document.set('file', context['analysis_file'])
        cfg = document.find('configuration')
        for child in list(cfg): cfg.remove(child)
        definitions = {}
        for arg in context['invocation']:
            if arg.startswith('-D'):
                name, sep, value = arg[2:].partition('='); definitions[name] = value if sep else '1'
            elif arg.startswith('-U'): definitions.pop(arg[2:], None)
        cfg.set('cfg', ';'.join(k + '=' + v for k, v in sorted(definitions.items())))
        effective = ET.SubElement(cfg, 'effective', std=static._header_standard(context, request['compiler_environment']))
        for k, v in sorted(definitions.items()): ET.SubElement(effective, 'define', value=k + '=' + v)
        for key, values in static._header_effective_inputs(context).items():
            for value in values: ET.SubElement(effective, key, value=value)
        is_failed = context['context_id'] in failed
        if is_failed:
            cfg.attrib.update(disposition='preprocess_error', checks_completed='false', completed='false',
                preprocessing_returned='false', preprocessing_had_output='true', normal_pass_started='false')
        else:
            for forced in static._header_effective_inputs(context)['forced_input']:
                ET.SubElement(cfg, 'include', file=forced, parent='', kind='forced', entered='true')
        for stage in ('pre_simplification', 'normal_form_ast_validated'):
            tokens = ET.SubElement(cfg, 'token_membership', stage=stage,
                captured='false' if is_failed else 'true', invalid='false', overflow='false')
            if not is_failed: ET.SubElement(tokens, 'token_file', file=context['analysis_file'])
        trace, trace_sha, encoding = static._encode_xml(ET.tostring(document), compact=True)
        if is_failed:
            errors = ET.Element('results', version='2'); ET.SubElement(errors, 'cppcheck', version='2.17.1')
            children = ET.SubElement(errors, 'errors')
            error = ET.SubElement(children, 'error', id='preprocessorErrorDirective', severity='error',
                msg='#error owned rejection', verbose='#error owned rejection', file0=context['analysis_file'])
            ET.SubElement(error, 'location', file=context['analysis_file'], line='1', column='2')
            ET.SubElement(children, 'error', id='checkersReport', severity='information',
                msg='Active checkers: There was critical errors (use --checkers-report=<filename> to see details)')
            xml = ET.tostring(errors)
        else:
            xml = base64.b64decode(row['xml']).replace(b'Owned diagnostic',
                b'Active checkers: 167/856 (use --checkers-report=&lt;filename&gt; to see details)')
        row.update(xml=packed(xml), xml_sha256=sha(xml), header_trace=trace,
            header_trace_sha256=trace_sha, header_trace_encoding=encoding)
    return canonical_bytes(output)


def fallback_response(request, shape):
    value = {'schema': 'nico.cpp-clang-fallback-evidence.v5',
        'request_sha256': sha(canonical_bytes(request)), 'analyst_uid': 1001,
        'version': observed(b'17.0.6\n'), 'duration_ms': 5, 'records': [],
        **{k: shape[k] for k in ('header_tool_receipt', 'header_tool_receipt_sha256')}}
    for context in request['contexts']:
        source = context['analysis_file']
        trace = {'schema': 'nico.clang-header-observer.v1', 'clang_version': '17.0.6',
            'source': source, 'context_id': context['context_id'], 'standard': clang._clang_standard(context),
            'translation_unit_started': False, 'translation_unit_ended': False,
            'diagnostic_errors': True, 'observation_overflow': False,
            'files': [{'path': source, 'entered': 1, 'ast_decl_nodes': 0, 'ast_stmt_nodes': 0,
                'ast_body_callbacks': 0, 'initially_system': False, 'system_header_pragma_observed': False}]}
        encoded, digest = clang._encode_plist(canonical_bytes(trace))
        execution = observed((source + ':1:2: error: owned rejection\n'
            '    1 | #error owned rejection\n      |  ^\n1 error generated.\n').encode())
        execution['exit_code'] = 1
        value['records'].append({'context_id': context['context_id'], 'invocation': context['invocation'],
            'dropped_arguments': context['dropped_arguments'], 'execution': execution,
            'plist': '', 'plist_sha256': None, 'header_trace': encoded, 'header_trace_sha256': digest, 'error': None})
    return canonical_bytes(value)


class CompletedDocker(GenerationDocker):
    """Only Docker responses are substituted; no receipt verifier is patched."""
    def __init__(self, targets, tmp_path, failing, template):
        super().__init__(targets, tmp_path)
        self.failing, self.template, self.static_mode = failing, template, False
        self.static_docker = StaticDocker(targets)
        (tmp_path/'header-shape').mkdir(); _, self.header_shape = header_shape(tmp_path/'header-shape')
        (tmp_path/'clang-shape').mkdir(); _, _, _, self.clang_shape = clang_shape(tmp_path/'clang-shape')
        self.environment_request = self.static_request = self.fallback_request = None

    def __call__(self, args, **kwargs):
        assert args[0] == 'docker'
        raw = None
        if FILEAPI_CAPTURE in args:
            request = json.loads(kwargs['input_bytes'])
            fileapi, native_raw, _, _, _ = adapted(request['client'])
            capsule = json.loads(fileapi); capsule['source_hashes'] = self.targets
            self.fileapi = canonical_bytes(capsule)
            native_capture = json.loads(native_raw); native_capture['fileapi_capture_sha256'] = sha(self.fileapi)
            self.native = canonical_bytes(native_capture); raw = self.fileapi
        elif OBSERVE_PROGRAM in args:
            request = json.loads(kwargs['input_bytes']); build = self.tmp_path/'observed-build'
            build.mkdir(exist_ok=True)
            if self.available:
                (build/'generated').mkdir(exist_ok=True)
                (build/'generated/hidden.cpp').write_bytes(self.template)
            result = observe_generated_inputs(build, request); result.update(uid=1001, gid=1001)
            raw = canonical_bytes(result)
        elif PROJECT_SNAPSHOT_PROGRAM in args:
            request = json.loads(kwargs['input_bytes']); private = self.tmp_path/'private'
            private.mkdir(mode=0o700, exist_ok=True)
            raw = canonical_bytes(capture_project_snapshot(self.tmp_path/'observed-build', private/'baseline', request))
        elif COMPILER_PROGRAM in args:
            self.compiler_request = json.loads(kwargs['input_bytes'])
            raw = compiler_response(self.compiler_request, self.failing)
        elif environment.ENV_PROGRAM in args:
            self.environment_request = json.loads(kwargs['input_bytes'])
            result = environment_evidence(self.environment_request)
            result['schema'] = ('nico.cpp-static-environment.v2'
                if self.environment_request['schema'].endswith('.v2') else 'nico.cpp-static-environment.v1')
            for query in result['queries'].values():
                query['predefines'] = observed(base64.b64decode(query['predefines']['output']) + b'#define __cplusplus 201703L\n')
            raw = canonical_bytes(result)
        elif static.PROGRAM in args:
            self.static_request = json.loads(kwargs['input_bytes'])
            raw = static_response(self.static_request, self.header_shape, self.failing)
        elif clang.PROGRAM in args:
            self.fallback_request = json.loads(kwargs['input_bytes'])
            raw = fallback_response(self.fallback_request, self.clang_shape)
        elif probe_api.READ_PROGRAM in args and '/work/build/nico-baseline-ctest.log' in args:
            raw = canonical_bytes({'data': packed(b'owned_suite passed\n'), 'truncated': False})
        if raw is not None:
            self.calls.append((args, kwargs))
            return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'output': raw}
        if args[1] == 'create' and any('noexec' in a for a in args): self.static_mode = True
        if self.static_mode:
            result = self.static_docker(args, **kwargs); self.calls.append((args, kwargs)); return result
        return super().__call__(args, **kwargs)


class Store:
    """The actual PostgreSQL artifact binding/gzip contract, with owned storage."""
    def __init__(self, identity):
        self.identity, self.rows, self.raw, self.refs = identity, {}, {}, {}

    def put(self, key, raw):
        compressed = gzip.compress(raw, mtime=0)
        artifact_id = 'scanartifact_' + sha(key.encode() + b'\0' + raw)
        reference = dict(artifact_id=artifact_id, key=key, sha256=sha(raw), gzip_sha256=sha(compressed),
            retained_bytes=len(raw), gzip_bytes=len(compressed), storage_backend='postgres')
        i = self.identity
        self.rows[artifact_id] = {'binding': {'run_id': i.run_id, 'scan_id': i.scan_id,
            'customer_id': i.customer_id, 'project_id': i.project_id, 'repository': i.repository_id,
            'commit_sha': i.revision, 'scanner_name': 'cppcheck:' + key}, 'sha256': sha(raw),
            'gzip_sha256': sha(compressed), 'compressed_bytes': len(compressed), 'compressed': compressed}
        self.raw[key], self.refs[key] = raw, reference
        return reference

    def get(self, artifact_id, limit):
        assert limit == 8 * 1024 * 1024
        return deepcopy(self.rows[artifact_id])


def installed(tmp_path, *, failing=True, collection=True):
    source, out = tmp_path/'source', tmp_path/'out'; source.mkdir(); out.mkdir()
    template = b'#error owned rejection\n' if failing else (FIXTURE/'source/hidden.cpp.in').read_bytes()
    targets = adapted('client-nico-owned-generation')[-1]
    for name in targets:
        raw = template if name == 'hidden.cpp.in' else (FIXTURE/'source'/name).read_bytes()
        (source/name).write_bytes(raw); targets[name] = sha(raw)
    plan = base_contract(); plan['image_digest'] = 'sha256:' + 'a'*64
    cfg = plan['configuration']; cfg.pop('project_options')
    cfg.update(schema='nico.cpp-configure-first-contract.v11' if collection else
        'nico.cpp-configure-first-contract.v8', project_option_policy='conservative-cmake-v1')
    cfg['capabilities'].update(capture_enabled_targets=True, capture_native_commands=True,
        materialize_generated_inputs=True, collect_completed_compiler_failures=True)
    if not collection: cfg['capabilities'].pop('collect_completed_compiler_failures')
    assert validate_configuration(cfg) == cfg and validate_contract(plan) == plan
    identity = JobIdentity('customer', 'project', 'run', 'scan', 'owner/owned-fixture',
        'a'*40, _digest(plan), 'c'*40)
    store = Store(identity)
    def sink(key, raw):
        store.put(key, raw)
        return persist_project_artifact(out, key, raw)
    docker = CompletedDocker(targets, tmp_path, failing, template)
    probe = probe_api.probe_project_configuration(source, targets, plan['image_digest'], project_options={},
        baseline_execution=cfg['baseline_execution'], command=docker, retain_artifact=sink,
        **cfg['capabilities'])
    baseline = retained_baseline_bytes(probe, targets, cfg, plan['image_digest'])
    assert baseline is not None, (probe['error'], probe['operations'])
    store.put('project-baseline-evidence', baseline)
    store.put('project-compilation-database', base64.b64decode(probe['compilation_database'], validate=True))
    native_summary = summarize_probe(probe, targets, store.refs, collect_completed_compiler_failures=collection)
    native_summary.update(project_option_policy=cfg['project_option_policy'],
        project_options={}, project_options_sha256=_digest({}))
    receipt = {'schema': 'nico.worker-native-receipt.v7', 'identity': asdict(identity),
        'lease_id': 'e'*32, 'worker_id': 'github:owned:control:1', 'image_digest': plan['image_digest'],
        'tool_version': plan['tool_version'], 'configuration_sha256': _digest(cfg),
        'target_hashes': targets, 'native': native_summary, 'native_sha256': _digest(native_summary)}
    return identity, plan, receipt, store, probe, docker


@pytest.mark.parametrize('failing', [True, False])
def test_installed_owned_collection_reconstructs_then_projects_truthfully(tmp_path, failing):
    identity, plan, receipt, store, probe, docker = installed(tmp_path, failing=failing)
    assert probe['schema'] == 'nico.cpp-project-configuration-probe.v11'
    assert receipt['native']['schema'] == 'nico.cpp-configure-first-native.v9'
    assert docker.environment_request['schema'] == 'nico.cpp-static-environment-request.v2'
    assert docker.static_request['schema'] == 'nico.cpp-project-static-request.v4'
    _, record, _ = validate_receipt(identity, plan, receipt['lease_id'], receipt['worker_id'], receipt)
    assert record['cpp_build_evidence']['collection_complete'] is False
    assert record['cpp_build_evidence']['collection_claimed_complete'] is True
    assert record['canonical_findings_projected'] is False and not record['verified_complete']
    reconstruction = reconstruct_configure_first(identity, plan, receipt, store)
    assert reconstruction['collection_complete'] is True
    assert reconstruction['runtime'] is None
    assert reconstruction['contexts']['context_count'] == 2
    assert reconstruction['native_command_plan']['original_database_context_count'] == 1
    assert reconstruction['native_command_plan']['omitted_database_context_count'] == 1
    projected = project_configure_first_record(record, identity, plan, receipt, reconstruction)
    assert projected['cpp_build_evidence']['collection_complete'] is True
    assert projected['canonical_findings_projected'] is True
    assert projected['client_delivery_allowed'] is False and projected['human_review_required'] is True
    assert reconstruction['compiler']['complete'] is (not failing)
    assert reconstruction['analysis']['complete'] is (not failing)
    assert reconstruction['analysis']['header_context_evidence_complete'] is (not failing)
    assert projected['cppcheck_source_coverage']['all_repository_configurations_analyzed'] is (not failing)
    assert not projected['cpp_build_evidence']['header_evidence']['line_or_branch_coverage_verified']
    assert not projected['cpp_build_evidence']['header_evidence']['full_project_qualified']
    assert all(args[0] == 'docker' for args, kwargs in docker.calls)
    creates = [args for args, kwargs in docker.calls if args[1] == 'create']
    assert len(creates) == 2 and any('noexec' in arg for arg in creates[1])
    assert probe['project_static_stage']['execution_budget_seconds'] == 1020
    assert probe['project_static_stage']['wall_budget_seconds'] == 1030
    if failing:
        assert probe['status'] == 'UNPROVEN' and probe['error'] == 'worker_configuration_probe_compiler_incomplete'
        assert reconstruction['compiler_collection']['failed_contexts'] == reconstruction['static_collection']['failed_contexts']
        assert reconstruction['compiler_collection']['unparsed_contexts'] == reconstruction['compiler_collection']['failed_contexts']
        assert len(reconstruction['compiler_collection']['failed_contexts']) == 1
        assert any(v['rule_id'] == 'preprocessorErrorDirective' for v in reconstruction['analysis']['limitations'])
        assert not projected['completed'] and not projected['verified_complete'] and projected['status'] == 'failed'
        assert docker.fallback_request is not None
        assert json.loads(store.raw['project-static-clang-fallback'])['schema'] == 'nico.cpp-clang-fallback-evidence.v5'
        legacy = summarize_probe(probe, receipt['target_hashes'], store.refs)
        assert legacy['complete_execution'] is False
    else:
        assert projected['completed'] and projected['verified_complete'] and projected['status'] == 'completed'
        assert not reconstruction['compiler_collection']['failed_contexts']
        assert not reconstruction['static_collection']['failed_contexts']


def test_legacy_policy_keeps_captured_target_failure_ineligible(tmp_path):
    original_fixture = (FIXTURE/'source/hidden.cpp.in').read_bytes()
    _, plan, receipt, store, probe, docker = installed(tmp_path, collection=False)
    assert plan['configuration']['schema'] == 'nico.cpp-configure-first-contract.v8'
    assert probe['schema'] == 'nico.cpp-project-configuration-probe.v10'
    assert probe['error'] == 'worker_configuration_probe_compiler_incomplete'
    assert probe['project_compiler']['complete'] is False
    assert not receipt['native']['complete_execution']
    assert 'collection_complete' not in receipt['native']
    assert docker.environment_request is None and docker.static_request is None
    assert (FIXTURE/'source/hidden.cpp.in').read_bytes() == original_fixture


def replace_artifact(store, receipt, key, value):
    raw = canonical_bytes(value)
    reference = store.put(key, raw)
    receipt['native']['artifacts'][key] = reference


@pytest.mark.parametrize('fault', [
    'wrong-raw-digest', 'wrong-gzip-digest', 'corrupt-gzip', 'wrong-tenant',
    'old-native-eight', 'old-probe-ten', 'old-environment-one', 'old-static-three',
    'old-fallback-four', 'omitted-fallback', 'missing-baseline-reference',
    'false-pass', 'false-complete-execution', 'failed-header-credit',
    'omitted-compiler-context', 'stale-compiler-request', 'snapshot-body-substitution',
])
def test_installed_backend_rejects_unbound_or_false_collection_before_canonical_credit(tmp_path, fault):
    identity, plan, receipt, store, probe, docker = installed(tmp_path)
    # The valid paired control is reconstructed before perturbation. This also
    # prevents a broken fixture from making all negative checks false passes.
    assert reconstruct_configure_first(identity, plan, receipt, store)['collection_complete'] is True
    _, original_record, _ = validate_receipt(identity, plan, receipt['lease_id'], receipt['worker_id'], receipt)
    assert original_record['cpp_build_evidence']['collection_complete'] is False
    assert original_record['canonical_findings_projected'] is False
    native_summary = receipt['native']
    baseline_ref = native_summary['artifacts']['project-baseline-evidence']
    if fault == 'wrong-raw-digest': baseline_ref['sha256'] = '0'*64
    elif fault == 'wrong-gzip-digest': baseline_ref['gzip_sha256'] = '0'*64
    elif fault == 'corrupt-gzip':
        stored = store.rows[baseline_ref['artifact_id']]
        stored['compressed'] = stored['compressed'][:-1] + bytes([stored['compressed'][-1] ^ 1])
    elif fault == 'wrong-tenant':
        store.rows[baseline_ref['artifact_id']]['binding']['customer_id'] = 'other-customer'
    elif fault == 'old-native-eight': native_summary['schema'] = 'nico.cpp-configure-first-native.v8'
    elif fault == 'old-probe-ten':
        changed = deepcopy(probe); changed['schema'] = 'nico.cpp-project-configuration-probe.v10'
        native_summary = summarize_probe(changed, receipt['target_hashes'], store.refs,
            collect_completed_compiler_failures=True)
        native_summary.update(project_option_policy=plan['configuration']['project_option_policy'],
            project_options={}, project_options_sha256=_digest({}))
        assert native_summary['collection_complete'] is False
        receipt['native'] = native_summary
    elif fault == 'old-environment-one':
        value = json.loads(store.raw['project-static-environment'])
        value['schema'] = 'nico.cpp-static-environment.v1'
        replace_artifact(store, receipt, 'project-static-environment', value)
    elif fault == 'old-static-three':
        value = json.loads(store.raw['project-static-evidence'])
        value['schema'] = 'nico.cpp-project-static-evidence.v3'
        replace_artifact(store, receipt, 'project-static-evidence', value)
    elif fault == 'old-fallback-four':
        value = json.loads(store.raw['project-static-clang-fallback'])
        value['schema'] = 'nico.cpp-clang-fallback-evidence.v4'
        replace_artifact(store, receipt, 'project-static-clang-fallback', value)
    elif fault == 'omitted-fallback': native_summary['artifacts'].pop('project-static-clang-fallback')
    elif fault == 'missing-baseline-reference': native_summary['artifacts'].pop('project-baseline-evidence')
    elif fault == 'false-complete-execution': native_summary['complete_execution'] = True
    elif fault in {'false-pass', 'failed-header-credit', 'omitted-compiler-context', 'stale-compiler-request'}:
        value = json.loads(store.raw['project-compiler-evidence'])
        context = docker.compiler_request['contexts'][0]; row = value['records'][0]
        assert context['origin'] == 'generated' and row['execution']['exit_code'] == 1
        if fault == 'false-pass':
            row['execution']['exit_code'] = 0
            dependency = ('nico_unit: ' + context['analysis_file'] + '\n').encode()
            row.update(dependency_bytes=packed(dependency), dependency_sha256=sha(dependency),
                generated_dependencies={context['path']: docker.compiler_request['generated_files'][context['path']]['sha256']})
        elif fault == 'failed-header-credit':
            row['toolchain_dependencies'] = ['/usr/include/stdint.h']
        elif fault == 'omitted-compiler-context': value['records'].pop()
        else: value['request_sha256'] = '0'*64
        replace_artifact(store, receipt, 'project-compiler-evidence', value)
    elif fault == 'snapshot-body-substitution':
        value = json.loads(store.raw['project-generated-context'])
        value['files']['generated/hidden.cpp']['base64'] = packed(b'int forged_success;\n')
        replace_artifact(store, receipt, 'project-generated-context', value)
    else: raise AssertionError('unknown owned perturbation')
    receipt['native_sha256'] = _digest(receipt['native'])
    with pytest.raises(ValueError):
        _, record, _ = validate_receipt(identity, plan, receipt['lease_id'], receipt['worker_id'], receipt)
        assert record['cpp_build_evidence']['collection_complete'] is False
        assert record['canonical_findings_projected'] is False
        reconstruction = reconstruct_configure_first(identity, plan, receipt, store)
        project_configure_first_record(record, identity, plan, receipt, reconstruction)
    assert original_record['canonical_findings_projected'] is False
    assert original_record['cpp_build_evidence']['collection_complete'] is False


def qualification_bundle(tmp_path, *, failing=True, collection=True):
    """Qualification-only fixed-DB/runtime extension; original controls stay intact.

    The declared runtime fixture and native operations are owned substitutions,
    passed through the real runtime producer and consumer. They are not evidence
    that the compiler, functional tests, sanitizer or fuzz tools ran here.
    """
    from nico.assessment_cpp_runtime_scope import (
        capture_runtime_interfaces, derive_runtime_plan, retained_runtime_bytes, validate_retained_runtime,
    )
    from nico.assessment_cpp_runtime_execution import execute_runtime_plan
    from tests.test_cpp_contention_scheduling import source_and_scope
    from tests.test_cpp_runtime_execution import Observe
    from tests.test_cpp_baseline_execution import contract as fixed_baseline

    runtime_inputs = tmp_path/'runtime-inputs'; runtime_inputs.mkdir()
    source, targets, scope = source_and_scope(runtime_inputs)
    template = b'#error owned rejection\n' if failing else (FIXTURE/'source/hidden.cpp.in').read_bytes()
    for name in adapted('client-nico-owned-generation')[-1]:
        raw = template if name == 'hidden.cpp.in' else (FIXTURE/'source'/name).read_bytes()
        if name == 'CMakeLists.txt': raw += b'\n# SANITIZERS BUILD_FUZZ_BINARY BUILD_FOR_FUZZING\n'
        (source/name).write_bytes(raw); targets[name] = sha(raw)
    options = {}
    runtime_plan = derive_runtime_plan(source, targets, options, scope)
    observer = Observe()
    def runtime_observed(key, argv, **kwargs):
        value = observer(key, argv, **kwargs)
        if key == 'runtime-functional-results':
            raw = ('test,status,duration(seconds)\n' + ''.join(
                name + ',Passed,1\n' for name in runtime_plan['functional']['selected_tests']) + 'ALL,Passed,4\n').encode()
            value['output'] = canonical_bytes({'data': packed(raw), 'truncated': False})
        elif key == 'runtime-fuzz-corpus-stage':
            value['output'] = canonical_bytes([{'path': '/work/runtime-corpus/connect_block/s'+str(i),
                'sha256': row['sha256'], 'bytes': row['bytes']} for i, row in enumerate(runtime_plan['fuzz']['corpus'])])
        return value
    runtime_evidence = execute_runtime_plan(runtime_observed, 'owned', runtime_plan, options)
    assert runtime_evidence['complete'] is True
    runtime_rows = []
    def visit(value):
        if isinstance(value, dict):
            if 'id' in value and 'argv' in value: runtime_rows.append(value)
            else:
                for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(runtime_evidence)

    class QualificationDocker(CompletedDocker):
        def __call__(self, args, **kwargs):
            for operation in runtime_rows:
                argv = operation['argv']
                if args[-len(argv):] == argv:
                    self.calls.append((args, kwargs))
                    return {**{k: operation[k] for k in ('exit_code', 'timed_out', 'output_truncated')},
                        'output': base64.b64decode(operation['output'])}
            return super().__call__(args, **kwargs)

    out = tmp_path/'qualification-artifacts'; out.mkdir()
    artifacts = {}
    def retain(key, raw):
        ref = persist_project_artifact(out, key, raw)
        artifacts[ref['path']] = raw
        return ref
    baseline = fixed_baseline()
    baseline['compilation_database_sha256'] = sha((FIXTURE/'compile_commands.json').read_bytes())
    docker = QualificationDocker(targets, tmp_path, failing, template)
    image = 'sha256:'+'a'*64
    probe = probe_api.probe_project_configuration(source, targets, image, project_options=options,
        baseline_execution=baseline, command=docker, runtime_plan=runtime_plan, retain_artifact=retain,
        capture_generated_context=True, project_compiler_evidence=True, project_static_analysis=True,
        extended_compiler_budget=True, compiler_environment=True, capture_enabled_targets=True,
        capture_native_commands=True, materialize_generated_inputs=True,
        collect_completed_compiler_failures=collection)
    assert probe['project_static_stage']['collection_complete' if collection else 'complete'] is True, probe['error']
    assert probe['runtime_summary']['complete'] is True, probe['error']
    runtime_raw = retained_runtime_bytes(capture_runtime_interfaces(source, targets), runtime_plan, probe['runtime_evidence'])
    runtime = validate_retained_runtime(runtime_raw, targets, options, scope)
    manifest = {'repository': 'nico/owned-generated-runtime-fixture', 'commit_sha': 'a'*40,
        'tree_sha': 'b'*40, 'project_options': options}
    manifest_raw, baseline_raw, scope_raw = map(canonical_bytes, (manifest, baseline, scope))
    receipt = {'schema': 'nico.cpp-configuration-qualification.v2', 'producer_source_sha': 'c'*40,
        'production_qualified': False, 'production_dispatch_exercised': False,
        'compiled': probe['compiled'], 'tests_executed': probe['tests_executed'], 'error': None,
        'status': probe['status'], 'stage': 'execution_unproven' if failing else 'completed',
        'benchmark_sha256': sha(manifest_raw), 'execution_contract_sha256': sha(baseline_raw),
        'runtime_scope_sha256': sha(scope_raw), 'runtime_plan_sha256': sha(canonical_bytes(runtime_plan)),
        'source': {**{k: manifest[k] for k in ('repository', 'commit_sha', 'tree_sha')},
            'inventory_complete': True, 'targets': targets}, 'probe': qualification_probe_receipt(probe),
        'runtime': {'complete': True, 'artifact': retain('project-runtime-evidence', runtime_raw),
            'native_evidence_sha256': sha(runtime_raw), 'duration_ms': runtime['duration_ms']}}
    kwargs = {'manifest_raw': manifest_raw, 'baseline_raw': baseline_raw, 'scope_raw': scope_raw,
        'producer_source_sha': 'c'*40, 'image': image, 'enabled_targets_required': True,
        'native_commands_required': True, 'generated_inputs_required': True,
        'collect_completed_compiler_failures': collection}
    return receipt, lambda ref: artifacts[ref['path']], kwargs, artifacts


@pytest.mark.parametrize('failing', [False, True])
def test_current_qualification_consumer_accepts_complete_owned_collection_without_clean_target_inference(tmp_path, failing):
    receipt, read, kwargs, artifacts = qualification_bundle(tmp_path, failing=failing)
    before = deepcopy(receipt)
    result = validate_project_collection(receipt, read, **kwargs)
    assert receipt == before
    assert result['schema'] == 'nico.cpp-assessment-collection.v3'
    assert result['collection_complete'] is True and result['target_tests_passed'] is True
    assert result['target_compiler_complete'] is (not failing)
    assert result['target_static_complete'] is (not failing)
    assert result['compiler_contexts'] == (1 if failing else 2)
    assert result['static_contexts'] == (1 if failing else 2)
    assert not result['full_project_qualified'] and not result['production_qualified']
    assert result['runtime']['collection_complete'] and result['runtime']['summary']['complete']
    assert result['baseline']['required'] == ['owned_suite']
    if failing:
        assert receipt['status'] == 'UNPROVEN'
        assert result['compiler_collection']['failed_contexts_count'] == 1
        assert result['static_collection']['failed_contexts_count'] == 1
        assert not result['analyzer_header_coverage_verified']
    else:
        assert receipt['status'] == 'BASELINE_EXECUTED'
        assert result['compiler_collection']['failed_contexts_count'] == 0
        assert result['static_collection']['failed_contexts_count'] == 0


def test_legacy_qualification_success_keeps_original_collection_schema(tmp_path):
    receipt, read, kwargs, artifacts = qualification_bundle(tmp_path, failing=False, collection=False)
    before = deepcopy(receipt)
    result = validate_project_collection(receipt, read, **kwargs)
    assert receipt == before and result['schema'] == 'nico.cpp-assessment-collection.v2'
    assert result['collection_complete'] and result['target_tests_passed']
    assert result['compiler_contexts'] == result['static_contexts'] == 2
    assert 'compiler_collection' not in result and 'target_compiler_complete' not in result
    assert not result['full_project_qualified'] and not result['production_qualified']


def replace_qualification_artifact(receipt, artifacts, reference, value):
    """Rebind transport bytes so semantic negatives reach the actual verifier."""
    previous = deepcopy(reference); raw = canonical_bytes(value)
    key = previous['path'].removeprefix('artifacts/').rsplit('-', 1)[0]
    replacement = {'path': 'artifacts/'+key+'-'+sha(raw)+'.json', 'sha256': sha(raw), 'bytes': len(raw)}
    artifacts[replacement['path']] = raw
    def visit(member):
        if isinstance(member, dict):
            if member == previous:
                member.clear(); member.update(replacement)
            else:
                if member.get('output_artifact') in (previous, replacement):
                    member['output_sha256'] = replacement['sha256']
                for child in member.values(): visit(child)
        elif isinstance(member, list):
            for child in member: visit(child)
    visit(receipt)


@pytest.mark.parametrize('fault', [
    'missing-runtime-bytes', 'missing-generated-bytes', 'wrong-runtime-digest',
    'wrong-producer', 'wrong-image', 'wrong-manifest-bytes', 'wrong-baseline-bytes',
    'old-probe-ten', 'old-static-stage-three', 'old-environment-one', 'old-static-three',
    'omitted-native-plan', 'omitted-fallback-reference', 'omitted-compiler-collection',
    'false-pass', 'failed-header-credit', 'omitted-runtime-sanitizer',
])
def test_current_qualification_consumer_rejects_missing_downgraded_unbound_or_false_pass_collection(tmp_path, fault):
    receipt, read, kwargs, artifacts = qualification_bundle(tmp_path)
    # Actual current-policy complete target-failure control must pass first.
    positive = validate_project_collection(receipt, read, **kwargs)
    assert positive['collection_complete'] and not positive['target_compiler_complete']
    probe = receipt['probe']
    if fault == 'missing-runtime-bytes':
        missing = receipt['runtime']['artifact']['path']
        original_read = read
        read = lambda ref: None if ref['path'] == missing else original_read(ref)
    elif fault == 'missing-generated-bytes':
        missing = probe['generated_context']['artifact']['path']
        original_read = read
        read = lambda ref: None if ref['path'] == missing else original_read(ref)
    elif fault == 'wrong-runtime-digest': receipt['runtime']['artifact']['sha256'] = '0'*64
    elif fault == 'wrong-producer': kwargs['producer_source_sha'] = 'd'*40
    elif fault == 'wrong-image': kwargs['image'] = 'sha256:'+'b'*64
    elif fault == 'wrong-manifest-bytes': kwargs['manifest_raw'] = b'{}'
    elif fault == 'wrong-baseline-bytes': kwargs['baseline_raw'] = b'{}'
    elif fault == 'old-probe-ten': probe['schema'] = 'nico.cpp-project-configuration-probe.v10'
    elif fault == 'old-static-stage-three': probe['project_static_stage']['schema'] = 'nico.cpp-project-static-stage.v3'
    elif fault == 'omitted-native-plan': probe['native_command_plan'] = None
    elif fault == 'omitted-compiler-collection': probe['project_compiler_collection'] = None
    elif fault == 'omitted-fallback-reference':
        probe['project_static'].pop('fallback_artifact')
        probe['project_static_stage']['analysis'].pop('fallback_artifact', None)
    elif fault == 'false-pass':
        receipt.update(status='BASELINE_EXECUTED', stage='completed')
        probe.update(status='BASELINE_EXECUTED', error=None)
    elif fault == 'old-environment-one':
        reference = probe['project_static_stage']['compiler_environment']['artifact']
        value = json.loads(read(reference)); value['schema'] = 'nico.cpp-static-environment.v1'
        replace_qualification_artifact(receipt, artifacts, reference, value)
    elif fault == 'old-static-three':
        reference = probe['project_static']['artifact']
        value = json.loads(read(reference)); value['schema'] = 'nico.cpp-project-static-evidence.v3'
        replace_qualification_artifact(receipt, artifacts, reference, value)
    elif fault == 'failed-header-credit':
        reference = probe['project_compiler']['artifact']; value = json.loads(read(reference))
        row = next(r for r in value['records'] if r['execution']['exit_code'] == 1)
        row['toolchain_dependencies'] = ['/usr/include/owned-forged-header.h']
        replace_qualification_artifact(receipt, artifacts, reference, value)
    elif fault == 'omitted-runtime-sanitizer':
        reference = receipt['runtime']['artifact']; value = json.loads(read(reference))
        value['evidence']['sanitizers'].pop()
        replace_qualification_artifact(receipt, artifacts, reference, value)
    else: raise AssertionError('unknown qualification perturbation')
    with pytest.raises(ValueError):
        validate_project_collection(receipt, read, **kwargs)
