"""One trusted owned CMake control; no arbitrary project support or binary run."""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import time
import uuid

EXPECTED = {
    'CMakeLists.txt': '833f2ef9c9aacb357d1c1fc846b2c3441f4c28824b8db0cc2e738a51afc25761',
    'config.h.in': '58e2516abedf3eb89a38b7650972f629a77e6fb446824175995441b5fa387dd3',
    'hidden.c': '6763e8385724114002682a1aba35fa42174424604ee26d35d30c9cba8402f73e',
    'include/active.h': '2ee290092717e13b516897337a6a14770bb44a441ef70f8ddf1d37584f082fcd',
    'main.c': '7091567002ce7a66f59621651d398d1d9e47bfd018594f068312230b30783e78',
}
PATH = '/usr/local/bin:/usr/bin:/bin'
RAW_LIMIT = 1024 * 1024
RSS_LIMIT = 2 * 1024 * 1024 * 1024
AS_LIMIT = 1024 * 1024 * 1024
WALL_SECONDS = 120


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def stable(root, relative, limit=RAW_LIMIT):
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, 'path_escape')
    path = root / rel
    require(path.resolve().is_relative_to(root.resolve()), 'path_escape')
    require(not any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)), 'symlink_rejected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'file_type_or_size')
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'file_changed')
        return raw
    finally:
        os.close(fd)


