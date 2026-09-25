"""Compiler-environment inputs are native evidence, not completion flags."""
from copy import deepcopy
import base64
import hashlib
import importlib
import importlib.util
import json

import pytest

from tests.test_cpp_project_compiler import inputs, result_for
from nico.assessment_cpp_project_compiler import project_compiler_request, _canonical


def api():
    name = 'nico.assessment_cpp_static_environment'
    assert importlib.util.find_spec(name), 'missing compiler-environment producer and validator'
    return importlib.import_module(name)


def fixture(tmp_path):
    database, targets, snapshot, _ = inputs(tmp_path)
    compiler = project_compiler_request(database, targets, snapshot)
    raw = _canonical(result_for(compiler))
    return database, targets, snapshot, compiler, raw


def observed(raw):
    return {'exit_code': 0, 'timed_out': False, 'output_truncated': False,
            'duration_ms': 1, 'output': base64.b64encode(raw).decode(),
            'output_sha256': hashlib.sha256(raw).hexdigest()}


def evidence(request):
    env = api()
    queries = {}
    for context in request['contexts']:
        argv = env.predefine_arguments(context['invocation'], context['source'])
        key = hashlib.sha256(_canonical(argv)).hexdigest()
        macros = '#define __GNUC__ 14\n#define __GNUC_MINOR__ 2\n'
        for arg in argv:
            if arg.startswith('-D'):
                name, _, value = arg[2:].partition('=')
                macros += '#define ' + name + ' ' + (value if '=' in arg else '1') + '\n'
        queries[key] = {'invocation': argv, 'predefines': observed(macros.encode()),
            'search_invocation': env.search_arguments(argv),
            'search': observed(b'#include <...> search starts here:\n /usr/local/include\n /usr/include\nEnd of search list.\n')}
    return {'schema': 'nico.cpp-static-environment.v1',
            'request_sha256': hashlib.sha256(_canonical(request)).hexdigest(),
            'image_config_digest': request['image_config_digest'], 'analyst_uid': 1001,
            'compiler_versions': {path: observed(b'14.2.0\n') for path in sorted({v['invocation'][0] for v in queries.values()})},
            'queries': queries, 'headers': {path: {'resolved_path': path,
                'sha256': hashlib.sha256(b'/* synthetic public header */\n').hexdigest(),
                'bytes': len(b'/* synthetic public header */\n'),
                'base64': base64.b64encode(b'/* synthetic public header */\n').decode()}
                for path in sorted({p for c in request['contexts'] for p in c['toolchain_dependencies']})},
            'models': dict(env.MODEL_HASHES), 'duration_ms': 3}


def test_compiler_query_retains_semantics_but_never_reads_a_target_or_output(tmp_path):
    *_, compiler, raw = fixture(tmp_path)
    context = compiler['contexts'][0]
    argv = api().predefine_arguments(context['invocation'], context['analysis_file'])
    assert argv[0] == '/usr/local/bin/g++'
    assert argv[-5:] == ['-dM', '-E', '-x', 'c++', '/dev/null']
    assert context['analysis_file'] not in argv
    assert not any(a in {'-c', '-o', '-MF', '-MD', '-MT', '-fsyntax-only', '-I'} for a in argv)
    assert '-std=c++20' in argv
    altered = [*context['invocation'][:-1], '-mavx2', '-pthread', '-DVALUE=7', '-UOLD', context['invocation'][-1]]
    args = api().predefine_arguments(altered, context['analysis_file'])
    assert all(value in args for value in ('-mavx2', '-pthread', '-DVALUE=7', '-UOLD'))


@pytest.mark.parametrize('flag', ['-fplugin=/tmp/payload.so', '@/tmp/options', '-include', '-imacros'])
def test_compiler_environment_never_accepts_helper_or_forced_input_commands(tmp_path, flag):
    *_, compiler, raw = fixture(tmp_path)
    row = compiler['contexts'][0]
    with pytest.raises(ValueError):
        api().predefine_arguments(row['invocation'] + [flag], row['analysis_file'])


def test_environment_request_binds_every_repeated_context_and_exact_compiler_bytes(tmp_path):
    *_, compiler, raw = fixture(tmp_path)
    request = api().environment_request(compiler, raw, 'sha256:' + 'a' * 64)
    assert len(request['contexts']) == len(compiler['contexts']) == 3
    assert [c['context_id'] for c in request['contexts']] == [c['context_id'] for c in compiler['contexts']]
    assert request['compiler_evidence_sha256'] == hashlib.sha256(raw).hexdigest()
    result = api().validate_environment(_canonical(evidence(request)), request)
    assert result['request_sha256'] == hashlib.sha256(_canonical(request)).hexdigest()


