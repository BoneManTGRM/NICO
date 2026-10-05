"""Existing-CI owned mechanism trial, with bounded primary bytes in JUnit."""
from __future__ import annotations

import base64
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time

import pytest

RUNNER_SHA = '66aa2459c0c5eb337dc3cf85d458f8d8b3e1b8ef7a8adacf9cd63dd4ef7bbfc5'
SOURCE_SHAS = {
    'CMakeLists.txt': '833f2ef9c9aacb357d1c1fc846b2c3441f4c28824b8db0cc2e738a51afc25761',
    'config.h.in': '58e2516abedf3eb89a38b7650972f629a77e6fb446824175995441b5fa387dd3',
    'hidden.c': '6763e8385724114002682a1aba35fa42174424604ee26d35d30c9cba8402f73e',
    'include/active.h': '2ee290092717e13b516897337a6a14770bb44a441ef70f8ddf1d37584f082fcd',
    'main.c': '7091567002ce7a66f59621651d398d1d9e47bfd018594f068312230b30783e78',
}
LABELS = ['cmake-version', 'gcc-version', 'make-version', 'configure', 'build']
NEGATIVES = ['wrong_source_digest', 'wrong_generated_bytes', 'escaped_reply_reference',
             'wrong_target_context_identity', 'wrong_source_context_path']
PRIMARY_LIMIT = 1024 * 1024
OUTER_OUTPUT_LIMIT = 64 * 1024
OUTER_SECONDS = 125
GROUP_RSS_LIMIT = 2 * 1024 * 1024 * 1024


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _read(root, name, limit=PRIMARY_LIMIT):
    relative = Path(name)
    _require(not relative.is_absolute() and '..' not in relative.parts, 'primary_path_escape')
    path = root / relative
    _require(path.resolve().is_relative_to(root.resolve()), 'primary_path_escape')
    _require(not any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)), 'primary_symlink')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'primary_type_or_size')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        fields = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        _require(len(raw) == before.st_size and fields(before) == fields(after), 'primary_changed')
        return bytes(raw)
    finally:
        os.close(descriptor)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('nonfinite_json')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=nonfinite)


def _process_info(pid):
    fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]),
            'group': int(fields[2]), 'session': int(fields[3]),
            'start_ticks': int(fields[19]), 'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE')}


def _scan(root_pid, tracked):
    snapshot = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            value = _process_info(int(path.parent.name))
            snapshot[value['pid']] = value
        except (FileNotFoundError, ProcessLookupError):
            continue
    # Never rediscover ownership merely from a reused numeric root PID.
    owned = {pid for (pid, ticks) in tracked
             if pid in snapshot and snapshot[pid]['start_ticks'] == ticks}
    while True:
        added = {pid for pid, value in snapshot.items() if value['ppid'] in owned}
        if added <= owned:
            break
        owned.update(added)
    for pid in owned:
        if pid in snapshot:
            value = snapshot[pid]
            tracked[(pid, value['start_ticks'])] = value
    live = []
    for identity in tracked:
        value = snapshot.get(identity[0])
        if value and value['start_ticks'] == identity[1] and value['state'] not in {'Z', 'X'}:
            live.append(value)
    return live


def _limits():
    for kind, cap in [(resource.RLIMIT_CORE, 0), (resource.RLIMIT_AS, 1024 * 1024 * 1024),
                      (resource.RLIMIT_CPU, 120)]:
        existing = [v for v in resource.getrlimit(kind) if v != resource.RLIM_INFINITY]
        effective = min([cap, *existing])
        resource.setrlimit(kind, (effective, effective))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])


def _reap_owned_child(process):
    """Bounded direct-child fallback, independent of /proc and process groups."""
    events, errors = [], []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if process.poll() is None:
                process.send_signal(sig)
                events.append({'pid': process.pid, 'signal': int(sig)})
            process.wait(timeout=0.5)
        except ProcessLookupError:
            pass
        except Exception as error:
            errors.append(type(error).__name__)
    return {'signals': events, 'error_types': sorted(set(errors)),
            'reaped': process.poll() is not None}