def source_binding(source):
    require({p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(EXPECTED), 'owned_source_population')
    result = {}
    for name, expected in EXPECTED.items():
        raw = stable(source, name, 8192)
        require(sha(raw) == expected, 'owned_source_digest')
        result[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return result


def validate_generated(raw):
    require(raw == b'#define CONFIG_SENTINEL 23\n', 'generated_exact_bytes')
    return {'bytes': len(raw), 'sha256': sha(raw)}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def parse_json(raw):
    def invalid(value):
        raise ValueError('nonfinite_json')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique_pairs, parse_constant=invalid)


def reply_read(reply, name, captured, budget=None):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+\.json', name) is not None and not name.startswith('.'), 'reply_reference_path')
    raw = stable(reply, name)
    require(sum(x['bytes'] for x in captured.values()) + (0 if name in captured else len(raw)) <= RAW_LIMIT, 'reply_population_cap')
    if budget is not None and name not in captured:
        require(budget[0] + len(raw) <= RAW_LIMIT, 'control_raw_cap')
        budget[0] += len(raw)
    captured[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return parse_json(raw)


def child_limits():
    os.setsid()
    for kind, cap in [(resource.RLIMIT_CORE, 0), (resource.RLIMIT_AS, AS_LIMIT), (resource.RLIMIT_CPU, WALL_SECONDS)]:
        inherited = [value for value in resource.getrlimit(kind) if value != resource.RLIM_INFINITY]
        effective = min([cap, *inherited])
        resource.setrlimit(kind, (effective, effective))
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, available[:2])
    # Do not set RLIMIT_FSIZE to the log cap: compiler artifacts are not logs.


def group_rss(group):
    total = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group:
                total += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
        except (FileNotFoundError, ProcessLookupError):
            continue
    return total


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(argv, label, out, env, deadline, receipts, usage):
    require(time.monotonic() < deadline, 'control_wall_deadline')
    started = now()
    begin = time.monotonic()
    process = subprocess.Popen(argv, cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=child_limits)
    selector = selectors.DefaultSelector()
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    for name in streams:
        selector.register(getattr(process, name), selectors.EVENT_READ, name)
    error = None
    peak = 0
    try:
        while selector.get_map():
            peak = max(peak, group_rss(process.pid))
            require(peak <= RSS_LIMIT, 'control_group_memory_cap')
            require(time.monotonic() < deadline, 'control_wall_deadline')
            for key, _ in selector.select(0.025):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                require(usage[0] + len(chunk) <= RAW_LIMIT, 'control_raw_cap')
                usage[0] += len(chunk)
                streams[key.data].extend(chunk)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as exc:
        error = type(exc).__name__ + ':' + str(exc)
        kill_group(process)
        process.wait(timeout=3)
        raise
    finally:
        selector.close()
        for name in streams:
            pipe = getattr(process, name)
            if not pipe.closed:
                pipe.close()
        receipt = {'label': label, 'argv': argv, 'cwd': str(out), 'started_at_utc': started, 'ended_at_utc': now(), 'elapsed_seconds': time.monotonic() - begin, 'exit_code': process.returncode, 'pid': process.pid, 'sampled_group_rss_peak_bytes': peak, 'runner_error': error, 'complete_capture': error is None}
        for name, raw in streams.items():
            target = out / (label + '.' + name)
            target.write_bytes(raw)
            receipt[name] = {'path': str(target), 'bytes': len(raw), 'sha256': sha(raw)}
        receipts.append(receipt)
    require(process.returncode == 0, label + '_native_exit')
    return bytes(streams['stdout']), bytes(streams['stderr'])


def validate_hidden(target, index_target, source, build):
    require(target['name'] == index_target['name'] == 'hidden' and target['id'] == index_target['id'], 'target_context_identity')
    candidates = [(i, value) for i, value in enumerate(target['sources']) if value['path'] == 'hidden.c']
    require(len(candidates) == 1, 'hidden_source_membership')
    i, member = candidates[0]
    require(member.get('isGenerated', False) is False, 'hidden_source_origin')
    group = target['compileGroups'][member['compileGroupIndex']]
    require(group['sourceIndexes'] == [i] and group['language'] == 'C', 'hidden_compile_group')
    require(group.get('languageStandard', {}).get('standard') == '11', 'hidden_language_standard')
    defines = [value['define'] for value in group.get('defines', [])]
    require(len(defines) == 2 and set(defines) == {'SOURCE_SENTINEL=19', 'TARGET_SENTINEL=17'}, 'hidden_defines')
    includes = [value['path'] for value in group.get('includes', [])]
    require(includes == [str(source / 'include'), str(build / 'generated')], 'hidden_include_order')
    require(all(not value.get('isSystem', False) for value in group['includes']), 'hidden_include_kind')
    flags = [token for value in group.get('compileCommandFragments', []) for token in shlex.split(value['fragment'], posix=True)]
    # These three independent owned flags commute. Retain both orders; this
    # deliberately does not certify general command-fragment reconstruction.
    require(len(flags) == 3 and set(flags) == {'-g', '-Wextra', '-std=gnu11'}, 'hidden_control_flags')
    return {'source': str(source / 'hidden.c'), 'defines': defines, 'includes': includes, 'flags': flags, 'target_id': target['id'], 'source_index': i, 'compile_group_index': member['compileGroupIndex']}


def validate_native_command(native, settings, compiler):
    obj = 'CMakeFiles/hidden.dir/hidden.c.o'
    # Only these two distinct owned macros commute. FileAPI ordering does not
    # promise native command ordering. Keep both actual orders, and still bind
    # compiler, exact two definitions, ordered includes and the entire rule tail.
    require(len(settings['defines']) == 2 and set(settings['defines']) == {'SOURCE_SENTINEL=19', 'TARGET_SENTINEL=17'}, 'hidden_defines')
    native_defines = native[1:3]
    require(len(native_defines) == 2 and set(native_defines) == {'-DSOURCE_SENTINEL=19', '-DTARGET_SENTINEL=17'}, 'owned_native_defines')
    prefix = [compiler, *native_defines, *['-I' + value for value in settings['includes']]]
    native_flags = native[len(prefix):native.index('-MD')]
    require(len(native_flags) == 3 and set(native_flags) == set(settings['flags']), 'owned_native_flag_population')
    expected = [*prefix, *native_flags, '-MD', '-MT', obj, '-MF', obj + '.d', '-o', obj, '-c', settings['source']]
    require(native == expected, 'owned_native_settings_or_rule_tail_mismatch')
    return native_flags


def negative_control(name, function):
    try:
        function()
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return {'case': name, 'rejected': True, 'reason': str(error)}
    raise ValueError('negative_false_accept:' + name)


def execute(source, out):
    started = now()
    begin = time.monotonic()
    deadline = begin + WALL_SECONDS
    receipts, usage = [], [0]
    summary = {'schema': 'nico.fileapi-owned-control.v1', 'operation_id': str(uuid.uuid4()), 'started_at_utc': started, 'status': 'PREPARED', 'source': str(source), 'output': str(out), 'scope': 'Trusted owned native control only; no qualification toolchain parity or mandatory-header gate credit.', 'limits': {'wall_seconds': WALL_SECONDS, 'cpu_affinity_max': 2, 'per_process_AS_bytes': AS_LIMIT, 'sampled_group_rss_bytes': RSS_LIMIT, 'combined_raw_bytes': RAW_LIMIT}, 'receipts': receipts, 'HOME_present': False, 'fixture_executable_run': False, 'FileAPI_exact_argv_oracle': False}
    out.mkdir(parents=True, exist_ok=False)
    journal = out / 'result.json'
    def checkpoint():
        journal.write_text(json.dumps(summary, indent=2) + '\n')
    checkpoint()
    try:
        summary['source_binding_before'] = source_binding(source)
        paths = {name: shutil.which(name, path=PATH) for name in ['cmake', 'gcc', 'make']}
        missing = [name for name, value in paths.items() if value is None]
        if missing:
            summary.update(status='NOT_RUN', missing_existing_tools=missing)
            return 2
        tools = {name: str(Path(value).resolve(strict=True)) for name, value in paths.items()}
        summary['tools'] = {name: {'path': value, 'sha256': sha(Path(value).read_bytes())} for name, value in tools.items()}
        scratch = out / 'tmp'
        scratch.mkdir()
        env = {'PATH': PATH, 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(scratch)}
        for name, value in tools.items():
            stdout, stderr = run([value, '--version'], name + '-version', out, env, deadline, receipts, usage)
            summary['tools'][name]['version_first_line'] = stdout.decode('utf-8', 'strict').splitlines()[0]
        build = out / 'build'
        query = build / '.cmake/api/v1/query/client-nico-export-control'
        query.mkdir(parents=True)
        for name in ['codemodel-v2', 'toolchains-v1']:
            (query / name).write_bytes(b'')
        summary['query_binding'] = {name: sha(b'') for name in ['codemodel-v2', 'toolchains-v1']}
        summary['status'] = 'SUBMITTING_CONFIGURE'
        checkpoint()
        run([tools['cmake'], '-S', str(source), '-B', str(build), '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_C_COMPILER=' + tools['gcc'], '-DCMAKE_MAKE_PROGRAM=' + tools['make']], 'configure', out, env, deadline, receipts, usage)
        before_db = stable(build, 'compile_commands.json')
        (out / 'compile-commands-before.json').write_bytes(before_db)
        db = parse_json(before_db)
        require(len(db) == 1 and db[0]['file'] == str(source / 'main.c') and db[0]['directory'] == str(build), 'exported_visible_only')
        summary['original_DB_before_sha256'] = sha(before_db)
        captured = {}
        reply = build / '.cmake/api/v1/reply'
        indexes = sorted(reply.glob('index-*.json'))
        require(len(indexes) == 1, 'fresh_single_reply_index')
        index = reply_read(reply, indexes[0].name, captured, usage)
        client = index['reply']['client-nico-export-control']
        codemodel = reply_read(reply, client['codemodel-v2']['jsonFile'], captured, usage)
        toolchains = reply_read(reply, client['toolchains-v1']['jsonFile'], captured, usage)
        require(codemodel['kind'] == 'codemodel' and codemodel['version']['major'] == 2, 'codemodel_version')
        require(toolchains['kind'] == 'toolchains' and toolchains['version']['major'] == 1, 'toolchains_version')
        require(codemodel['paths'] == {'source': str(source), 'build': str(build)}, 'codemodel_roots')
        configs = codemodel['configurations']
        require(len(configs) == 1 and configs[0]['name'] == 'Debug', 'codemodel_configuration')
        refs = configs[0]['targets']
        require(len(refs) == 2 and {value['name'] for value in refs} == {'hidden', 'visible'} and len({value['id'] for value in refs}) == 2, 'enabled_target_population')
        target_ref = next(value for value in refs if value['name'] == 'hidden')
        hidden = reply_read(reply, target_ref['jsonFile'], captured, usage)
        settings = validate_hidden(hidden, target_ref, source, build)
        c_tools = [value for value in toolchains['toolchains'] if value['language'] == 'C']
        require(len(c_tools) == 1 and c_tools[0]['compiler']['path'] == tools['gcc'], 'toolchain_identity')
        generated = stable(build, 'generated/config.h', 8192)
        summary['generated_binding'] = validate_generated(generated)
        summary['status'] = 'SUBMITTING_TRUSTED_VERBOSE_BUILD'
        checkpoint()
        stdout, stderr = run([tools['cmake'], '--build', str(build), '--parallel', '2', '--verbose'], 'build', out, env, deadline, receipts, usage)
        commands = []
        for line in stdout.decode('utf-8', 'strict').splitlines():
            tokens = shlex.split(line, posix=True)
            if tokens and tokens[0] == tools['gcc'] and '-c' in tokens:
                commands.append(tokens)
        require(len(commands) == 2, 'native_compile_command_population')
        require({tokens[tokens.index('-c') + 1] for tokens in commands} == {str(source / 'hidden.c'), str(source / 'main.c')}, 'native_source_population')
        native = next(tokens for tokens in commands if tokens[tokens.index('-c') + 1] == settings['source'])
        native_flags = validate_native_command(native, settings, tools['gcc'])
        after_db = stable(build, 'compile_commands.json')
        require(after_db == before_db, 'original_DB_changed')
        (out / 'compile-commands-after.json').write_bytes(after_db)
        require(source_binding(source) == summary['source_binding_before'], 'owned_source_changed')
        wrong_identity = copy.deepcopy(hidden); wrong_identity['id'] += '-changed'
        wrong_path = copy.deepcopy(hidden); wrong_path['sources'][settings['source_index']]['path'] = '../hidden.c'
        tampered_source = out / 'controls/tampered-source'
        for name in EXPECTED:
            destination = tampered_source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(stable(source, name, 8192))
        (tampered_source / 'hidden.c').write_bytes(stable(tampered_source, 'hidden.c', 8192) + b' ')
        summary['negative_controls'] = [
            negative_control('wrong_source_digest', lambda: source_binding(tampered_source)),
            negative_control('wrong_generated_bytes', lambda: validate_generated(generated + b' ')),
            negative_control('escaped_reply_reference', lambda: reply_read(reply, '../foreign.json', {})),
            negative_control('wrong_target_context_identity', lambda: validate_hidden(wrong_identity, target_ref, source, build)),
            negative_control('wrong_source_context_path', lambda: validate_hidden(wrong_path, target_ref, source, build)),
        ]
        summary.update(status='VERIFIED_OWNED_MECHANISM_ONLY', native_hidden_argv=native, native_compile_commands=commands, FileAPI_hidden_settings=settings, native_flag_order=native_flags, FileAPI_flag_order_matches_native=(native_flags == settings['flags']), flags_comparison_scope='Exact population of three independent owned flags; ordering preserved separately, no general argv reconstruction claim.', reply_bindings=captured, original_DB_after_sha256=sha(after_db), original_DB_bytes_unchanged=True, gate_promoted=False)
        return 0
    except BaseException as error:
        summary.update(status='FAILED', error_type=type(error).__name__, reason=str(error), gate_promoted=False)
        return 1
    finally:
        summary.update(ended_at_utc=now(), elapsed_seconds=time.monotonic() - begin, combined_native_and_FileAPI_raw_bytes=usage[0], native_raw_output_bytes=sum(r[k]['bytes'] for r in receipts for k in ['stdout', 'stderr']))
        checkpoint()
        print(json.dumps({'path': str(journal), 'sha256': sha(journal.read_bytes()), 'status': summary['status'], 'elapsed_seconds': summary['elapsed_seconds']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, default=Path(__file__).parent / 'source')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(execute(args.source_dir.resolve(strict=True), args.output_dir.absolute()))
