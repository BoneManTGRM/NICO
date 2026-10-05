"""Actual enabled/compiled hidden.c must survive an export-suppressed database.

The exact native fixture is retained, including original absolute paths and raw
FileAPI bytes. These tests neither execute CMake nor qualify an image.
"""
from pathlib import Path
import base64
import hashlib
import importlib
import json
import copy
import subprocess
import sys

import pytest

FIXTURE = Path(__file__).parent / 'fixtures/cpp/fileapi-export-off-primary-18c'


def owned():
    provenance = json.loads((FIXTURE / 'fixture-provenance.json').read_bytes())
    for row in provenance['files']:
        raw = (FIXTURE / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    native = json.loads((FIXTURE / 'native-result.json').read_bytes())
    files = {p.name: p.read_bytes() for p in (FIXTURE / 'reply').glob('*.json')}
    model = json.loads(next(v for k, v in files.items() if k.startswith('codemodel-')))
    targets = {p.relative_to(FIXTURE / 'source').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (FIXTURE / 'source').rglob('*') if p.is_file()}
    capsule = {'schema': 'nico.cpp-fileapi-capture.v1',
        'source_root': model['paths']['source'], 'build_root': model['paths']['build'],
        'client': 'client-nico-export-control', 'query': native['query_binding'],
        'index': next(k for k in files if k.startswith('index-')),
        'database_sha256': native['original_DB_before_sha256'], 'cache_sha256': None,
        'source_hashes': dict(targets),
        'files': {k: {'data': base64.b64encode(v).decode(), 'bytes': len(v),
                      'sha256': hashlib.sha256(v).hexdigest()} for k, v in files.items()}}
    kwargs = {'source_root': model['paths']['source'], 'build_root': model['paths']['build'],
              'client': capsule['client'], 'cache_sha256': None,
              'compiler_versions': {'C': '13.3.0'},
              'compiler_paths': {'C': native['tools']['gcc']['path']}}
    return capsule, (FIXTURE / 'compile_commands.json').read_bytes(), targets, kwargs


def inventory(capsule, database, targets, kwargs):
    try:
        module = importlib.import_module('nico.assessment_cpp_fileapi_membership')
    except ModuleNotFoundError:
        # Current configured population derives only from the exported DB.
        # Preserve a behavior failure (one unit vs two), not a missing-import failure.
        rows = json.loads(database)
        return {'configured_original_units': sorted({Path(r['file']).name for r in rows})}
    return module.configured_target_membership(json.dumps(capsule).encode(), database, targets, **kwargs)


def test_actual_enabled_compiled_target_cannot_disappear_from_configuration_inventory():
    capsule, database, targets, kwargs = owned()
    native = json.loads((FIXTURE / 'native-result.json').read_bytes())
    assert native['status'] == 'VERIFIED_OWNED_MECHANISM_ONLY'
    assert native['original_DB_bytes_unchanged'] is True
    assert Path(native['native_hidden_argv'][-1]).name == 'hidden.c'
    assert {Path(r['file']).name for r in json.loads(database)} == {'main.c'}
    proof = inventory(capsule, database, targets, kwargs)
    assert proof['configured_original_units'] == ['hidden.c', 'main.c']
    assert proof['configured_context_count'] == 2
    assert [r['file'].rsplit('/', 1)[-1] for r in proof['missing_database_contexts']] == ['hidden.c']
    assert proof['database_membership_complete'] is False
    assert proof['execution_authorized'] is False
    assert proof['analysis_executed'] is False
    assert proof['analyzer_header_coverage_verified'] is False


def rewrite(capsule, name, mutate):
    row = capsule['files'][name]
    model = json.loads(base64.b64decode(row['data']))
    mutate(model)
    raw = json.dumps(model).encode()
    capsule['files'][name] = {'data': base64.b64encode(raw).decode(),
                              'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def test_valid_complete_source_population_keeps_argv_and_execution_unproven():
    capsule, database, targets, kwargs = owned()
    native = json.loads((FIXTURE / 'native-result.json').read_bytes())
    rows = json.loads(database)
    rows.append({'directory': kwargs['build_root'], 'file': native['native_hidden_argv'][-1],
                 'arguments': native['native_hidden_argv']})
    database = json.dumps(rows).encode()
    capsule['database_sha256'] = hashlib.sha256(database).hexdigest()
    proof = inventory(capsule, database, targets, kwargs)
    assert proof['database_membership_complete'] is True
    assert proof['missing_database_contexts'] == []
    assert proof['comparison_scope'] == 'source_membership_only'
    assert proof['context_argv_binding_verified'] is False
    assert proof['full_project_qualified'] is False


def test_original_four_mib_database_boundary_is_preserved_with_membership():
    from nico.assessment_cpp_fileapi_membership import RAW_LIMIT
    capsule, database, targets, kwargs = owned()
    padded = database + b' ' * (RAW_LIMIT - len(database))
    assert json.loads(padded) == json.loads(database)
    capsule['database_sha256'] = hashlib.sha256(padded).hexdigest()
    proof = inventory(capsule, padded, targets, kwargs)
    assert proof['configured_original_units'] == ['hidden.c', 'main.c']
    assert proof['database_membership_complete'] is False
    assert proof['context_argv_binding_verified'] is False


def test_same_source_two_enabled_targets_does_not_become_one_verified_context():
    capsule, database, targets, kwargs = owned()
    hidden = next(k for k in capsule['files'] if k.startswith('target-hidden-'))
    rewrite(capsule, hidden, lambda x: x['sources'][0].update(path='main.c'))
    proof = inventory(capsule, database, targets, kwargs)
    assert proof['database_membership_complete'] is True
    assert len(proof['source_represented_contexts']) == 2
    assert len({c['target_id'] for c in proof['contexts']}) == 2
    assert proof['context_argv_binding_verified'] is False
    assert proof['analysis_executed'] is False


@pytest.mark.parametrize('mutation', [
    'missing_visible', 'missing_directory', 'stale_index', 'wrong_target', 'wrong_configuration',
    'unknown_version', 'escaped_reference', 'duplicate_target', 'wrong_source_hash',
    'wrong_generated_origin', 'wrong_compile_group', 'wrong_compiler', 'changed_database',
    'wrong_query', 'raw_digest', 'raw_size', 'unknown_extra_file', 'wrong_cache',
])
def test_partial_stale_corrupt_or_misbound_reply_is_rejected(mutation):
    capsule, database, targets, kwargs = owned()
    index, model, hidden, visible, directory, tools = [next(k for k in capsule['files'] if k.startswith(p))
        for p in ('index-', 'codemodel-', 'target-hidden-', 'target-visible-', 'directory-', 'toolchains-')]
    if mutation == 'missing_visible': del capsule['files'][visible]
    elif mutation == 'missing_directory': del capsule['files'][directory]
    elif mutation == 'stale_index': capsule['files']['index-stale.json'] = copy.deepcopy(capsule['files'][index])
    elif mutation == 'wrong_target': rewrite(capsule, hidden, lambda x: x.update(id='foreign-target'))
    elif mutation == 'wrong_configuration': rewrite(capsule, model, lambda x: x['configurations'][0].update(name='Release'))
    elif mutation == 'unknown_version': rewrite(capsule, index, lambda x: x['objects'][0]['version'].update(major=3))
    elif mutation == 'escaped_reference': rewrite(capsule, model, lambda x: x['configurations'][0]['targets'][0].update(jsonFile='../secret.json'))
    elif mutation == 'duplicate_target': rewrite(capsule, model, lambda x: x['configurations'][0]['targets'].append(copy.deepcopy(x['configurations'][0]['targets'][0])))
    elif mutation == 'wrong_source_hash': targets['hidden.c'] = '0' * 64
    elif mutation == 'wrong_generated_origin': rewrite(capsule, hidden, lambda x: x['sources'][0].update(isGenerated=True))
    elif mutation == 'wrong_compile_group': rewrite(capsule, hidden, lambda x: x['compileGroups'][0].update(sourceIndexes=[1]))
    elif mutation == 'wrong_compiler': rewrite(capsule, tools, lambda x: x['toolchains'][0]['compiler'].update(version='foreign'))
    elif mutation == 'changed_database': database += b' '
    elif mutation == 'wrong_query': capsule['query']['codemodel-v2'] = 'f' * 64
    elif mutation == 'raw_digest': capsule['files'][hidden]['sha256'] = '0' * 64
    elif mutation == 'raw_size': capsule['files'][hidden]['bytes'] += 1
    elif mutation == 'unknown_extra_file':
        data = b'{"jsonFile":"extra.json"}'
        capsule['files']['extra.json'] = {'data': base64.b64encode(data).decode(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    elif mutation == 'wrong_cache': kwargs['cache_sha256'] = 'a' * 64
    with pytest.raises(ValueError, match='worker_configuration_probe_fileapi_invalid'):
        inventory(capsule, database, targets, kwargs)


def test_duplicate_json_key_and_raw_overflow_do_not_pass():
    module = importlib.import_module('nico.assessment_cpp_fileapi_membership')
    capsule, database, targets, kwargs = owned()
    raw = json.dumps(capsule).encode()
    duplicate = raw.replace(b'{', b'{"schema":"nico.cpp-fileapi-capture.v1",', 1)
    with pytest.raises(ValueError): module.configured_target_membership(duplicate, database, targets, **kwargs)
    with pytest.raises(ValueError): module.configured_target_membership(b' ' * (module.STREAM_LIMIT + 1), database, targets, **kwargs)


def invoke_program(program, argv=(), data=None):
    return subprocess.run([sys.executable, '-I', '-S', '-c', program, *map(str, argv)],
        input=data, capture_output=True, timeout=5, env={'LANG': 'C.UTF-8'})


@pytest.mark.parametrize('four_mib_database', [False, True])
def test_installed_query_prepares_fresh_build_and_capture_retains_exact_bytes(tmp_path, four_mib_database):
    from nico.assessment_cpp_fileapi_membership import QUERY_PROGRAM, CAPTURE_PROGRAM
    # Only trusted Python executes. CMake reply bytes are retained primary data;
    # this verifies installed transport, not execution with this local toolchain.
    source, build = tmp_path / 'source', tmp_path / 'build'
    source.mkdir()
    capsule, database, targets, kwargs = owned()
    if four_mib_database:
        from nico.assessment_cpp_fileapi_membership import RAW_LIMIT
        database += b' ' * (RAW_LIMIT - len(database))
    for name in targets:
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes((FIXTURE / 'source' / name).read_bytes())
    client = 'client-nico-installed-control'
    assert not build.exists()
    query = invoke_program(QUERY_PROGRAM, (build, client))
    assert query.returncode == 0, query.stderr.decode()
    assert json.loads(query.stdout)['client'] == client
    for path in (build, build/'.cmake', build/'.cmake/api', build/'.cmake/api/v1',
                 build/'.cmake/api/v1/query', build/'.cmake/api/v1/query'/client):
        assert path.stat().st_mode & 0o777 == 0o755
    for name in ('codemodel-v2', 'toolchains-v1'):
        assert (build/'.cmake/api/v1/query'/client/name).stat().st_mode & 0o777 == 0o644
    reply = build / '.cmake/api/v1/reply'
    reply.mkdir()
    for name, row in capsule['files'].items():
        (reply / name).write_bytes(base64.b64decode(row['data']))
    cache = b'CMAKE_BUILD_TYPE:STRING=Debug\n'
    (build / 'compile_commands.json').write_bytes(database)
    (build / 'CMakeCache.txt').write_bytes(cache)
    request = dict(source_root=str(source), build_root=str(build), client=client,
        source_targets=targets, database_sha256=hashlib.sha256(database).hexdigest(),
        cache_sha256=hashlib.sha256(cache).hexdigest())
    capture = invoke_program(CAPTURE_PROGRAM, data=json.dumps(request).encode())
    assert capture.returncode == 0, capture.stderr.decode()
    captured = json.loads(capture.stdout)
    assert captured['files'] == capsule['files']
    assert captured['source_hashes'] == targets
    assert (build / 'compile_commands.json').read_bytes() == database
    assert (build / 'CMakeCache.txt').read_bytes() == cache
    # The original reply still names its actual remote roots and old query.
    # Local copying must never turn this into a fresh configured proof.
    from nico.assessment_cpp_fileapi_membership import configured_target_membership
    with pytest.raises(ValueError, match='worker_configuration_probe_fileapi_invalid'):
        configured_target_membership(capture.stdout, database, targets,
            **{**kwargs, 'source_root': str(source), 'build_root': str(build),
               'client': client, 'cache_sha256': request['cache_sha256']})
    request['source_targets'] = {**targets, 'hidden.c': '0' * 64}
    changed = invoke_program(CAPTURE_PROGRAM, data=json.dumps(request).encode())
    assert changed.returncode != 0 and changed.stdout == b''


def test_installed_query_rejects_stale_replies_and_symlink_boundary(tmp_path):
    from nico.assessment_cpp_fileapi_membership import QUERY_PROGRAM
    build = tmp_path / 'build'
    (build / '.cmake/api/v1/reply').mkdir(parents=True)
    stale = invoke_program(QUERY_PROGRAM, (build, 'client-nico-stale-control'))
    assert stale.returncode != 0 and b'fileapi_stale_reply' in stale.stderr
    outside = tmp_path / 'outside'
    outside.mkdir()
    linked = tmp_path / 'linked'
    linked.symlink_to(outside, target_is_directory=True)
    escaped = invoke_program(QUERY_PROGRAM, (linked, 'client-nico-linked-control'))
    assert escaped.returncode != 0 and b'fileapi_query_path' in escaped.stderr
    assert not (outside / '.cmake').exists()