def _cleanup(process, tracked):
    events, telemetry_errors, group_errors = [], [], []
    deadline = time.monotonic() + 1.5

    def inspected_live():
        try:
            return _scan(process.pid, tracked)
        except Exception as error:
            telemetry_errors.append(type(error).__name__)
            return []

    # Signal only groups discovered from exact owned PID/start identities.
    # An inspection/signaling failure never admits unknown descendants.
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            live = inspected_live()
            groups = {v['group'] for v in live if v['group'] != os.getpgrp()}
            for group in groups:
                try:
                    os.killpg(group, sig)
                    events.append({'group': group, 'signal': int(sig)})
                except ProcessLookupError:
                    continue
                except Exception as error:
                    group_errors.append(type(error).__name__)
            stop = min(deadline, time.monotonic() + 0.5)
            while inspected_live() and time.monotonic() < stop:
                time.sleep(0.025)
    except Exception as error:
        group_errors.append(type(error).__name__)
    finally:
        # The Popen child is ours even when admission, scan or group signaling
        # fails. This runs independently and never kills unknown descendants.
        direct = _reap_owned_child(process)
    remaining = inspected_live()
    return {'signals': events, 'direct_owned_child_signals': direct['signals'],
            'owned_child_reaped': direct['reaped'],
            'direct_child_error_types': direct['error_types'],
            'remaining_owned_identities': remaining,
            'telemetry_error_types': sorted(set(telemetry_errors)),
            'group_error_types': sorted(set(group_errors)),
            'descendant_cleanup_verified': bool(tracked) and direct['reaped']
                and not telemetry_errors and not group_errors and not direct['error_types'] and not remaining}


def _invoke(argv, cwd, env):
    begin = time.monotonic()
    deadline = begin + OUTER_SECONDS
    receipt = {'argv': argv, 'cwd': str(cwd), 'started_at_utc': _utc(),
               'timeout_seconds': OUTER_SECONDS, 'HOME_present': 'HOME' in env,
               'environment_keys': sorted(env), 'native_scope': 'trusted owned trial only'}
    tracked, streams = {}, {'stdout': bytearray(), 'stderr': bytearray()}
    process = None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True, preexec_fn=_limits)
        receipt['pid'] = process.pid
        identity = _process_info(process.pid)
        tracked[(identity['pid'], identity['start_ticks'])] = identity
        receipt['root_process_identity'] = {'pid': identity['pid'], 'start_ticks': identity['start_ticks']}
        for name in streams:
            selector.register(getattr(process, name), selectors.EVENT_READ, name)
        peak = 0
        while selector.get_map():
            live = _scan(process.pid, tracked)
            peak = max(peak, sum(v['rss_bytes'] for v in live))
            _require(peak <= GROUP_RSS_LIMIT, 'outer_group_memory_cap')
            _require(time.monotonic() < deadline, 'outer_timeout')
            for key, _ in selector.select(0.025):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                else:
                    _require(sum(map(len, streams.values())) + len(chunk) <= OUTER_OUTPUT_LIMIT, 'outer_output_cap')
                    streams[key.data].extend(chunk)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        receipt['sampled_descendant_rss_peak_bytes'] = peak
        receipt['complete_outer_capture'] = True
    except BaseException as error:
        receipt.update(error_type=type(error).__name__, reason=str(error), complete_outer_capture=False)
    finally:
        if process is not None:
            try:
                receipt['cleanup'] = _cleanup(process, tracked)
            except BaseException as error:
                receipt['cleanup'] = {'error_type': type(error).__name__, 'reason': str(error)}
            receipt['exit_code'] = process.poll()
        selector.close()
        if process is not None:
            for name in streams:
                pipe = getattr(process, name)
                if not pipe.closed:
                    pipe.close()
        receipt.update(ended_at_utc=_utc(), elapsed_seconds=time.monotonic() - begin,
                       tracked_process_identities=[{'pid': pid, 'start_ticks': ticks} for pid, ticks in tracked])
    return receipt, {name: bytes(raw) for name, raw in streams.items()}


