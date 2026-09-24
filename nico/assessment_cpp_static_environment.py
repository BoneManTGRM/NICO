"""Observed GCC environment and immutable dependency inputs for Cppcheck.

The compiler is queried with an empty input, never a repository script or TU.
Compiler-visited dependency bytes are retained before projection. Public C/C++
and POSIX headers use pinned upstream models; their native missing-include
messages remain explicit modeled-input disclosures, not blanket suppressions.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import time

from nico.assessment_cpp_compiler_evidence import _regular_bytes, _run, _source_path
from nico.assessment_cpp_generated_context import _project_option
from nico.assessment_cpp_project_compiler import _extra_option, _canonical, _digest

COMPILER_VERSION = '14.2.0'
ROOT = '/work/analysis/compiler-environment'
MODEL_ROOT = '/opt/cppcheck/cfg'
MODEL_HASHES = {
    'std': '45e3cd7c43a9f38c8028dfab4bb400ab18c34f43da6fc0a1669dcf6049295013',
    'posix': 'feefad581fdae94784e012a976c29e78917d25be849b2ad973938fc804e9fd6d',
    'gnu': '8818424fca492b16ca0b14613202961731f1a2de63cc02298af97ae0db94069c',
    'boost': 'e7ff2b2d3015c08d7d95e8ec02ca2ea6a3a35d50ce9a1f76568534193cda6c81',
}
ENV_LIMITS = {'wall_seconds': 30, 'query_seconds': 5, 'queries': 128,
              'headers': 4096, 'header_bytes': 2 * 1024 * 1024,
              'total_header_bytes': 32 * 1024 * 1024}
ENV_STREAM_LIMIT = 48 * 1024 * 1024
ENV_REQUEST_LIMIT = 16 * 1024 * 1024
# Named public headers only. Internal implementation headers, intrinsics and
# arbitrary absent/application dependencies are never waived. Compiler-resolved
# system Boost headers may use the pinned Boost model instead of parsing third-party
# implementation headers; native bytes/hashes and modeled-input disclosures remain.
STD_HEADERS = frozenset(('algorithm any array atomic barrier bit bitset charconv chrono codecvt '
    'compare complex concepts condition_variable coroutine deque exception execution filesystem '
    'format forward_list fstream functional future initializer_list iomanip ios iosfwd iostream '
    'istream iterator latch limits list locale map memory memory_resource mutex new numbers '
    'numeric optional ostream queue random ranges ratio regex scoped_allocator semaphore set '
    'shared_mutex source_location span sstream stack stdexcept stop_token streambuf string '
    'string_view strstream syncstream system_error thread tuple type_traits typeindex typeinfo '
    'unordered_map unordered_set utility valarray variant vector version '
    'cassert ccomplex cctype cerrno cfenv cfloat cinttypes ciso646 climits clocale cmath '
    'csetjmp csignal cstdalign cstdarg cstdbool cstddef cstdint cstdio cstdlib cstring '
    'ctgmath ctime cuchar cwchar cwctype '
    'assert.h complex.h ctype.h errno.h fenv.h float.h inttypes.h iso646.h limits.h locale.h '
    'math.h setjmp.h signal.h stdalign.h stdarg.h stdatomic.h stdbool.h stddef.h stdint.h '
    'stdio.h stdlib.h stdnoreturn.h string.h tgmath.h threads.h time.h uchar.h wchar.h wctype.h').split())
POSIX_HEADERS = frozenset(('aio.h arpa/inet.h dirent.h dlfcn.h fcntl.h fnmatch.h glob.h grp.h '
    'iconv.h langinfo.h libgen.h monetary.h mqueue.h net/if.h netdb.h netinet/in.h netinet/tcp.h '
    'poll.h pthread.h pwd.h regex.h sched.h search.h semaphore.h spawn.h strings.h sys/ipc.h '
    'sys/mman.h sys/msg.h sys/resource.h sys/select.h sys/sem.h sys/shm.h sys/socket.h sys/stat.h '
    'sys/statvfs.h sys/time.h sys/times.h sys/types.h sys/uio.h sys/un.h sys/utsname.h sys/wait.h '
    'syslog.h termios.h unistd.h utime.h utmpx.h wordexp.h').split())


def _env_json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('worker_static_environment_duplicate_key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError('worker_static_environment_json_invalid') from exc


def _usr_path(path):
    return (isinstance(path, str) and 0 < len(path) <= 1024
            and path.startswith('/usr/') and posixpath.normpath(path) == path
            and re.fullmatch(r'[A-Za-z0-9_./+@=-]+', path) is not None
            and all(part not in {'', '.', '..'} for part in path.split('/')[1:]))


def _input_path(path):
    return (_usr_path(path) or path in {'/work/source', '/work/analysis/generated-baseline'}
            or isinstance(path, str) and re.fullmatch(
                r'/work/(?:source|analysis/generated-baseline)/[A-Za-z0-9_./+-]+', path) is not None
            and all(p not in {'', '.', '..'} for p in path.split('/')[1:]))


def predefine_arguments(invocation, source):
    """Derive a bounded empty-input query, retaining requested scalar semantics."""
    if (not isinstance(invocation, list) or not 2 <= len(invocation) <= 4096
            or any(not isinstance(a, str) or not a or len(a) > 4096
                   or any(ord(c) < 32 for c in a) for a in invocation)
            or invocation[0] not in {'/usr/local/bin/gcc', '/usr/local/bin/g++'}
            or not _input_path(source) or invocation.count(source) != 1
            or invocation.count('-c') != 1 or invocation.count('-o') != 1):
        raise ValueError('worker_static_environment_invocation_invalid')
    result, index = [invocation[0]], 1
    while index < len(invocation):
        arg = invocation[index]; index += 1
        if arg in {'-o', '-MF', '-MT', '-MQ'}:
            if index >= len(invocation) or invocation[index].startswith('-'):
                raise ValueError('worker_static_environment_output_invalid')
            index += 1
        elif arg in {'-c', '-MD', '-MMD', '-MP', '-fsyntax-only'} or arg == source:
            continue
        elif arg in {'-I', '-isystem'}:
            if index >= len(invocation) or not _input_path(invocation[index]):
                raise ValueError('worker_static_environment_include_invalid')
            index += 1  # Empty input needs no project or explicit include operand.
        elif arg.startswith('-I'):
            if not _input_path(arg[2:]):
                raise ValueError('worker_static_environment_include_invalid')
        elif arg.startswith(('-D', '-U')):
            if re.fullmatch(r'-[DU][A-Za-z_][A-Za-z0-9_]*(?:=.*)?', arg) is None:
                raise ValueError('worker_static_environment_define_invalid')
            result.append(arg)
        elif (arg in {'-g', '-g0', '-g1', '-g2', '-g3', '-ggdb', '-pthread', '-pipe',
                      '-fPIC', '-fPIE', '-fpic', '-fpie', '-fno-pie', '-fno-exceptions',
                      '-fno-rtti', '-fno-omit-frame-pointer', '-fno-strict-aliasing',
                      '-fwrapv', '-fno-sanitize-recover=all', '-fsanitize=address', '-fsanitize=undefined'}
              or re.fullmatch(r'-O(?:0|1|2|3|s|g|z)|-std=(?:gnu\+\+|c\+\+|gnu|c)[0-9]+', arg)
              or re.fullmatch(r'-W(?:no-)?[A-Za-z][A-Za-z0-9_-]*(?:=[0-9]+)?', arg)
              or _extra_option(arg)
              or arg == '-fmacro-prefix-map=/work/analysis/generated-baseline=/work/build'):
            result.append(arg)
        else:
            raise ValueError('worker_static_environment_option_unsupported')
    language = 'c++' if invocation[0].endswith('g++') else 'c'
    return [*result, '-dM', '-E', '-x', language, '/dev/null']


def search_arguments(predefines):
    if (not isinstance(predefines, list) or len(predefines) < 6
            or predefines[-5:] not in (['-dM', '-E', '-x', 'c', '/dev/null'],
                                      ['-dM', '-E', '-x', 'c++', '/dev/null'])):
        raise ValueError('worker_static_environment_query_invalid')
    return [*predefines[:-5], '-E', '-v', '-x', predefines[-2], '/dev/null']


def environment_request(compiler_request, compiler_raw, image):
    from nico.assessment_cpp_project_compiler import validate_project_compiler
    if not isinstance(image, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', image) is None:
        raise ValueError('worker_static_environment_image_invalid')
    if not validate_project_compiler(compiler_raw, compiler_request)['complete']:
        raise ValueError('worker_static_environment_compiler_incomplete')
    records = _env_json(compiler_raw)['records']
    contexts = []
    for context, native in zip(compiler_request['contexts'], records):
        predefine_arguments(context['invocation'], context['analysis_file'])
        contexts.append({'context_id': context['context_id'], 'source': context['analysis_file'],
            'invocation': context['invocation'], 'toolchain_dependencies': native['toolchain_dependencies']})
    result = {'schema': 'nico.cpp-static-environment-request.v1', 'contexts': contexts,
        'compiler_evidence_sha256': _digest(compiler_raw), 'image_config_digest': image,
        'models': dict(MODEL_HASHES), 'limits': dict(ENV_LIMITS)}
    _validate_request(result)
    return result


def _validate_request(request):
    if (not isinstance(request, dict) or set(request) != {'schema', 'contexts', 'compiler_evidence_sha256',
            'image_config_digest', 'models', 'limits'}
            or request['schema'] != 'nico.cpp-static-environment-request.v1'
            or request['limits'] != ENV_LIMITS
            or any(type(v) is not int for v in request['limits'].values())
            or request['models'] != MODEL_HASHES
            or re.fullmatch(r'[0-9a-f]{64}', str(request['compiler_evidence_sha256'])) is None
            or re.fullmatch(r'sha256:[0-9a-f]{64}', str(request['image_config_digest'])) is None
            or not isinstance(request['contexts'], list) or not 1 <= len(request['contexts']) <= 20000
            or len(_canonical(request)) > ENV_REQUEST_LIMIT):
        raise ValueError('worker_static_environment_request_invalid')
    ids, queries, headers = set(), {}, set()
    for row in request['contexts']:
        if (not isinstance(row, dict) or set(row) != {'context_id', 'source', 'invocation', 'toolchain_dependencies'}
                or re.fullmatch(r'[0-9a-f]{64}', str(row['context_id'])) is None or row['context_id'] in ids
                or not isinstance(row['toolchain_dependencies'], list)
                or len(row['toolchain_dependencies']) != len(set(row['toolchain_dependencies']))
                or any(not _usr_path(p) for p in row['toolchain_dependencies'])):
            raise ValueError('worker_static_environment_context_invalid')
        ids.add(row['context_id']); headers.update(row['toolchain_dependencies'])
        argv = predefine_arguments(row['invocation'], row['source'])
        queries[_digest(_canonical(argv))] = argv
    if len(queries) > ENV_LIMITS['queries'] or len(headers) > ENV_LIMITS['headers']:
        raise ValueError('worker_static_environment_population_limit')
    return queries, sorted(headers)


def _observation(record, seconds=5):
    if (not isinstance(record, dict) or set(record) != {'exit_code', 'timed_out', 'output_truncated',
            'duration_ms', 'output', 'output_sha256'}
            or type(record['exit_code']) is not int or record['exit_code'] != 0
            or type(record['timed_out']) is not bool or record['timed_out']
            or type(record['output_truncated']) is not bool or record['output_truncated']
            or type(record['duration_ms']) is not int or not 0 <= record['duration_ms'] <= (seconds+2)*1000):
        raise ValueError('worker_static_environment_execution_incomplete')
    try:
        raw = base64.b64decode(record['output'], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('worker_static_environment_output_invalid') from exc
    if not 0 < len(raw) <= 65536 or _digest(raw) != record['output_sha256']:
        raise ValueError('worker_static_environment_output_digest')
    return raw


def _predefines(raw, argv):
    try:
        text = raw.decode('utf-8')
    except UnicodeError as exc:
        raise ValueError('worker_static_environment_predefines_invalid') from exc
    definitions = {}
    for line in text.splitlines():
        match = re.fullmatch(r'#define ([A-Za-z_][A-Za-z0-9_]*)(\([^\r\n]*?\))?(?:[ \t]+([^\r\n]*))?', line)
        if match is None or match[1] in definitions or '\x00' in line:
            raise ValueError('worker_static_environment_predefines_invalid')
        definitions[match[1]] = (match[2] or '') + (match[3] or '')
    if definitions.get('__GNUC__') != '14' or definitions.get('__GNUC_MINOR__') != '2':
        raise ValueError('worker_static_environment_compiler_macro_mismatch')
    specified = {}
    for arg in argv:
        if arg.startswith('-D'):
            key, _, value = arg[2:].partition('='); specified[key] = value if '=' in arg else '1'
        elif arg.startswith('-U'): specified[arg[2:]] = None
    for name, value in specified.items():
        if value is None and name in definitions or value is not None and definitions.get(name) != value:
            raise ValueError('worker_static_environment_requested_macro_mismatch')
    return text


def _search_roots(raw):
    try:
        text = raw.decode('utf-8')
        start = '#include <...> search starts here:\n'
        if text.count(start) != 1 or text.count('End of search list.') != 1:
            raise ValueError()
        rows = text.split(start, 1)[1].split('End of search list.', 1)[0].splitlines()
        roots = [posixpath.normpath(line.strip()) for line in rows]
        if (not 1 <= len(roots) <= 32 or len(roots) != len(set(roots))
                or any(not _usr_path(p) for p in roots)):
            raise ValueError()
        return roots
    except (ValueError, UnicodeError) as exc:
        raise ValueError('worker_static_environment_search_invalid') from exc


def header_model(name):
    # Library API models cannot supply the installed dependency's version macros.
    # Keep the compiler-resolved metadata header as exact, hash-verified input.
    if name == 'boost/version.hpp': return None
    if name in STD_HEADERS: return 'std'
    if name in POSIX_HEADERS: return 'posix'
    if (isinstance(name, str) and name.startswith('boost/')
            and re.fullmatch(r'boost/[A-Za-z0-9_./+-]+', name) is not None
            and all(part not in {'', '.', '..'} for part in name.split('/'))):
        return 'boost'
    return None


def _model_header(path, roots):
    for root in roots:
        if path.startswith(root + '/'):
            name = path[len(root)+1:]
            model = header_model(name)
            # Only compiler-native public standard roots, not a similarly named
            # application/third-party header below an arbitrary -I directory.
            standard_root = (root in {'/usr/include', '/usr/include/x86_64-linux-gnu'}
                or re.fullmatch(r'/usr(?:/local)?/include/c\+\+/14(?:\.2(?:\.0)?)?(?:/x86_64-linux-gnu)?', root)
                or re.fullmatch(r'/usr(?:/local)?/lib/gcc/x86_64-linux-gnu/14(?:\.2(?:\.0)?)?/include(?:-fixed)?', root))
            if model and standard_root:
                return name, model
    return None


def validate_environment(raw, request):
    queries, required_headers = _validate_request(request)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= ENV_STREAM_LIMIT:
        raise ValueError('worker_static_environment_output_limit')
    native = _env_json(raw)
    if (not isinstance(native, dict) or set(native) != {'schema', 'request_sha256', 'image_config_digest',
            'analyst_uid', 'compiler_versions', 'queries', 'headers', 'models', 'duration_ms'}
            or native['schema'] != 'nico.cpp-static-environment.v1'
            or native['request_sha256'] != _digest(_canonical(request))
            or native['image_config_digest'] != request['image_config_digest']
            or type(native['analyst_uid']) is not int or native['analyst_uid'] != 1001
            or type(native['duration_ms']) is not int or not 0 <= native['duration_ms'] < ENV_LIMITS['wall_seconds']*1000
            or native['models'] != MODEL_HASHES
            or not isinstance(native['queries'], dict) or set(native['queries']) != set(queries)
            or not isinstance(native['headers'], dict) or sorted(native['headers']) != required_headers
            or not isinstance(native['compiler_versions'], dict)
            or set(native['compiler_versions']) != {argv[0] for argv in queries.values()}):
        raise ValueError('worker_static_environment_evidence_invalid')
    for version in native['compiler_versions'].values():
        if _observation(version).strip() != COMPILER_VERSION.encode():
            raise ValueError('worker_static_environment_version_invalid')
    proof_queries = {}
    roots = set()
    for key, argv in queries.items():
        item = native['queries'][key]
        if (not isinstance(item, dict) or set(item) != {'invocation', 'predefines', 'search_invocation', 'search'}
                or item['invocation'] != argv or item['search_invocation'] != search_arguments(argv)):
            raise ValueError('worker_static_environment_query_mismatch')
        macro_raw = _observation(item['predefines'])
        _predefines(macro_raw, argv)
        search = _search_roots(_observation(item['search']))
        roots.update(search)
        proof_queries[key] = {'invocation': argv, 'roots': search,
            'predefines_sha256': _digest(macro_raw), 'predefines_bytes': len(macro_raw),
            'predefines_path': ROOT + '/predefines/' + key + '.h'}
    total, headers = 0, {}
    for path, member in native['headers'].items():
        if (not isinstance(member, dict) or set(member) != {'resolved_path', 'sha256', 'bytes', 'base64'}
                or not _usr_path(member['resolved_path']) or type(member['bytes']) is not int
                or not 0 < member['bytes'] <= ENV_LIMITS['header_bytes']):
            raise ValueError('worker_static_environment_header_invalid')
        try: body = base64.b64decode(member['base64'], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError('worker_static_environment_header_invalid') from exc
        total += len(body)
        if (len(body) != member['bytes'] or _digest(body) != member['sha256']
                or total > ENV_LIMITS['total_header_bytes']):
            raise ValueError('worker_static_environment_header_digest_or_limit')
        modeled = _model_header(path, sorted(roots))
        headers[path] = {'sha256': member['sha256'], 'bytes': member['bytes'],
            'resolved_path': member['resolved_path'],
            'projection': None if modeled else ROOT + '/headers' + path,
            'modeled_name': modeled[0] if modeled else None, 'model': modeled[1] if modeled else None}
    header_index = {path: index for index, path in enumerate(sorted(headers))}
    contexts = {}
    for row in request['contexts']:
        key = _digest(_canonical(predefine_arguments(row['invocation'], row['source'])))
        contexts[row['context_id']] = {'query': key,
            'header_indices': [header_index[path] for path in row['toolchain_dependencies']]}
    return {'schema': 'nico.cpp-static-environment-model.v1',
        'request_sha256': native['request_sha256'], 'native_evidence_sha256': _digest(raw),
        'image_config_digest': native['image_config_digest'],
        'compiler_evidence_sha256': request['compiler_evidence_sha256'],
        'queries': proof_queries, 'headers': headers, 'contexts': contexts, 'models': dict(MODEL_HASHES),
        'header_population_sha256': _digest(_canonical(headers)), 'header_bytes': total,
        'model_policy': 'gcc14-unix64-public-c-cpp20-posix-boost-native-version-v3'}


def _write_input(path, raw):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with target.open('xb') as handle: handle.write(raw)
    target.chmod(0o444)


def collect_environment(request, retain=lambda value: None):
    """Execute only in the existing isolated, no-network private analyst UID."""
    queries, paths = _validate_request(request)
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_static_environment_identity')
    parent = Path('/work/analysis'); info = parent.lstat()
    if parent.resolve(strict=True) != parent or info.st_uid != 1001 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('worker_static_environment_private_invalid')
    directory = Path(ROOT); directory.mkdir(mode=0o700)
    (directory/'logs').mkdir(mode=0o700)
    start = time.monotonic(); deadline = start + ENV_LIMITS['wall_seconds']
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'HOME': ROOT, 'TMPDIR': ROOT, 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
    result = {'schema': 'nico.cpp-static-environment.v1', 'request_sha256': _digest(_canonical(request)),
        'image_config_digest': request['image_config_digest'], 'analyst_uid': os.getuid(),
        'compiler_versions': {}, 'queries': {}, 'headers': {}, 'models': {}, 'duration_ms': 0}
    retain(result)
    for name, expected in MODEL_HASHES.items():
        actual = _digest(_regular_bytes(MODEL_ROOT + '/' + name + '.cfg', 1024*1024))
        if actual != expected: raise ValueError('worker_static_environment_model_mismatch')
        result['models'][name] = actual
    for index, compiler in enumerate(sorted({argv[0] for argv in queries.values()})):
        result['compiler_versions'][compiler] = _run([compiler, '-dumpfullversion'],
            ROOT+'/logs/version'+str(index), min(deadline, time.monotonic()+5), env)
    for key, argv in queries.items():
        if time.monotonic() >= deadline: raise ValueError('worker_static_environment_deadline')
        result['queries'][key] = {'invocation': argv,
            'predefines': _run(argv, ROOT+'/logs/'+key+'-macros', min(deadline, time.monotonic()+5), env),
            'search_invocation': search_arguments(argv),
            'search': _run(search_arguments(argv), ROOT+'/logs/'+key+'-search', min(deadline, time.monotonic()+5), env)}
    total = 0
    for path in paths:
        if time.monotonic() >= deadline: raise ValueError('worker_static_environment_deadline')
        # Trusted toolchain aliases may resolve only inside the immutable /usr
        # tree. Every resolved component is read using O_NOFOLLOW.
        resolved = str(Path(path).resolve(strict=True))
        if not _usr_path(resolved): raise ValueError('worker_static_environment_header_escape')
        body = _regular_bytes(resolved, ENV_LIMITS['header_bytes']); total += len(body)
        if total > ENV_LIMITS['total_header_bytes']: raise ValueError('worker_static_environment_header_limit')
        result['headers'][path] = {'resolved_path': resolved, 'sha256': _digest(body),
                                 'bytes': len(body), 'base64': base64.b64encode(body).decode()}
    result['duration_ms'] = int((time.monotonic()-start)*1000)
    proof = validate_environment(_canonical(result), request)
    for key, query in proof['queries'].items():
        _write_input(query['predefines_path'], base64.b64decode(result['queries'][key]['predefines']['output'], validate=True))
    for path, header in proof['headers'].items():
        if header['projection']:
            _write_input(header['projection'], base64.b64decode(result['headers'][path]['base64'], validate=True))
    for query in proof['queries'].values():
        for root in query['roots']:
            Path(ROOT+'/headers'+root).mkdir(mode=0o700, parents=True, exist_ok=True)
    for here, dirs, _ in os.walk(ROOT, topdown=False):
        for subdir in dirs: Path(here, subdir).chmod(0o555)
    directory.chmod(0o555)
    result['duration_ms'] = int((time.monotonic()-start)*1000)
    if time.monotonic() >= deadline: raise ValueError('worker_static_environment_deadline')
    validate_environment(_canonical(result), request)
    return result


def run_environment():
    import sys
    saved = [None]
    try:
        raw = sys.stdin.buffer.read(ENV_REQUEST_LIMIT+1)
        if len(raw) > ENV_REQUEST_LIMIT: raise ValueError('worker_static_environment_request_limit')
        result = collect_environment(_env_json(raw), retain=lambda value: saved.__setitem__(0, value))
        output = _canonical(result)
        if len(output) > ENV_STREAM_LIMIT: raise ValueError('worker_static_environment_output_limit')
        sys.stdout.buffer.write(output)
    except Exception as exc:
        code = str(exc)
        if re.fullmatch(r'worker_static_environment_[a-z_]+', code) is None:
            code = 'worker_static_environment_failed'
        partial = _canonical({'error': code, 'partial': saved[0]})
        if len(partial) > ENV_STREAM_LIMIT:
            partial = _canonical({'error': code, 'partial_exceeded_limit': True})
        sys.stdout.buffer.write(partial); raise SystemExit(2)



def analyzer_environment_arguments(context, environment):
    """Project verified inputs without exposing broad host/system include trees."""
    if (not isinstance(environment, dict) or environment.get('schema') != 'nico.cpp-static-environment-model.v1'
            or environment.get('models') != MODEL_HASHES):
        raise ValueError('worker_project_static_environment_invalid')
    member = environment['contexts'].get(context['context_id'])
    argv = predefine_arguments(context['invocation'], context['analysis_file'])
    key = _digest(_canonical(argv))
    if not member or member['query'] != key or environment['queries'][key]['invocation'] != argv:
        raise ValueError('worker_project_static_environment_context_mismatch')
    query = environment['queries'][key]
    args, index = [context['invocation'][0]], 1
    while index < len(context['invocation']):
        arg = context['invocation'][index]; index += 1
        if arg in {'-I', '-isystem'}:
            if index == len(context['invocation']):
                raise ValueError('worker_project_static_include_invalid')
            path = context['invocation'][index]; index += 1
            args += ['-I', ROOT+'/headers'+path if _usr_path(path) else path]
        elif arg.startswith('-I'):
            path = arg[2:]
            args.append('-I' + (ROOT+'/headers'+path if _usr_path(path) else path))
        else:
            args.append(arg)
    for root in query['roots']:
        args += ['-I', ROOT+'/headers'+root]
    libraries = ['posix', 'gnu']
    paths = sorted(environment['headers'])
    if any('/boost/' in paths[index] for index in member['header_indices']): libraries.append('boost')
    flags = ['--include=' + query['predefines_path'],
             *['--library='+MODEL_ROOT+'/'+lib+'.cfg' for lib in libraries]]
    return args, flags


def verify_environment_inputs(environment):
    """Recheck the observed immutable input bytes inside the analyzer boundary."""
    if (environment.get('schema') != 'nico.cpp-static-environment-model.v1'
            or environment.get('models') != MODEL_HASHES
            or _digest(_canonical(environment['headers'])) != environment['header_population_sha256']):
        raise ValueError('worker_project_static_environment_invalid')
    for name, expected in MODEL_HASHES.items():
        if _digest(_regular_bytes(MODEL_ROOT+'/'+name+'.cfg', 1024*1024)) != expected:
            raise ValueError('worker_project_static_model_changed')
    for key, query in environment['queries'].items():
        path = ROOT + '/predefines/' + key + '.h'
        if query['predefines_path'] != path or _digest(_canonical(query['invocation'])) != key:
            raise ValueError('worker_project_static_predefines_binding')
        raw = _regular_bytes(path, 65536)
        if len(raw) != query['predefines_bytes'] or _digest(raw) != query['predefines_sha256']:
            raise ValueError('worker_project_static_predefines_changed')
        _predefines(raw, query['invocation'])
    for path, member in environment['headers'].items():
        if not _usr_path(path): raise ValueError('worker_project_static_dependency_path')
        if member['projection'] is not None:
            expected = ROOT + '/headers' + path
            if member['projection'] != expected:
                raise ValueError('worker_project_static_dependency_projection')
            raw = _regular_bytes(expected, ENV_LIMITS['header_bytes'])
            if len(raw) != member['bytes'] or _digest(raw) != member['sha256']:
                raise ValueError('worker_project_static_dependency_changed')


def context_dependencies(environment, context_id):
    paths = sorted(environment['headers'])
    indices = environment['contexts'][context_id]['header_indices']
    if (not isinstance(indices, list) or len(indices) != len(set(indices))
            or any(type(i) is not int or not 0 <= i < len(paths) for i in indices)):
        raise ValueError('worker_project_static_dependency_population')
    return {paths[i]: environment['headers'][paths[i]] for i in indices}


def modeled_missing_include(limit, environment, context_id):
    """A documented model is distinct from a present or analyzer-visited header.

    Preserve the original diagnostic. Only a named public header that the actual
    compiler resolved for this exact context and a hash-verified upstream model
    can be recorded as modeled rather than an unavailable required dependency.
    """
    if limit.get('rule_id') != 'missingIncludeSystem': return None
    match = re.fullmatch(r'Include file: <([^<>]+)> not found\. Please note: Cppcheck does not need standard library headers to get proper results\.', limit.get('message', ''))
    if match is None: return None
    name = match[1]; model = header_model(name)
    if not model or environment['models'].get(model) != MODEL_HASHES[model]: return None
    resolved = [path for path, member in context_dependencies(environment, context_id).items()
                if member['modeled_name'] == name and member['model'] == model]
    if not resolved: return None
    return {**limit, 'context_id': context_id, 'classification': 'modeled_public_header',
            'model': model, 'model_sha256': MODEL_HASHES[model], 'header_name': name,
            'compiler_resolved_headers': resolved,
            'compiler_environment_sha256': environment['native_evidence_sha256'],
            'analyzer_header_visited': False}

ENV_PROGRAM = ('import base64, hashlib, json, os, posixpath, re, stat, subprocess, time\nfrom pathlib import Path\n'
    + '\n'.join(name + '=' + repr(value) for name, value in {
        'COMPILER_VERSION': COMPILER_VERSION, 'ROOT': ROOT, 'MODEL_ROOT': MODEL_ROOT,
        'MODEL_HASHES': MODEL_HASHES, 'ENV_LIMITS': ENV_LIMITS, 'ENV_STREAM_LIMIT': ENV_STREAM_LIMIT,
        'ENV_REQUEST_LIMIT': ENV_REQUEST_LIMIT, 'STD_HEADERS': tuple(sorted(STD_HEADERS)), 'POSIX_HEADERS': tuple(sorted(POSIX_HEADERS))}.items())
    + '\n' + '\n'.join(inspect.getsource(f) for f in (
        _canonical, _digest, _source_path, _project_option, _extra_option, _regular_bytes, _run,
        _env_json, _usr_path, _input_path, predefine_arguments, search_arguments, _validate_request,
        _observation, _predefines, _search_roots, header_model, _model_header,
        validate_environment, _write_input, collect_environment, run_environment))
    + '\nrun_environment()\n')

# These same audited functions run in the existing standalone analyzer program.
STATIC_ENV_SUPPORT = ('import posixpath\n' + '\n'.join(name+'='+repr(value) for name,value in {
    'ROOT': ROOT, 'MODEL_ROOT': MODEL_ROOT, 'MODEL_HASHES': MODEL_HASHES, 'ENV_LIMITS': ENV_LIMITS,
    'STD_HEADERS': tuple(sorted(STD_HEADERS)), 'POSIX_HEADERS': tuple(sorted(POSIX_HEADERS))}.items())
    + '\n' + '\n'.join(inspect.getsource(f) for f in (_usr_path, _input_path, predefine_arguments,
        _predefines, analyzer_environment_arguments, verify_environment_inputs, context_dependencies)))


def bind_environment(proof, compiler_request, compiler_raw):
    """Check controller-derived model bindings against the full compiler plan."""
    if not isinstance(proof, dict) or proof.get('models') != MODEL_HASHES:
        raise ValueError('worker_project_static_environment_invalid')
    requested = environment_request(compiler_request, compiler_raw, proof.get('image_config_digest'))
    queries, paths = _validate_request(requested)
    if (proof.get('schema') != 'nico.cpp-static-environment-model.v1'
            or proof.get('compiler_evidence_sha256') != _digest(compiler_raw)
            or proof.get('request_sha256') != _digest(_canonical(requested))
            or proof.get('header_population_sha256') != _digest(_canonical(proof.get('headers')))
            or sorted(proof.get('headers', {})) != paths
            or set(proof.get('queries', {})) != set(queries)
            or set(proof.get('contexts', {})) != {r['context_id'] for r in requested['contexts']}
            or re.fullmatch(r'[0-9a-f]{64}', str(proof.get('native_evidence_sha256'))) is None):
        raise ValueError('worker_project_static_environment_binding')
    for row in requested['contexts']:
        key = _digest(_canonical(predefine_arguments(row['invocation'], row['source'])))
        if (proof['contexts'][row['context_id']]['query'] != key
                or list(context_dependencies(proof, row['context_id'])) != row['toolchain_dependencies']
                or proof['queries'][key]['invocation'] != queries[key]):
            raise ValueError('worker_project_static_environment_population')
    return proof