@pytest.mark.parametrize('fault', ['request', 'image', 'uid', 'compiler', 'model', 'query', 'digest', 'timeout', 'directive', 'root', 'header'])
def test_environment_rejects_substitution_or_unbounded_native_inputs(tmp_path, fault):
    *_, compiler, raw = fixture(tmp_path)
    request = api().environment_request(compiler, raw, 'sha256:' + 'a' * 64)
    result = evidence(request)
    key = next(iter(result['queries']))
    if fault == 'request': result['request_sha256'] = '0' * 64
    if fault == 'image': result['image_config_digest'] = 'sha256:' + 'b' * 64
    if fault == 'uid': result['analyst_uid'] = True
    if fault == 'compiler': result['compiler_versions']['/usr/local/bin/g++'] = observed(b'13.1.0\n')
    if fault == 'model': result['models']['std'] = '0' * 64
    if fault == 'query': result['queries'][key]['invocation'] += ['-DOTHER=1']
    if fault == 'digest': result['queries'][key]['predefines']['output_sha256'] = '0' * 64
    if fault == 'timeout': result['queries'][key]['predefines']['timed_out'] = True
    if fault == 'directive': result['queries'][key]['predefines'] = observed(b'#include "/etc/passwd"\n')
    if fault == 'root': result['queries'][key]['search'] = observed(b'#include <...> search starts here:\n /etc\nEnd of search list.\n')
    if fault == 'header': result['headers']['/usr/include/not_requested.h'] = {'sha256': '0'*64, 'bytes': 5}
    with pytest.raises(ValueError): api().validate_environment(_canonical(result), request)


def test_models_do_not_turn_an_arbitrary_missing_header_into_supported_input():
    env = api()
    assert env.header_model('vector') == 'std'
    assert env.header_model('sys/socket.h') == 'posix'
    assert env.header_model('capnp/generated-header-support.h') is None
    assert env.header_model('boost/test/unit_test.hpp') == 'boost'
    assert env.header_model('missing_required.h') is None
    assert env.header_model('../vector') is None


def test_cppcheck_plan_preserves_isystem_order_and_adds_observed_predefines(tmp_path):
    from nico import assessment_cpp_project_static as static
    *_, compiler, raw = fixture(tmp_path)
    request = api().environment_request(compiler, raw, 'sha256:' + 'a' * 64)
    validated = api().validate_environment(_canonical(evidence(request)), request)
    context = deepcopy(compiler['contexts'][0])
    context['invocation'] += ['-isystem', '/work/source/headers']
    data, argv = static._static_plan(context, validated)
    args = json.loads(data)[0]['arguments']
    assert '-isystem' not in args
    assert args[args.index('/work/source/headers')-1] == '-I'
    assert any(a.startswith('--include=/work/analysis/compiler-environment/') for a in argv)
    assert '--check-level=exhaustive' in argv
    assert not any(a.startswith('--suppress') for a in argv)


def test_native_legacy_receipts_remain_reconstructible(tmp_path):
    from nico.assessment_cpp_project_static import project_static_request, validate_project_static
    from tests.test_cpp_project_static import native
    database, targets, snapshot, compiler, raw = fixture(tmp_path)
    request = project_static_request(database, targets, snapshot, raw)
    assert request['schema'] == 'nico.cpp-project-static-request.v1'
    assert validate_project_static(_canonical(native(request)), request)['complete']


@pytest.mark.parametrize('root', ['/usr/local/include/c++/14.2.0', '/usr/include/c++/14',
                                  '/usr/lib/gcc/x86_64-linux-gnu/14/include'])
def test_pinned_compiler_public_header_models_do_not_depend_on_patch_directory_layout(root):
    assert api()._model_header(root+'/stdint.h', [root]) == ('stdint.h', 'std')


def test_third_party_header_named_like_a_standard_header_is_never_reclassified():
    assert api()._model_header('/usr/local/include/vendor/vector', ['/usr/local/include/vendor']) is None


def test_only_compiler_resolved_system_boost_headers_use_the_pinned_boost_model():
    env = api()
    assert env._model_header('/usr/include/boost/multi_index/detail/bucket_array.hpp', ['/usr/include']) == (
        'boost/multi_index/detail/bucket_array.hpp', 'boost')
    assert env._model_header('/usr/local/include/vendor/boost/version.hpp', ['/usr/local/include/vendor']) is None


