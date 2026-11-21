"""Ordered configured C/C++ commands from CMake3.31 Unix Makefile data.

This parser never runs Make or assessed shell code. It supports literal generated
object rules, scalar flags and GCC14 response files, failing closed on wrappers,
dynamic Make/shell syntax and incomplete populations. Configured commands are
distinct from the original database and from independently executed receipts.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import PurePosixPath
import re
import shlex

from nico.assessment_cpp_fileapi_membership import (
    FILE_LIMIT, RAW_LIMIT, STREAM_LIMIT, _json, configured_target_membership,
)

CAPTURE_SCHEMA = 'nico.cpp-native-command-capture.v1'
PLAN_SCHEMA = 'nico.cpp-native-command-plan.v1'
NATIVE_MAKE_FILES = ('build.make', 'flags.make', 'depend.make', 'compiler_depend.make', 'progress.make')
UTILITY_MAKE_FILES = ('build.make', 'compiler_depend.make', 'progress.make')
PARENT_MAKE_FILES = ('Makefile', 'CMakeFiles/Makefile2')


def _require(value):
    if not value:
        raise ValueError('worker_native_command_plan_invalid')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _path(value, root):
    _require(isinstance(value, str) and 0 < len(value) <= 1200
             and re.fullmatch(r'[A-Za-z0-9_./+-]+', value) is not None
             and all(p not in ('', '.', '..', '.git') for p in value.lstrip('/').split('/')))
    result = value if value.startswith('/') else root + '/' + value
    _require(result.startswith(root + '/') and PurePosixPath(result).as_posix() == result)
    return result


def _decode_files(capsule):
    files = capsule.get('files')
    _require(isinstance(files, dict) and 0 < len(files) <= 4096)
    result = {}
    for name, row in files.items():
        _require(isinstance(row, dict) and set(row) == {'data', 'bytes', 'sha256'}
                 and type(row['bytes']) is int
                 and (0 if name.endswith('.rsp') else 1) <= row['bytes'] <= FILE_LIMIT)
        try:
            raw = base64.b64decode(row['data'], validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError('worker_native_command_plan_invalid') from exc
        _require(len(raw) == row['bytes'] and _sha(raw) == row['sha256'])
        result[name] = raw
    _require(sum(map(len, result.values())) <= RAW_LIMIT)
    return result


def _target_directories(fileapi, membership):
    build = membership['build_root']
    models = [_json(raw) for raw in _decode_files(fileapi).values()]
    result = {}
    compiled = {c['target_id']: c['target_name'] for c in membership['contexts']}
    utility = {m['id']: m['name'] for m in models if m.get('type') == 'UTILITY'}
    _require(not set(compiled) & set(utility))
    for target_id, name in {**compiled, **utility}.items():
        target_models = [m for m in models if m.get('id') == target_id]
        _require(len(target_models) == 1)
        model = target_models[0]
        _require(model['name'] == name
                 and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+-]{0,199}', model['name']) is not None)
        if target_id in utility:
            _require(not model.get('compileGroups'))
        directory = model['paths']['build']
        directory = build if directory == '.' else _path(directory, build)
        support = directory + '/CMakeFiles/' + model['name'] + '.dir'
        result[target_id] = {'directory': directory, 'support': support,
                             'relative': support[len(build) + 1:], 'compiled': target_id in compiled}
    _require(len({r['support'] for r in result.values()}) == len(result))
    return result


def native_capture_request(fileapi_raw, membership):
    """Bound the native capture to the verified model and shared metadata cap."""
    fileapi = _json(fileapi_raw)
    _require(membership['capture_sha256'] == _sha(fileapi_raw))
    files = _decode_files(fileapi)
    directories = _target_directories(fileapi, membership)
    return {'source_root': membership['source_root'], 'build_root': membership['build_root'],
        'fileapi_capture_sha256': _sha(fileapi_raw),
        'database_sha256': membership['compilation_database_sha256'],
        'cache_sha256': membership['configuration_cache_sha256'],
        'metadata_remaining_bytes': RAW_LIMIT - sum(map(len, files.values())),
        'native_directories': sorted(r['relative'] for r in directories.values() if r['compiled']),
        'utility_directories': sorted(r['relative'] for r in directories.values() if not r['compiled'])}


CAPTURE_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, stat, sys
def require(value):
    if not value: raise ValueError('native_command_capture_invalid')
def unique(pairs):
    result={}
    for k,v in pairs: require(k not in result); result[k]=v
    return result
def parse(raw):
    return json.loads(raw.decode('utf-8','strict'),object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError('native_command_capture_invalid')))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def stable(root,name,limit):
    require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_./+-]+',name) is not None
        and not name.startswith('/') and all(p not in ('','.','..','.git') for p in name.split('/')))
    path=root/name; require(path.resolve(strict=True)==path and not path.is_symlink())
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd); require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=limit)
        with os.fdopen(os.dup(fd),'rb') as h: raw=h.read(limit+1)
        after=os.fstat(fd)
        require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
            ==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns))
        return raw
    finally: os.close(fd)
raw_request=sys.stdin.buffer.read(16777217); require(0<len(raw_request)<=16777216)
request=parse(raw_request)
require(isinstance(request,dict) and set(request)=={'source_root','build_root','fileapi_capture_sha256',
    'database_sha256','cache_sha256','metadata_remaining_bytes','native_directories','utility_directories'})
source,build=[pathlib.Path(request[k]) for k in ('source_root','build_root')]
for p in (source,build): require(p.is_absolute() and not p.is_symlink() and p.resolve(strict=True)==p)
for k in ('fileapi_capture_sha256','database_sha256','cache_sha256'):
    require(isinstance(request[k],str) and re.fullmatch(r'[0-9a-f]{64}',request[k]) is not None)
limit=request['metadata_remaining_bytes']; require(type(limit) is int and 0<limit<=4194304)
directories=request['native_directories']
require(isinstance(directories,list) and 0<len(directories)<=4096 and directories==sorted(set(directories)))
utility=request['utility_directories']
require(isinstance(utility,list) and utility==sorted(set(utility)) and not set(utility)&set(directories)
    and len(utility)+len(directories)<=4096)
db=stable(build,'compile_commands.json',4194304); cache=stable(build,'CMakeCache.txt',1048576)
require(sha(db)==request['database_sha256'] and sha(cache)==request['cache_sha256'])
files={}; population={}; total=0
for name in ('Makefile','CMakeFiles/Makefile2'):
    raw=stable(build,name,1048576); require(raw); total+=len(raw); require(total<=limit)
    files[name]={'data':base64.b64encode(raw).decode('ascii'),'bytes':len(raw),'sha256':sha(raw)}
for directory in directories+utility:
    require(isinstance(directory,str) and re.fullmatch(r'(?:[A-Za-z0-9_.+-]+/)*CMakeFiles/[A-Za-z0-9_.+-]+\.dir',directory) is not None)
    root=build/directory; require(root.resolve(strict=True)==root and not root.is_symlink())
    fixed={'build.make','compiler_depend.make','progress.make'}
    if directory in directories: fixed|={'flags.make','depend.make'}
    names=sorted(fixed|{p.name for p in root.iterdir() if p.name.endswith('.rsp')})
    population[directory]=names
    for name in names:
        require(re.fullmatch(r'[A-Za-z0-9_.+-]+',name) is not None)
        relative=directory+'/'+name; raw=stable(build,relative,1048576)
        require(raw or name.endswith('.rsp')); total+=len(raw); require(total<=limit and len(files)<4096)
        files[relative]={'data':base64.b64encode(raw).decode('ascii'),'bytes':len(raw),'sha256':sha(raw)}
require(stable(build,'compile_commands.json',4194304)==db and stable(build,'CMakeCache.txt',1048576)==cache)
for directory,names in population.items():
    fixed={'build.make','compiler_depend.make','progress.make'}
    if directory in directories: fixed|={'flags.make','depend.make'}
    require(sorted(fixed|{p.name for p in (build/directory).iterdir() if p.name.endswith('.rsp')})==names)
for relative,row in files.items(): require(sha(stable(build,relative,1048576))==row['sha256'])
result={k:request[k] for k in ('source_root','build_root','fileapi_capture_sha256','database_sha256','cache_sha256')}
result.update(schema='nico.cpp-native-command-capture.v1',files=files)
output=json.dumps(result,sort_keys=True,separators=(',',':')).encode(); require(len(output)<=6291456)
sys.stdout.buffer.write(output)
'''


def gcc_response_arguments(raw):
    """GCC14 libiberty buildargv: backslash escapes even inside single quotes."""
    _require(isinstance(raw, bytes) and len(raw) <= FILE_LIMIT and b'\0' not in raw)
    try:
        text = raw.decode('utf-8', 'strict')
    except UnicodeError as exc:
        raise ValueError('worker_native_command_plan_invalid') from exc
    _require(not any(ord(c) < 32 and c not in '\t\n\r\v\f' for c in text))
    argv, i = [], 0
    while i < len(text):
        while i < len(text) and text[i] in ' \t\n\r\v\f':
            i += 1
        if i == len(text):
            break
        value, quote = [], None
        while i < len(text):
            c = text[i]
            i += 1
            if c == '\\':
                # Reject dangling escape or unmatched quote rather than guess
                # which compiler diagnostic an incomplete transport would emit.
                _require(i < len(text))
                value.append(text[i]); i += 1
            elif quote is not None:
                if c == quote:
                    quote = None
                else:
                    value.append(c)
            elif c in "'\"":
                quote = c
            elif c in ' \t\n\r\v\f':
                break
            else:
                value.append(c)
        _require(quote is None and len(value) <= 16384)
        argv.append(''.join(value)); _require(len(argv) <= 4096)
    return argv


def _expand_response(argv, files, cwd, build):
    references = []
    def expand(values, stack):
        result = []
        for value in values:
            if value.startswith('@'):
                path = _path(value[1:], cwd) if not value[1:].startswith('/') else _path(value[1:], build)
                _require(path.startswith(build + '/') and path not in stack and len(stack) < 64)
                name = path[len(build) + 1:]
                _require(name in files and name.endswith('.rsp'))
                references.append({'path': path, 'sha256': _sha(files[name]), 'bytes': len(files[name])})
                _require(len(references) <= 4096)
                result.extend(expand(gcc_response_arguments(files[name]), (*stack, path)))
            else:
                result.append(value)
            _require(len(result) <= 4096)
        return result
    # GCC expands response arguments after the executable name only.
    return [argv[0], *expand(argv[1:], ())], references


def _flags(raw):
    try:
        text = raw.decode('utf-8', 'strict')
    except UnicodeError as exc:
        raise ValueError('worker_native_command_plan_invalid') from exc
    _require(text.startswith('# CMAKE generated file: DO NOT EDIT!\n') and '\0' not in text)
    text = re.sub(r'\\\n[ \t]*', ' ', text)
    result = {'EQUALS': '='}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'((?:C|CXX)_(?:DEFINES|INCLUDES|FLAGS)) = ?(.*)', line)
        _require(match is not None and match[1] not in result)
        # Make comments are independent of shell quote state. CMake escapes
        # literal hashes for Make; reject a raw trailing comment as ambiguity.
        value = match[2]
        _require(re.search(r'(?<!\\)#', value) is None)
        result[match[1]] = value.replace('\\#', '#')
    return result


def _expand_variables(recipe, flags):
    def replace(match):
        name = match[1]
        _require(name in flags)
        return flags[name]
    result = re.sub(r'\$\(([A-Za-z0-9_]+)\)', replace, recipe)
    # No dynamic Make functions, recursive variables or shell interpolation.
    _require('$' not in result and '`' not in result and '\0' not in result)
    return result


def _shell_arguments(command):
    quote, escape = None, False
    for c in command:
        _require(c not in '\r\n\0')
        if escape:
            escape = False
            continue
        if c == '\\' and quote != "'":
            escape = True
        elif quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        else:
            _require(c not in ';&|<>()*?[]~{}#')
    _require(quote is None and not escape and '$' not in command and '`' not in command)
    try:
        result = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError('worker_native_command_plan_invalid') from exc
    _require(result and len(result) <= 4096 and all(len(a) <= 16384 for a in result))
    return result


def _make_environment(raw, files, support, source, build, cmake_path, *, compiled=True,
                      top_level_makefile=False):
    """Reject overrides and executable Make syntax before any recipe expansion.

    All included Make inputs are captured, not just flags.make. CMake's native
    dependency rules and progress integers cannot set compiler variables.
    """
    text = raw.decode('utf-8', 'strict')
    _require(text.startswith('# CMAKE generated file: DO NOT EDIT!\n') and '\0' not in text)
    relative = support[len(build) + 1:] if support else None
    native_files = NATIVE_MAKE_FILES if compiled else UTILITY_MAKE_FILES
    includes = set()
    assignments = {
        'SHELL': '/bin/sh', 'CMAKE_COMMAND': cmake_path,
        'RM': cmake_path + ' -E rm -f', 'EQUALS': '=',
        'CMAKE_SOURCE_DIR': source, 'CMAKE_BINARY_DIR': build,
        '$(VERBOSE)MAKESILENT': '-s',
    }
    seen = set()
    # Nonrecipe continuations are Make's whitespace folding. A continued
    # recipe is outside this parser's narrow literal supported grammar.
    logical = re.sub(r'\\\n[ \t]*', ' ', text)
    rule = None
    for line in logical.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        if line.startswith('\t'):
            references = re.findall(r'\$\(([^)]*)\)', line)
            if 'ARGS' in references:
                # CMake's top-level test helper is not a compiler object rule.
                # Its optional arguments are neither expanded nor executed here.
                ctest = cmake_path.rsplit('/', 1)[0] + '/ctest'
                _require(top_level_makefile and support is None and rule in {
                    'test: all', 'test: cmake_check_build_system'}
                    and line == '\t' + ctest + ' --force-new-ctest-process $(ARGS)')
                references = [name for name in references if name != 'ARGS']
            _require(all(name in {'CMAKE_COMMAND','CMAKE_SOURCE_DIR','CMAKE_BINARY_DIR','MAKE',
                'COLOR','VERBOSE','EQUALS','MAKESILENT'}
                or re.fullmatch(r'CMAKE_PROGRESS_[0-9]+|(?:C|CXX)_(?:DEFINES|INCLUDES|FLAGS)', name)
                for name in references))
            _require('$' not in re.sub(r'\$\([^)]*\)', '', line))
            if '$(MAKE)' in line:
                # Recursive child calls cannot inject compiler overrides,
                # altered environment precedence or another Makefile.
                _require(re.fullmatch(r'\t\$\(MAKE\) \$\(MAKESILENT\) -f [A-Za-z0-9_./+-]+ [A-Za-z0-9_./+-]+', line) is not None)
                child = line.split(' -f ', 1)[1].split(' ',1)[0]
                _require(child == 'CMakeFiles/Makefile2' or child in files and child.endswith('/build.make'))
            continue
        if line.startswith('include '):
            name = line[len('include '):]
            _require(relative is not None and name in {relative + '/' + n for n in native_files if n != 'build.make'} and name not in includes)
            includes.add(name)
            continue
        if ' = ' in line or line.endswith(' =') or line.endswith('='):
            name, separator, value = line.partition(' =')
            _require(separator)
            value = value.lstrip(' ')
            if name in assignments:
                _require(name not in seen and value == assignments[name])
                seen.add(name)
            else:
                # The generated object lists are inert literal data; only the
                # target's own names are admitted, not arbitrary Make variables.
                target = relative.rsplit('/',1)[1][:-4] if relative else None
                # CMake3.31.6 CreateMakeVariable encodes these punctuation
                # characters in noncolliding target identifiers. Unexpected
                # collision suffixes remain outside this supported grammar.
                variable = (target.replace('.', '_').replace('-', '__').replace('+', '___')
                            if target is not None else None)
                _require(variable is not None and name in {variable + '_OBJECTS', variable + '_EXTERNAL_OBJECTS'}
                    and '$' not in value and not any(c in value for c in ';#`'))
            continue
        if line.startswith('.'):
            _require(line.split(':',1)[0].strip() in {'.PHONY','.SUFFIXES','.DELETE_ON_ERROR','.NOTPARALLEL'})
        _require(':' in line and '$' not in line.replace('$(VERBOSE).SILENT:', '')
                 and not any(c in line for c in '=;`') and not line.startswith((' ', 'override ', 'export ')))
        rule = line
    _require(seen == set(assignments) and includes == (
        {relative + '/' + n for n in native_files if n != 'build.make'} if relative else set()))
    if relative is None:
        return
    for name in (('depend.make', 'compiler_depend.make') if compiled else ('compiler_depend.make',)):
        dependency = files[relative + '/' + name].decode('utf-8','strict')
        for line in re.sub(r'\\\n[ \t]*', ' ', dependency).splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            # Included dependency data may contain ordinary prerequisites and
            # their empty phony rules. Make special targets, pattern rules,
            # double-colon rules and inline recipes can change execution.
            _require(line.count(':') == 1 and not any(c in line for c in '$=;`\0%#\\')
                and not line.startswith(('\t',' ')))
            target, prerequisites = line.split(':')
            _require(re.fullmatch(r'[A-Za-z0-9_/+-][A-Za-z0-9_./+-]*', target) is not None
                and all(re.fullmatch(r'[A-Za-z0-9_./+-]+', item) is not None
                        for item in prerequisites.split()))
    progress = files[relative + '/progress.make'].decode('utf-8','strict')
    progress_names = set()
    for line in progress.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'(CMAKE_PROGRESS_[0-9]+) = ?([0-9]*)', line)
        _require(match is not None and match[1] not in progress_names)
        progress_names.add(match[1])


def _recipes(raw, flags, build, target_directory):
    text = raw.decode('utf-8', 'strict')
    _require(text.startswith('# CMAKE generated file: DO NOT EDIT!\n') and '\0' not in text)
    rule, result = None, []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('\t'):
            # Only object compile rules. Preprocess/assembly/link/custom steps
            # remain separate; unsupported object rules cause a missing context.
            if rule is None or not rule.endswith('.o'):
                continue
            recipe = line[1:]
            if recipe.startswith('@$(CMAKE_COMMAND) -E cmake_echo_color '):
                continue
            command = _expand_variables(recipe, flags)
            cwd = build
            if command.startswith('cd '):
                prefix, separator, command = command.partition(' && ')
                _require(separator and prefix == 'cd ' + target_directory)
                cwd = target_directory
            argv = _shell_arguments(command)
            _require('-c' in argv)
            result.append((rule, number, recipe, cwd, argv))
        elif line and not line.startswith('#'):
            if ': ' in line:
                rule = line.split(': ', 1)[0]
                _require(not rule.startswith(' ') and '\\' not in rule)
            else:
                rule = None
    return result


def _exported_argument_candidates(argv, native_rule):
    # CMake3.31's GNU object rule appends this exact generator segment to
    # FLAGS. Remove only one matching segment; preserve user-specified -MD,
    # -MF/-MT/-MQ and their original order, including legitimate repetitions.
    _require(argv.count('-o') == 1 and argv.index('-o') + 1 < len(argv))
    obj = argv[argv.index('-o') + 1]
    segment = ['-MD', '-MT', native_rule, '-MF', obj + '.d']
    return [argv[:i] + argv[i + len(segment):]
        for i in range(len(argv) - len(segment) + 1) if argv[i:i + len(segment)] == segment]


def _configured_native_commands(raw, fileapi_raw, database, targets, **kwargs):
    _require(isinstance(raw, bytes) and 0 < len(raw) <= STREAM_LIMIT)
    membership = configured_target_membership(fileapi_raw, database, targets, **kwargs)
    fileapi = _json(fileapi_raw)
    native = _json(raw)
    _require(raw == _canonical(native))
    _require(isinstance(native, dict) and set(native) == {'schema', 'fileapi_capture_sha256',
        'database_sha256', 'cache_sha256', 'source_root', 'build_root', 'files'}
        and native['schema'] == CAPTURE_SCHEMA and native['fileapi_capture_sha256'] == _sha(fileapi_raw)
        and native['database_sha256'] == _sha(database)
        and native['cache_sha256'] == membership['configuration_cache_sha256']
        and native['source_root'] == membership['source_root'] and native['build_root'] == membership['build_root'])
    files = _decode_files(native)
    _require(sum(map(len, files.values())) + sum(map(len, _decode_files(fileapi).values())) <= RAW_LIMIT)
    build, directories = membership['build_root'], _target_directories(fileapi, membership)
    required = {r['relative'] + '/' + name for r in directories.values()
                for name in (NATIVE_MAKE_FILES if r['compiled'] else UTILITY_MAKE_FILES)} | set(PARENT_MAKE_FILES)
    _require(required <= set(files))
    for name in files:
        _path(name, build)
        _require(name in required or (name.endswith('.rsp') and name.rsplit('/', 1)[0] in {r['relative'] for r in directories.values()}))
    contexts, matched, outputs = [], set(), set()
    for name in PARENT_MAKE_FILES:
        _make_environment(files[name], files, None, membership['source_root'], build,
            kwargs.get('cmake_path','/usr/local/bin/cmake'), top_level_makefile=name == 'Makefile')
    for target_id, directory in directories.items():
        _make_environment(files[directory['relative'] + '/build.make'], files, directory['support'],
            membership['source_root'], build, kwargs.get('cmake_path','/usr/local/bin/cmake'), compiled=directory['compiled'])
        if not directory['compiled']:
            continue
        flags = _flags(files[directory['relative'] + '/flags.make'])
        candidates = [c for c in membership['contexts'] if c['target_id'] == target_id]
        for rule, line, recipe, cwd, literal in _recipes(files[directory['relative'] + '/build.make'], flags, build, directory['directory']):
            argv, responses = _expand_response(literal, files, cwd, build)
            _require(argv.count('-c') == 1 and argv.count('-o') == 1
                and argv.index('-c') + 1 < len(argv) and argv.index('-o') + 1 < len(argv))
            source = argv[argv.index('-c') + 1]
            possible = [c for c in candidates if c['file'] == source]
            _require(len(possible) == 1)
            context = possible[0]
            key = (target_id, context['source_index'], context['compile_group_index'])
            _require(key not in matched and argv[0] == membership['compiler_bindings'][context['language']]['path'])
            _require(all(isinstance(a, str) and len(a) <= 16384 and not any(ord(c) < 32 for c in a) for a in argv))
            output = _path(argv[argv.index('-o') + 1], cwd) if not argv[argv.index('-o') + 1].startswith('/') else _path(argv[argv.index('-o') + 1], build)
            _require(_path(rule, build) == output and output.startswith(directory['support'] + '/') and output not in outputs)
            identity = {**context, 'directory': cwd, 'arguments': argv, 'literal_arguments': literal,
                'response_files': responses, 'output_path': output, 'native_rule': rule,
                'native_recipe': recipe, 'native_recipe_line': line,
                'native_build_make_sha256': _sha(files[directory['relative'] + '/build.make']),
                'native_flags_make_sha256': _sha(files[directory['relative'] + '/flags.make'])}
            contexts.append({'index': len(contexts), 'context_id': _sha(_canonical(identity)), **identity})
            matched.add(key); outputs.add(output)
    _require(len(contexts) == membership['configured_context_count'])
    # Every existing exported command must agree with its own native object
    # rule; only the generator's dependency switches are absent from the DB.
    represented = set()
    for row in _json(database):
        argv = row.get('arguments')
        if 'command' in row:
            parsed = _shell_arguments(row['command'])
            _require(argv is None or argv == parsed)
            argv = parsed
        _require(isinstance(argv, list))
        argv, _ = _expand_response(argv, files, row['directory'], build)
        candidates = [c for c in contexts if c['file'] == row['file'] and c['directory'] == row['directory']
                      and argv in _exported_argument_candidates(c['arguments'], c['native_rule'])]
        _require(len(candidates) == 1 and candidates[0]['context_id'] not in represented)
        if 'output' in row:
            # CMake's output metadata is top-build relative, while its -o
            # operand is relative to the target's actual compile directory.
            _require(candidates[0]['output_path'] in {
                _path(row['output'], row['directory']), _path(row['output'], build)})
        represented.add(candidates[0]['context_id'])
    analysis_database = _canonical([{'directory': c['directory'], 'file': c['file'],
        'arguments': c['arguments'], 'output': c['output_path']} for c in contexts])
    _require(0 < len(analysis_database) <= RAW_LIMIT)
    result = {'schema': PLAN_SCHEMA, 'native_capture_sha256': _sha(raw),
        'fileapi_capture_sha256': _sha(fileapi_raw), 'original_database_sha256': _sha(database),
        'configuration_cache_sha256': membership['configuration_cache_sha256'],
        'source_population_sha256': membership['source_population_sha256'],
        'native_file_population_sha256': _sha(_canonical({n: _sha(v) for n, v in sorted(files.items())})),
        'contexts': contexts, 'context_count': len(contexts),
        'context_membership_sha256': _sha(_canonical([c['context_id'] for c in contexts])),
        'original_database_context_count': len(represented),
        'omitted_database_context_count': len(contexts) - len(represented),
        'analysis_database': base64.b64encode(analysis_database).decode('ascii'),
        'analysis_database_sha256': _sha(analysis_database),
        'context_argv_binding_verified': True, 'binding_scope': 'generated_configured_object_rules',
        'execution_authorized': False, 'analysis_executed': False,
        'analyzer_header_coverage_verified': False, 'full_project_qualified': False}
    _require(len(_canonical(result)) <= STREAM_LIMIT)
    return result


def configured_native_commands(raw, fileapi_raw, database, targets, **kwargs):
    """Reconstruct all enabled model contexts; never trust producer booleans."""
    try:
        return _configured_native_commands(raw, fileapi_raw, database, targets, **kwargs)
    except (KeyError, TypeError, IndexError, RecursionError, AttributeError, UnicodeError) as exc:
        raise ValueError('worker_native_command_plan_invalid') from exc


def validate_native_plan_freeze(before, after, fileapi_raw, database, targets, **kwargs):
    """Admit only inert dependency evolution; freeze every exact command input."""
    first = configured_native_commands(before, fileapi_raw, database, targets, **kwargs)
    last = configured_native_commands(after, fileapi_raw, database, targets, **kwargs)
    old_files, new_files = _decode_files(_json(before)), _decode_files(_json(after))
    _require(set(old_files) == set(new_files))
    changed = sorted(name for name in old_files if old_files[name] != new_files[name])
    _require(all(name.endswith(('/depend.make', '/compiler_depend.make')) for name in changed))
    _require(first['contexts'] == last['contexts'] and first['analysis_database'] == last['analysis_database']
        and first['original_database_sha256'] == last['original_database_sha256'])
    # Both complete populations were independently parsed, including changed
    # dependency files. No compiler-variable overrides or Make functions pass.
    return {'before_capture_sha256': _sha(before), 'after_capture_sha256': _sha(after),
        'before_population_sha256': first['native_file_population_sha256'],
        'after_population_sha256': last['native_file_population_sha256'],
        'validated_dependency_changes': changed, 'exact_command_inputs_unchanged': True}
