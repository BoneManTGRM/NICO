"""Bounded CMake enabled-target inventory, separate from executable argv.

An exported compile database can omit enabled targets. The FileAPI model gives
source/target/configuration membership, not a compiler command oracle. Neither
source containment nor a completed configure authorizes execution or proves
whole-project/header analysis.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import PurePosixPath
import re

RAW_LIMIT = 4 * 1024 * 1024
FILE_LIMIT = 1024 * 1024
STREAM_LIMIT = 6 * 1024 * 1024
REQUEST_LIMIT = 16 * 1024 * 1024
SCHEMA = 'nico.cpp-fileapi-capture.v1'
MEMBERSHIP_SCHEMA = 'nico.cpp-fileapi-membership.v1'
QUERY_NAMES = ('codemodel-v2', 'toolchains-v1')
EMPTY_SHA = hashlib.sha256(b'').hexdigest()

# Existing read-only full-project image PATH selects this pinned CMake wheel.
# Legacy v8 retained contracts keep their original wrapper-path expectation.
RUNTIME_CMAKE_PATH = '/opt/cmake-wheel/cmake/data/bin/cmake'


def runtime_cmake_path(native_commands):
    if type(native_commands) is not bool:
        raise ValueError('worker_configuration_probe_fileapi_invalid')
    return RUNTIME_CMAKE_PATH if native_commands else '/usr/local/bin/cmake'

# These two programs run only in the existing disposable worker boundary.
# They never import or execute assessed Python and never change its options.
QUERY_PROGRAM = r'''
import hashlib, json, os, pathlib, re, sys
build, client = pathlib.Path(sys.argv[1]), sys.argv[2]
if (not build.is_absolute() or build == pathlib.Path('/') or build.is_symlink()
        or build.parent.resolve(strict=True) != build.parent
        or re.fullmatch(r'client-nico-[A-Za-z0-9-]{1,80}', client) is None):
    raise SystemExit('fileapi_query_path')
build.mkdir(mode=0o755, exist_ok=True)
if build.resolve(strict=True) != build:
    raise SystemExit('fileapi_query_path')
# Match CMake's existing nonsecret build-tree visibility. The analyst1001
# snapshot must traverse this tree; /work/analysis stays private0700.
build.chmod(0o755)
base = build / '.cmake' / 'api' / 'v1'
for directory in (build / '.cmake', build / '.cmake/api', base, base / 'query'):
    directory.mkdir(mode=0o755, exist_ok=True)
    if directory.is_symlink() or directory.resolve(strict=True) != directory:
        raise SystemExit('fileapi_query_path')
    directory.chmod(0o755)
if (base / 'reply').exists() or (base / 'reply').is_symlink():
    raise SystemExit('fileapi_stale_reply')
query = base / 'query' / client
query.mkdir(mode=0o755, exist_ok=False)
query.chmod(0o755)
result = {}
for name in ('codemodel-v2', 'toolchains-v1'):
    with (query / name).open('xb') as handle: handle.write(b'')
    (query / name).chmod(0o644)
    result[name] = hashlib.sha256(b'').hexdigest()
print(json.dumps({'client':client,'query':result},sort_keys=True))
'''

CAPTURE_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, stat, sys
REQUEST_LIMIT, RAW_LIMIT, FILE_LIMIT, STREAM_LIMIT = 16777216, 4194304, 1048576, 6291456
def require(value):
    if not value: raise ValueError('fileapi_capture_invalid')
def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result); result[k]=v
    return result
def parse(raw):
    return json.loads(raw.decode('utf-8','strict'),object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('fileapi_capture_invalid')))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def stable(root,name,limit):
    require(isinstance(name,str) and name and not name.startswith('/')
        and all(p not in ('','.','..','.git') for p in name.split('/'))
        and '\\' not in name and not any(ord(c)<32 for c in name))
    path=root/name
    require(not path.is_symlink() and path.resolve(strict=True)==path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd); require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=limit)
        with os.fdopen(os.dup(fd),'rb') as handle: raw=handle.read(limit+1)
        after=os.fstat(fd)
        require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
            ==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns))
        return raw
    finally: os.close(fd)
raw=sys.stdin.buffer.read(REQUEST_LIMIT+1); require(0<len(raw)<=REQUEST_LIMIT)
request=parse(raw)
require(isinstance(request,dict) and set(request)=={'source_root','build_root','client','source_targets','database_sha256','cache_sha256'})
source,build=[pathlib.Path(request[k]) for k in ('source_root','build_root')]
for path in (source,build): require(path.is_absolute() and not path.is_symlink() and path.resolve(strict=True)==path)
client=request['client']; require(re.fullmatch(r'client-nico-[A-Za-z0-9-]{1,80}',client) is not None)
query=build/'.cmake/api/v1/query'/client; reply=build/'.cmake/api/v1/reply'
for path in (query,reply): require(not path.is_symlink() and path.resolve(strict=True)==path)
require({p.name for p in query.iterdir()}=={'codemodel-v2','toolchains-v1'})
queries={name:sha(stable(query,name,0)) for name in ('codemodel-v2','toolchains-v1')}
database=stable(build,'compile_commands.json',RAW_LIMIT)
cache=stable(build,'CMakeCache.txt',FILE_LIMIT)
require(sha(database)==request['database_sha256'] and sha(cache)==request['cache_sha256'])
targets=request['source_targets']; require(isinstance(targets,dict) and 0<len(targets)<=20000)
source_hashes={}; total_source=0
for name,expected in sorted(targets.items()):
    data=stable(source,name,16777216); total_source+=len(data); require(total_source<=67108864)
    require(sha(data)==expected); source_hashes[name]=sha(data)
paths=sorted(reply.iterdir()); require(0<len(paths)<=4096 and all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.json',p.name) is not None for p in paths))
indexes=[p.name for p in paths if p.name.startswith('index-')]; require(len(indexes)==1)
files={}; raw_total=0
for path in paths:
    data=stable(reply,path.name,FILE_LIMIT); require(data); raw_total+=len(data); require(raw_total<=RAW_LIMIT)
    files[path.name]={'data':base64.b64encode(data).decode('ascii'),'bytes':len(data),'sha256':sha(data)}
require(stable(build,'compile_commands.json',RAW_LIMIT)==database and stable(build,'CMakeCache.txt',FILE_LIMIT)==cache)
require([p.name for p in sorted(reply.iterdir())]==[p.name for p in paths])
result={'schema':'nico.cpp-fileapi-capture.v1','client':client,'query':queries,'index':indexes[0],
    'source_root':str(source),'build_root':str(build),
    'source_hashes':source_hashes,'database_sha256':sha(database),'cache_sha256':sha(cache),'files':files}
output=json.dumps(result,sort_keys=True,separators=(',',':')).encode(); require(len(output)<=STREAM_LIMIT)
sys.stdout.buffer.write(output)
'''


def _require(value):
    if not value:
        raise ValueError('worker_configuration_probe_fileapi_invalid')


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('worker_configuration_probe_fileapi_invalid')
    try:
        return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique,
                          parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('worker_configuration_probe_fileapi_invalid') from exc


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    from nico.assessment_worker_receipts import canonical_bytes
    return canonical_bytes(value)


def _name(value):
    return (isinstance(value, str) and len(value) <= 200
            and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.json', value) is not None)


def _root(value):
    _require(isinstance(value, str) and len(value) <= 1200 and value.startswith('/')
             and value != '/' and PurePosixPath(value).as_posix() == value
             and all(p not in ('', '.', '..') for p in value.split('/')[1:])
             and not any(ord(c) < 32 for c in value) and '\\' not in value)
    return value


def _relative(value, root):
    _require(isinstance(value, str) and 0 < len(value) <= 1200
             and not any(ord(c) < 32 for c in value) and '\\' not in value)
    if value == '.':
        return root
    path = value if value.startswith('/') else root + '/' + value
    _root(path)
    _require(path == root or path.startswith(root + '/'))
    return path


def _configured_target_membership(raw, database, targets, *, source_root, build_root,
                                client, cache_sha256, compiler_versions,
                                configuration='Debug', cmake_version='3.31.6',
                                compiler_paths=None, cmake_path='/usr/local/bin/cmake'):
    """Independently reconstruct a complete reply closure and source comparison.

    A source-present context retains its separate target/group identity. Its
    compiler argv mapping remains UNPROVEN even when all paths are present.
    """
    _require(isinstance(raw, bytes) and 0 < len(raw) <= STREAM_LIMIT
             and isinstance(database, bytes) and 0 < len(database) <= RAW_LIMIT)
    source_root, build_root = _root(source_root), _root(build_root)
    _require(source_root != build_root and not source_root.startswith(build_root + '/')
             and not build_root.startswith(source_root + '/'))
    _require(isinstance(targets, dict) and 0 < len(targets) <= 20000
             and isinstance(compiler_versions, dict) and compiler_versions
             and all(k in {'C', 'CXX'} and isinstance(v, str) for k, v in compiler_versions.items()))
    for path, digest in targets.items():
        _require(not path.startswith('/') and _relative(path, source_root) != source_root
                 and isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) is not None)
    capture = _json(raw)
    _require(isinstance(capture, dict) and set(capture) == {
        'schema', 'client', 'query', 'index', 'database_sha256', 'cache_sha256', 'source_hashes', 'files', 'source_root', 'build_root'})
    _require(capture['schema'] == SCHEMA and capture['client'] == client
             and re.fullmatch(r'client-nico-[A-Za-z0-9-]{1,80}', client) is not None
             and capture['query'] == {name: EMPTY_SHA for name in QUERY_NAMES}
             and capture['database_sha256'] == _digest(database)
             and capture['cache_sha256'] == cache_sha256
             and capture['source_hashes'] == targets
             and capture['source_root'] == source_root and capture['build_root'] == build_root)
    files = capture['files']
    _require(isinstance(files, dict) and 1 <= len(files) <= 4096 and _name(capture['index']))
    decoded, models = {}, {}
    for name, row in files.items():
        _require(_name(name) and isinstance(row, dict) and set(row) == {'data', 'bytes', 'sha256'}
                 and type(row['bytes']) is int and 0 < row['bytes'] <= FILE_LIMIT)
        try:
            data = base64.b64decode(row['data'], validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError('worker_configuration_probe_fileapi_invalid') from exc
        _require(len(data) == row['bytes'] and _digest(data) == row['sha256'])
        decoded[name], models[name] = data, _json(data)
    # Preserve the existing4MiB database boundary. The separate metadata
    # artifact stays within its4MiB raw/6MiB stream allowance and the existing
    # worker artifact envelope; CPU/memory/time/storage limits do not change.
    _require(sum(len(v) for v in decoded.values()) <= RAW_LIMIT)
    _require([n for n in files if n.startswith('index-')] == [capture['index']])
    seen = set()
    def read(name):
        _require(_name(name) and name in models)
        seen.add(name)
        return models[name]
    index = read(capture['index'])
    _require(isinstance(index, dict) and set(index) == {'cmake', 'objects', 'reply'})
    _require(index['cmake']['version']['string'] == cmake_version
             and index['cmake']['paths']['cmake'] == cmake_path
             and index['cmake']['generator'] == {'name': 'Unix Makefiles', 'multiConfig': False}
             and set(index['reply']) == {client} and set(index['reply'][client]) == set(QUERY_NAMES))
    expected_versions = {'codemodel': {'major': 2, 'minor': 7}, 'toolchains': {'major': 1, 'minor': 0}}
    references = []
    for query in QUERY_NAMES:
        ref = index['reply'][client][query]
        kind = query.rsplit('-v', 1)[0]
        _require(isinstance(ref, dict) and set(ref) == {'kind', 'version', 'jsonFile'}
                 and ref['kind'] == kind and ref['version'] == expected_versions[kind])
        references.append(ref)
    _require(index['objects'] == references)
    model = read(references[0]['jsonFile'])
    tools = read(references[1]['jsonFile'])
    _require(model['kind'] == 'codemodel' and model['version'] == expected_versions['codemodel']
             and model['paths'] == {'source': source_root, 'build': build_root}
             and tools['kind'] == 'toolchains' and tools['version'] == expected_versions['toolchains'])
    tool_bindings, languages = {}, set()
    _require(isinstance(tools['toolchains'], list) and 0 < len(tools['toolchains']) <= 3)
    for tool in tools['toolchains']:
        _require(isinstance(tool, dict))
        language = tool['language']
        _require(isinstance(language, str) and language not in languages)
        languages.add(language)
        if language == 'NONE':
            # project(... LANGUAGES NONE) enables no native compiler. A NONE
            # compile group still fails below; no C/CXX context is discarded.
            _require(tool == {'language': 'NONE', 'compiler': {'implicit': {}}})
            continue
        compiler = tool['compiler']
        _require(language in compiler_versions and isinstance(compiler, dict))
        # CMake 3.31.6 documents these as optional. Preserve observed bytes;
        # never invent missing ID/version fields. Real probe/consumer callers
        # independently verify pinned gcc/g++ version operations and image paths.
        missing_identity = 'id' not in compiler or 'version' not in compiler
        _require(('id' not in compiler or compiler['id'] == 'GNU')
                 and ('version' not in compiler or compiler['version'] == compiler_versions[language]))
        if compiler_paths is not None:
            _require(isinstance(compiler_paths, dict)
                     and compiler.get('path') == compiler_paths[language])
        else:
            _require(not missing_identity)
        tool_bindings[language] = dict(compiler)
    _require(tool_bindings and set(tool_bindings) <= set(compiler_versions))
    configs = model['configurations']
    _require(isinstance(configs, list) and len(configs) == 1 and configs[0]['name'] == configuration)
    cfg = configs[0]
    directories, projects, refs = cfg['directories'], cfg['projects'], cfg['targets']
    _require(isinstance(directories, list) and 0 < len(directories) <= 4096
             and isinstance(projects, list) and 0 < len(projects) <= 4096
             and isinstance(refs, list) and 0 < len(refs) <= 4096)
    def member(values, i):
        _require(type(i) is int and 0 <= i < len(values))
        return values[i]
    for i, directory in enumerate(directories):
        _relative(directory['source'], source_root); _relative(directory['build'], build_root)
        project = member(projects, directory['projectIndex'])
        _require(i in project['directoryIndexes'])
        if 'jsonFile' in directory:
            d = read(directory['jsonFile'])
            _require(d['paths'] == {'source': directory['source'], 'build': directory['build']})
        indexes = directory.get('targetIndexes', [])
        _require(isinstance(indexes, list) and indexes == sorted(set(indexes)))
        for t in indexes:
            _require(member(refs, t)['directoryIndex'] == i)
    for i, project in enumerate(projects):
        for d in project['directoryIndexes']:
            _require(member(directories, d)['projectIndex'] == i)
        indexes = project.get('targetIndexes', [])
        _require(isinstance(indexes, list) and indexes == sorted(set(indexes)))
        for t in indexes:
            _require(member(refs, t)['projectIndex'] == i)
    contexts, target_ids = [], set()
    for ti, ref in enumerate(refs):
        target = read(ref['jsonFile'])
        _require(ref['id'] == target['id'] and ref['name'] == target['name']
                 and isinstance(target['id'], str) and 0<len(target['id'])<=800
                 and isinstance(target['name'],str) and 0<len(target['name'])<=200
                 and not any(ord(c)<32 for c in target['id']+target['name'])
                 and target['id'] not in target_ids)
        target_ids.add(target['id'])
        directory = member(directories, ref['directoryIndex'])
        project = member(projects, ref['projectIndex'])
        _require(ti in directory.get('targetIndexes', []) and ti in project.get('targetIndexes', [])
                 and target['paths'] == {'source': directory['source'], 'build': directory['build']})
        sources, groups = target.get('sources', []), target.get('compileGroups', [])
        _require(isinstance(sources, list) and len(sources) <= 20000
                 and isinstance(groups, list) and len(groups) <= 20000)
        linked = set()
        for gi, group in enumerate(groups):
            indexes = group['sourceIndexes']
            _require(isinstance(indexes, list) and indexes and indexes == sorted(set(indexes))
                     and group['language'] in tool_bindings)
            for si in indexes:
                source = member(sources, si)
                _require(source.get('compileGroupIndex') == gi and si not in linked)
                linked.add(si)
        for si, source in enumerate(sources):
            if 'compileGroupIndex' not in source:
                continue
            gi = source['compileGroupIndex']; group = member(groups, gi)
            _require(si in linked and type(source.get('isGenerated', False)) is bool)
            path = source['path']
            path = path if path.startswith('/') else source_root + '/' + path
            # isGenerated records CMake's GENERATED property, not physical
            # origin: file(WRITE) can create a build-tree source without it.
            if path.startswith(build_root + '/'):
                _relative(path, build_root)
                origin, source_hash = 'generated', None
            else:
                _relative(path, source_root)
                rel = path[len(source_root) + 1:]
                _require(rel in targets)
                origin, source_hash = 'original', targets[rel]
            contexts.append({'configuration': configuration, 'target_id': target['id'],
                'target_name': target['name'], 'source_index': si, 'compile_group_index': gi,
                'language': group['language'], 'origin': origin, 'file': path,
                'source_sha256': source_hash, 'target_model_sha256': _digest(decoded[ref['jsonFile']]),
                'compile_group_sha256': _digest(_canonical(group))})
            if source.get('isGenerated', False) is not (origin == 'generated'):
                contexts[-1]['fileapi_generated_property'] = source.get('isGenerated')
            _require(len(contexts) <= 20000)
    # Reconstruct every FileAPI reference, including directory objects, not just hidden.c.
    known = set(seen)
    def closure(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'jsonFile':
                    _require(_name(item) and item in known)
                else:
                    closure(item)
        elif isinstance(value, list):
            for item in value:
                closure(item)
    for name in known:
        closure(models[name])
    _require(seen == set(models) and contexts)
    rows = _json(database)
    _require(isinstance(rows, list) and rows and len(rows) <= 20000)
    db_files = set()
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get('file'), str)
                 and isinstance(row.get('directory'), str))
        directory = _relative(row['directory'], build_root)
        file = row['file'] if row['file'].startswith('/') else directory + '/' + row['file']
        _root(file)
        _require(file.startswith(source_root + '/') or file.startswith(build_root + '/'))
        db_files.add(file)
    missing = [c for c in contexts if c['file'] not in db_files]
    represented = [c for c in contexts if c['file'] in db_files]
    unexpected = sorted(db_files - {c['file'] for c in contexts})
    original = sorted({c['file'][len(source_root) + 1:] for c in contexts if c['origin'] == 'original'})
    result = {'schema': MEMBERSHIP_SCHEMA, 'source_population_sha256': _digest(_canonical(targets)),
        'compilation_database_sha256': _digest(database), 'configuration_cache_sha256': cache_sha256,
        'capture_sha256': _digest(raw), 'reply_population_sha256': _digest(_canonical({n: _digest(v) for n, v in sorted(decoded.items())})),
        'source_root': source_root, 'build_root': build_root, 'configuration': configuration,
        'compiler_bindings': tool_bindings, 'configured_original_units': original,
        'configured_generated_units': sorted({c['file'][len(build_root) + 1:] for c in contexts if c['origin'] == 'generated'}),
        'configured_context_count': len(contexts), 'contexts': contexts,
        'missing_database_contexts': missing, 'source_represented_contexts': represented,
        'unexpected_database_sources': unexpected,
        'database_membership_complete': not missing and not unexpected,
        'comparison_scope': 'source_membership_only', 'context_argv_binding_verified': False,
        'execution_authorized': False, 'analysis_executed': False,
        'analyzer_header_coverage_verified': False, 'full_project_qualified': False}
    _require(len(_canonical(result)) <= STREAM_LIMIT)
    return result


def configured_target_membership(raw, database, targets, **kwargs):
    try:
        return _configured_target_membership(raw, database, targets, **kwargs)
    except (KeyError, TypeError, IndexError, RecursionError, AttributeError) as exc:
        raise ValueError('worker_configuration_probe_fileapi_invalid') from exc