def test_owned_export_off_fileapi_mechanism(tmp_path, record_property):
    """Missing tools and incomplete raw evidence fail; never skip this trial."""
    fixture = Path(__file__).parent / 'fixtures/cpp/fileapi-export-off-owned-control'
    work = tmp_path / 'fileapi-owned-trial'
    work.mkdir()
    trusted = work / 'trusted-input'
    trusted.mkdir()
    native = work / 'native'
    expected_inputs = {'run_fileapi_control.py': RUNNER_SHA,
                       **{'source/' + name: value for name, value in SOURCE_SHAS.items()}}
    primary, rows, faults = {}, [], []
    result, outer = None, None

    def retain(name, root, relative, *, expected=None, required=True):
        row = {'name': name, 'source_path': str(root / relative), 'required': required}
        if expected is not None:
            row['expected_sha256'] = sorted(expected) if isinstance(expected, set) else expected
        try:
            _require(len(primary) < 80, 'primary_file_count_cap')
            raw = _read(root, relative)
            row.update(bytes=len(raw), sha256=_sha(raw))
            allowed = expected if isinstance(expected, set) else {expected}
            _require(expected is None or _sha(raw) in allowed, 'primary_digest_mismatch')
            _require(sum(map(len, primary.values())) + len(raw) <= PRIMARY_LIMIT, 'primary_total_bytes_cap')
            _require(name not in primary, 'primary_duplicate')
            primary[name] = raw
            row['status'] = 'CAPTURED'
        except BaseException as error:
            row.update(status='NOT_CAPTURED', reason=type(error).__name__ + ':' + str(error))
            if required:
                faults.append(name + ':' + row['reason'])
        rows.append(row)
        return primary.get(name)

    def retain_bytes(name, raw):
        _require(name not in primary and len(primary) < 80, 'primary_duplicate_or_count')
        _require(sum(map(len, primary.values())) + len(raw) <= PRIMARY_LIMIT, 'primary_total_bytes_cap')
        primary[name] = raw
        rows.append({'name': name, 'bytes': len(raw), 'sha256': _sha(raw), 'required': True, 'status': 'CAPTURED'})

    try:
        for name, expected in expected_inputs.items():
            raw = retain('input/' + name, fixture, name, expected=expected)
            _require(raw is not None, 'fixed_owned_input_not_admitted')
            target = trusted / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o400)
        retain('input/pytest-adapter.py', Path(__file__).parent, Path(__file__).name)
        interpreter = Path(sys.executable).resolve(strict=True)
        operation = {'purpose': 'Confirm enabled EXPORT_COMPILE_COMMANDS OFF target absent from original DB but present in actual FileAPI; actual native compile settings, not general argv oracle.',
                     'expected_runner_sha256': RUNNER_SHA, 'expected_owned_source_shas': SOURCE_SHAS,
                     'submitted_at_utc': _utc(), 'state': 'SUBMITTING_ONCE',
                     'python_path': str(interpreter), 'python_sha256': _sha(interpreter.read_bytes()),
                     'native_output_directory': str(native), 'qualification_gate_credit': False}
        retain_bytes('operation-before.json', (json.dumps(operation, indent=2) + '\n').encode())
        scratch = work / 'outer-tmp'
        scratch.mkdir()
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(scratch)}
        outer, outputs = _invoke([str(interpreter), '-I', '-S', str(trusted / 'run_fileapi_control.py'),
                                  '--source-dir', str(trusted / 'source'), '--output-dir', str(native)], work, env)
        for name, raw in outputs.items():
            retain_bytes('outer.' + name, raw)
        retain_bytes('outer-receipt.json', (json.dumps(outer, indent=2) + '\n').encode())
        raw = retain('native/result.json', native, 'result.json')
        if raw is not None:
            try:
                result = _json(raw)
            except (ValueError, UnicodeError) as error:
                faults.append('native_result_malformed:' + str(error))
        if not isinstance(result, dict):
            faults.append('native_result_missing_or_malformed')
            result = {}
        references = {}
        for item in result.get('receipts', []):
            _require(item['label'] in LABELS and item['label'] not in references, 'unexpected_native_operation')
            references[item['label']] = item
        complete = result.get('status') == 'VERIFIED_OWNED_MECHANISM_ONLY'
        # Capture admitted fixed filenames even when a killed runner left no
        # final result or only partial receipts. Missing files stay explicit.
        for label in LABELS:
            for stream in ['stdout', 'stderr']:
                ref = references.get(label, {}).get(stream)
                if ref is not None:
                    _require(Path(ref['path']) == native / (label + '.' + stream), 'native_log_path_mismatch')
                retain('native/' + label + '.' + stream, native, label + '.' + stream,
                       expected=ref.get('sha256') if ref else None, required=complete or ref is not None)
        for name in ['compile-commands-before.json', 'compile-commands-after.json']:
            expected = result.get('original_DB_' + ('before' if 'before' in name else 'after') + '_sha256')
            retain('native/' + name, native, name, expected=expected, required=complete)
        retain('native/build/compile_commands.json', native, 'build/compile_commands.json',
               expected=result.get('original_DB_after_sha256'), required=complete)
        retain('native/build/generated/config.h', native, 'build/generated/config.h',
               expected=result.get('generated_binding', {}).get('sha256'), required=complete)
        query = 'build/.cmake/api/v1/query/client-nico-export-control/'
        for name in ['codemodel-v2', 'toolchains-v1']:
            retain('native/' + query + name, native, query + name, expected=_sha(b''), required=complete)
        replies = native / 'build/.cmake/api/v1/reply'
        if replies.exists():
            _require(replies.is_dir() and not replies.is_symlink(), 'reply_directory_type')
            listing = sorted(replies.iterdir())
            _require(len(listing) <= 32, 'reply_file_count_cap')
            for path in listing:
                _require(re.fullmatch(r'[A-Za-z0-9_.-]+\.json', path.name) is not None and not path.name.startswith('.'), 'reply_filename')
                expected = result.get('reply_bindings', {}).get(path.name, {}).get('sha256')
                retain('native/build/.cmake/api/v1/reply/' + path.name, replies, path.name,
                       expected=expected, required=True)
        elif complete:
            faults.append('FileAPI_reply_directory_missing')
        for name in SOURCE_SHAS:
            original = primary['input/source/' + name]
            mutated = original + (b' ' if name == 'hidden.c' else b'')
            # A failed copy/write/control may leave the original public bytes.
            # Both admitted forms are safe to retain; success requires mutation.
            expected = _sha(mutated) if complete else {_sha(original), _sha(mutated)}
            retain('negative/tampered-source/' + name, native, 'controls/tampered-source/' + name,
                   expected=expected, required=complete)
        _require(outer.get('exit_code') == 0 and outer.get('complete_outer_capture') is True, 'runner_outer_failure')
        _require(outer.get('cleanup', {}).get('owned_child_reaped') is True
                 and outer.get('cleanup', {}).get('descendant_cleanup_verified') is True
                 and not outer.get('cleanup', {}).get('signals')
                 and not outer.get('cleanup', {}).get('direct_owned_child_signals')
                 and not outer.get('cleanup', {}).get('remaining_owned_identities')
                 and not outer.get('cleanup', {}).get('error_type'), 'outer_cleanup_unverified')
        _require(complete, 'native_mechanism_not_verified:' + str(result.get('status')))
        _require([r['label'] for r in result['receipts']] == LABELS, 'native_execution_population')
        _require(all(r['exit_code'] == 0 and r['runner_error'] is None and r['complete_capture'] is True for r in result['receipts']), 'native_execution_incomplete')
        _require([r['case'] for r in result['negative_controls']] == NEGATIVES and all(r['rejected'] is True for r in result['negative_controls']), 'negative_control_population')
        _require(result['original_DB_bytes_unchanged'] is True and result['FileAPI_exact_argv_oracle'] is False and result['fixture_executable_run'] is False, 'scope_or_original_DB_contract')
        _require(primary['native/compile-commands-before.json'] == primary['native/compile-commands-after.json'], 'actual_DB_byte_parity')
        _require(not faults, 'primary_evidence_incomplete')
    except BaseException as error:
        faults.append(type(error).__name__ + ':' + str(error))
    finally:
        summary = {'schema': 'nico.fileapi-owned-ci-adapter.v1', 'status': 'FAILED' if faults else 'VERIFIED_OWNED_TRIAL_ONLY',
                   'runner_sha256': RUNNER_SHA, 'native_status': result.get('status') if isinstance(result, dict) else None,
                   'actual_outer_exit': outer.get('exit_code') if isinstance(outer, dict) else None,
                   'actual_operation_id': result.get('operation_id') if isinstance(result, dict) else None,
                   'negative_outcomes': result.get('negative_controls', []) if isinstance(result, dict) else [],
                   'tool_identities': result.get('tools', {}) if isinstance(result, dict) else {},
                   'source_shas': SOURCE_SHAS, 'faults': faults, 'primary_file_count': len(primary),
                   'primary_bytes': sum(map(len, primary.values())), 'required_evidence_complete': not faults,
                   'native_local_preflight_reused_as_success': False, 'general_argv_or_header_qualification_credit': False}
        try:
            manifest = {'schema': 'nico.fileapi-owned-primary-manifest.v1', 'summary': summary,
                        'files': rows, 'archive_exclusion': 'No object files, binaries, libraries, dependency files, build Makefiles, environments or credentials.'}
            manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
            _require(len(manifest_raw) <= 64 * 1024, 'manifest_bytes_cap')
            archive_stream = io.BytesIO()
            with gzip.GzipFile(fileobj=archive_stream, mode='wb', mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode='w') as archive:
                    for name, raw in [*sorted(primary.items()), ('manifest.json', manifest_raw)]:
                        _require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'archive_member_path')
                        info = tarfile.TarInfo(name)
                        info.size = len(raw)
                        info.mode = 0o400
                        info.mtime = info.uid = info.gid = 0
                        archive.addfile(info, io.BytesIO(raw))
            bundle = archive_stream.getvalue()
            _require(len(bundle) <= PRIMARY_LIMIT, 'compressed_archive_bytes_cap')
            with tarfile.open(fileobj=io.BytesIO(bundle), mode='r:gz') as archive:
                expected = {**primary, 'manifest.json': manifest_raw}
                _require(len(archive.getmembers()) == len(expected), 'archive_member_population')
                for member in archive.getmembers():
                    _require(member.isfile() and member.name in expected and archive.extractfile(member).read() == expected[member.name], 'archive_actual_byte_binding')
            record_property('nico_fileapi_manifest_sha256', _sha(manifest_raw))
            record_property('nico_fileapi_archive_sha256', _sha(bundle))
            record_property('nico_fileapi_archive_bytes', str(len(bundle)))
            record_property('nico_fileapi_archive_tar_gz_base64', base64.b64encode(bundle).decode('ascii'))
            record_property('nico_fileapi_summary', json.dumps(summary, sort_keys=True))
        except BaseException as error:
            faults.append('primary_export_failed:' + type(error).__name__)
            fallback = {'schema': 'nico.fileapi-owned-export-error.v1',
                        'status': 'UNVERIFIED', 'required_evidence_complete': False,
                        'error_type': type(error).__name__,
                        'captured_primary_files': len(primary),
                        'general_argv_or_header_qualification_credit': False}
            try:
                record_property('nico_fileapi_export_error', json.dumps(fallback, sort_keys=True))
            except BaseException as property_error:
                faults.append('export_error_property_failed:' + type(property_error).__name__)
    if faults:
        pytest.fail('Owned FileAPI mechanism trial failed; bounded primary bytes retained in JUnit: ' + '; '.join(faults), pytrace=False)