@pytest.mark.parametrize('root', ['/usr/include', '/usr/include/x86_64-linux-gnu'])
def test_boost_version_macros_are_native_inputs_not_a_library_model(root):
    # boost.cfg models API semantics; it cannot supply this installed version.
    env = api()
    assert env._model_header(root + '/boost/version.hpp', [root]) is None
    assert env._model_header(root + '/boost/multi_index/detail/bucket_array.hpp', [root]) == (
        'boost/multi_index/detail/bucket_array.hpp', 'boost')


def test_compiler_resolved_boost_version_retains_exact_header_and_missing_is_fatal(tmp_path):
    env = api()
    *_, compiler, raw = fixture(tmp_path)
    native = json.loads(raw)
    path = '/usr/include/boost/version.hpp'
    for row in native['records']:
        deps = base64.b64decode(row['dependency_bytes']).replace(b'/usr/include/stdint.h', path.encode())
        row.update(dependency_bytes=base64.b64encode(deps).decode(),
                   dependency_sha256=hashlib.sha256(deps).hexdigest(),
                   toolchain_dependencies=[path])
    request = env.environment_request(compiler, _canonical(native), 'sha256:' + 'a' * 64)
    data = evidence(request)
    body = b'#ifndef BOOST_VERSION_HPP\n#define BOOST_VERSION_HPP\n#define BOOST_VERSION 107400\n#endif\n'
    data['headers'][path].update(base64=base64.b64encode(body).decode(), bytes=len(body),
                                 sha256=hashlib.sha256(body).hexdigest())
    proof = env.validate_environment(_canonical(data), request)
    member = proof['headers'][path]
    assert member['projection'] == env.ROOT + '/headers' + path
    assert member['sha256'] == hashlib.sha256(body).hexdigest()
    assert member['bytes'] == len(body)
    assert member['modeled_name'] is None and member['model'] is None
    missing = {'rule_id': 'missingIncludeSystem', 'message':
               'Include file: <boost/version.hpp> not found. Please note: Cppcheck does not need standard library headers to get proper results.'}
    for context in request['contexts']:
        assert env.modeled_missing_include(missing, proof, context['context_id']) is None


def test_modeled_missing_include_reuses_validated_context_dependencies(monkeypatch):
    env = api()
    proof = {
        'models': dict(env.MODEL_HASHES),
        'native_evidence_sha256': 'a' * 64,
    }
    dependencies = {
        '/usr/include/stdint.h': {'modeled_name': 'stdint.h', 'model': 'std'}
    }
    monkeypatch.setattr(env, 'context_dependencies', lambda *args: (_ for _ in ()).throw(AssertionError('recomputed')))
    limit = {'rule_id': 'missingIncludeSystem',
             'message': 'Include file: <stdint.h> not found. Please note: Cppcheck does not need standard library headers to get proper results.',
             'locations': []}
    modeled = env.modeled_missing_include(limit, proof, 'owned-context', dependencies)
    assert modeled['compiler_resolved_headers'] == ['/usr/include/stdint.h']
    assert modeled['model'] == 'std'


def test_modeled_missing_include_uses_preindexed_dependency_population():
    env = api()
    proof = {'models': dict(env.MODEL_HASHES), 'native_evidence_sha256': 'a' * 64}
    dependencies = {
        '/usr/include/stdint.h': {'modeled_name': 'stdint.h', 'model': 'std'},
        '/usr/include/boost/asio.hpp': {'modeled_name': 'boost/asio.hpp', 'model': 'boost'},
    }
    index = {('stdint.h', 'std'): ['/usr/include/stdint.h'],
             ('boost/asio.hpp', 'boost'): ['/usr/include/boost/asio.hpp']}
    limit = {'rule_id': 'missingIncludeSystem',
             'message': 'Include file: <stdint.h> not found. Please note: Cppcheck does not need standard library headers to get proper results.',
             'locations': []}
    modeled = env.modeled_missing_include(limit, proof, 'owned-context', dependencies, index)
    assert modeled['compiler_resolved_headers'] == ['/usr/include/stdint.h']
    broken = {('stdint.h', 'std'): ['/usr/include/boost/asio.hpp']}
    with pytest.raises(ValueError, match='dependency_population'):
        env.modeled_missing_include(limit, proof, 'owned-context', dependencies, broken)
