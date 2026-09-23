"""Inspect immutable sanitizer test binaries, then replay them as a separate UID.

This is an internal host controller. It never executes assessed bytes on the
host or as the analyst UID. Actual child commands and exits are retained; the
controller result is not itself a native test pass. Only declared native tests
with self-contained arguments and immutable loader paths are supported here.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time

ORIGINAL_CTEST_LIMIT = 'Original CTest execution-time binary identity is not established; immutable native-test replays are reported separately.'
from nico.comprehensive_coverage_reconciliation_v1 import COPY_ES
COPY_ES[ORIGINAL_CTEST_LIMIT] = 'La identidad del binario durante las ejecuciones originales de CTest no está establecida; las repeticiones de pruebas nativas con binarios inmutables se informan por separado.'

ROOT = '/work/native-tests'

def runtime_user(group, index):
    uid = 1002 + index + (64 if group == 'undefined' else 0)
    return f'{uid}:{uid}'


PROBE_PROGRAM = r'''
import hashlib, json, os, pathlib, sys
path = sys.argv[1]
status = dict(line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
denied = False
try:
    fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
except PermissionError: denied = True
else: os.close(fd)
with open(path, 'rb') as handle: digest = hashlib.sha256(handle.read(67108865)).hexdigest()
print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(), 'write_denied': denied,
    'binary_sha256': digest, 'no_new_privileges': status['NoNewPrivs'].strip() == '1',
    'capabilities': int(status['CapEff'].strip(), 16),
    'credential_environment_absent': not any(k.startswith(('NICO_', 'GITHUB_', 'ACTIONS_', 'RAILWAY_')) for k in os.environ)}, sort_keys=True))
'''

SETUP_PROGRAM = r'''
import os, pathlib
if os.getuid() != 0 or os.getgid() != 0: raise ValueError('runtime_setup_identity')
root = pathlib.Path('/work/native-tests')
root.mkdir(mode=0o755)
for group in ('address', 'undefined'):
    (root / group).mkdir(mode=0o755)
    (root / (group + '-tmp')).mkdir(mode=0o1777)
    (root / (group + '-tmp')).chmod(0o1777)
print('runtime_snapshot_destination_ready')
'''

SNAPSHOT_PROGRAM = r'''
import hashlib, json, os, pathlib, re, stat, sys
request = json.loads(sys.stdin.buffer.read(65537))
group = request['configuration']
if os.getuid() != 0 or group not in ('address', 'undefined'): raise ValueError('runtime_snapshot_identity')
def read(path):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in pathlib.PurePosixPath(path).parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(pathlib.PurePosixPath(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not 64 <= info.st_size <= 67108864:
                raise ValueError('runtime_binary_type_or_limit')
            data = handle.read(67108865)
        if len(data) > 67108864: raise ValueError('runtime_binary_limit')
        return data
    finally: os.close(fd)
root = pathlib.Path('/work/native-tests') / group
info = root.stat()
if root.is_symlink() or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755:
    raise ValueError('runtime_snapshot_destination')
paths = request['binaries']
if not isinstance(paths, list) or not 1 <= len(paths) <= 32 or paths != sorted(set(paths)):
    raise ValueError('runtime_binary_population')
result = {}
total = 0
for index, source in enumerate(paths):
    if not isinstance(source, str) or not source.startswith('/work/' + group + '/') or not re.fullmatch(r'[A-Za-z0-9_./+-]+', source) or any(p in ('', '.', '..') for p in source.split('/')[1:]):
        raise ValueError('runtime_binary_source')
    data = read(source); total += len(data)
    if total > 134217728 or data[:6] != b'\x7fELF\x02\x01' or data[16:20] not in (b'\x02\x00\x3e\x00', b'\x03\x00\x3e\x00'):
        raise ValueError('runtime_binary_elf_or_budget')
    path = root / ('b' + str(index))
    with path.open('xb') as output: output.write(data)
    path.chmod(0o555)
    result[source] = {'snapshot': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                      'bytes': len(data), 'uid': path.stat().st_uid, 'mode': stat.S_IMODE(path.stat().st_mode)}
root.chmod(0o555)
print(json.dumps(result, sort_keys=True))
'''

VERIFY_PROGRAM = r'''
import hashlib, json, os, pathlib, re, stat, sys
path = sys.argv[1]
if os.getuid() != 0 or re.fullmatch(r'/work/native-tests/(address|undefined)/b[0-9]+', path) is None:
    raise ValueError('runtime_snapshot_verification_path')
parent = pathlib.Path(path).parent
pinfo = parent.stat()
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as handle:
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode) or not 64 <= info.st_size <= 67108864:
        raise ValueError('runtime_snapshot_verification_type')
    data = handle.read(67108865)
if len(data) != info.st_size or parent.is_symlink() or pinfo.st_uid != 0 or stat.S_IMODE(pinfo.st_mode) != 0o555:
    raise ValueError('runtime_snapshot_verification_changed')
print(json.dumps({'snapshot':path, 'sha256':hashlib.sha256(data).hexdigest(),
                  'bytes':len(data), 'uid':info.st_uid, 'mode':stat.S_IMODE(info.st_mode)}, sort_keys=True))
'''


def test_plan(raw, config, group):
    from nico.assessment_cpp_full_project import _json, _discovery
    if group not in {'address', 'undefined'}:
        raise ValueError('worker_native_test_configuration_invalid')
    names = sorted(config['unit_tests'] + config['integration_tests'])
    if not 1 <= len(names) <= 64 or len(names) != len(set(names)):
        raise ValueError('worker_native_test_population_invalid')
    if not set(names) <= set(_discovery(raw)):
        raise ValueError('worker_native_test_discovery_incomplete')
    tests = {row['name']: row for row in _json(raw)['tests']}
    result = []
    for name in names:
        row = tests[name]; argv = row.get('command')
        if (not isinstance(argv, list) or not 1 <= len(argv) <= 32
                or any(not isinstance(a, str) or not a or len(a) > 500 for a in argv)
                or not argv[0].startswith('/work/' + group + '/')
                or re.fullmatch(r'[A-Za-z0-9_./+-]+', argv[0]) is None
                or any(p in {'', '.', '..'} for p in argv[0].split('/')[1:])
                or any(re.fullmatch(r'[A-Za-z0-9_=:+.,-]{1,200}', a) is None for a in argv[1:])):
            raise ValueError('worker_native_test_command_unsupported')
        props = row.get('properties', [])
        if not isinstance(props, list): raise ValueError('worker_native_test_properties_unsupported')
        property_names = [p.get('name') if isinstance(p, dict) else None for p in props]
        if any(not isinstance(name, str) for name in property_names) or len(set(property_names)) != len(property_names):
            raise ValueError('worker_native_test_properties_unsupported')
        for prop in props:
            if not isinstance(prop, dict) or set(prop) != {'name', 'value'}:
                raise ValueError('worker_native_test_properties_unsupported')
            key, value = prop['name'], prop['value']
            if ((key == 'WORKING_DIRECTORY' and value == '/work/' + group)
                    or (key == 'TIMEOUT' and type(value) in {int, float} and value == 30)
                    or (key == 'LABELS' and isinstance(value, list) and all(isinstance(x, str) for x in value))):
                continue
            raise ValueError('worker_native_test_properties_unsupported')
        result.append({'name': name, 'argv': argv})
    if len({row['argv'][0] for row in result}) > 32:
        raise ValueError('worker_native_test_binary_population_invalid')
    return result



def sanitizer_symbols(raw, group):
    """Require actual undefined runtime symbols, not a substring in a symbol name."""
    symbols = []
    for line in raw.splitlines():
        match = re.fullmatch(rb'[ \t]*U[ \t]+([A-Za-z0-9_]+)(?:@[A-Za-z0-9_.]+)?[ \t]*', line)
        if match: symbols.append(match[1])
    if group == 'address':
        return b'__asan_init' in symbols and any(s.startswith(b'__asan_report_') for s in symbols)
    return group == 'undefined' and any(s.startswith(b'__ubsan_handle_') for s in symbols)


def _probe_matches(raw, snapshot, user):
    from nico.assessment_cpp_full_project import _json
    value = _json(raw)
    uid = int(user.split(':')[0])
    expected = {'uid': uid, 'gid': uid, 'write_denied': True,
        'binary_sha256': snapshot['sha256'], 'no_new_privileges': True,
        'capabilities': 0, 'credential_environment_absent': True}
    return (isinstance(value, dict) and value == expected
        and all(type(value[k]) is int for k in ('uid', 'gid', 'capabilities'))
        and all(type(value[k]) is bool for k in ('write_denied', 'no_new_privileges', 'credential_environment_absent')))


def inspect_dynamic_paths(raw):
    """The snapshot is immutable; its loader must not consult assessed outputs."""
    text = raw.decode('utf-8')
    needed_libraries = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)
    if not needed_libraries: return False
    for needed in needed_libraries:
        if re.fullmatch(r'[A-Za-z0-9_.+-]+', needed) is None: return False
    for paths in re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]*)\]', text):
        for path in paths.split(':'):
            if (not path.startswith(('/usr/lib/', '/usr/local/lib', '/lib/'))
                    or '$' in path or any(p in {'', '.', '..'} for p in path.split('/')[1:])):
                return False
    return True


def run_bound_tests(invoke, container, group, discovery, config):
    """Host-only controller; invoke retains the original job deadline/checkpoint."""
    result = {'schema': 'nico.cpp-native-test-binding.v1', 'configuration': group,
        'discovery_sha256': hashlib.sha256(discovery).hexdigest(),
        'snapshot_operation': None, 'snapshots': {}, 'inspections': [], 'tests': [], 'error': None}
    def op(argv, user, *, data=None, runtime=False):
        before = time.monotonic()
        prefix = ['docker', 'exec', '--user=' + user]
        if data is not None: prefix += ['--interactive']
        if runtime:
            prefix += ['--workdir=' + ROOT + '/' + group,
                '--env=HOME=' + ROOT + '/' + group + '-tmp',
                '--env=TMPDIR=' + ROOT + '/' + group + '-tmp']
        value = invoke([*prefix, container, *argv], data=data, max_output=65536, seconds=30)
        return {'invocation': argv, 'user': user, 'exit_code': value['exit_code'],
            'timed_out': value['timed_out'], 'output_truncated': value['output_truncated'],
            'duration_ms': int((time.monotonic() - before) * 1000),
            'output': base64.b64encode(value['output']).decode('ascii'),
            'output_sha256': hashlib.sha256(value['output']).hexdigest()}
    def okay(value):
        return value['exit_code'] == 0 and not value['timed_out'] and not value['output_truncated']
    def parsed(value):
        if not okay(value): raise ValueError('worker_native_test_snapshot_unavailable')
        return json.loads(base64.b64decode(value['output']))
    try:
        plans = test_plan(discovery, config, group)
        binaries = sorted({p['argv'][0] for p in plans})
        payload = json.dumps({'configuration': group, 'binaries': binaries}).encode()
        result['snapshot_operation'] = op(['python3', '-I', '-S', '-c', SNAPSHOT_PROGRAM], '0:0', data=payload)
        result['snapshots'] = parsed(result['snapshot_operation'])
        good = set()
        for source in binaries:
            snapshot = result['snapshots'][source]['snapshot']
            nm = op(['/usr/bin/nm', '-D', '--undefined-only', snapshot], '1001:1001')
            dynamic = op(['/usr/bin/readelf', '-dW', snapshot], '1001:1001')
            result['inspections'].append({'source': source, 'nm': nm, 'dynamic': dynamic})
            symbols = base64.b64decode(nm['output'])
            if (okay(nm) and okay(dynamic) and sanitizer_symbols(symbols, group)
                    and inspect_dynamic_paths(base64.b64decode(dynamic['output']))):
                good.add(source)
        for test_index, plan in enumerate(plans):
            source = plan['argv'][0]; snapshot = result['snapshots'][source]
            row = {'name': plan['name'], 'source': source, 'before': None, 'probe': None, 'execution': None, 'after': None}
            result['tests'].append(row)
            if source not in good: continue
            verify = ['python3', '-I', '-S', '-c', VERIFY_PROGRAM, snapshot['snapshot']]
            row['before'] = op(verify, '0:0')
            if parsed(row['before']) != snapshot: continue
            user = runtime_user(group, test_index)
            row['probe'] = op(['python3', '-I', '-S', '-c', PROBE_PROGRAM, snapshot['snapshot']], user, runtime=True)
            if not okay(row['probe']) or not _probe_matches(base64.b64decode(row['probe']['output']), snapshot, user):
                continue
            row['execution'] = op([snapshot['snapshot'], *plan['argv'][1:]], user, runtime=True)
            # Stop before another test when a native process may still be alive.
            if row['execution']['timed_out'] or row['execution']['output_truncated']:
                result['error'] = 'worker_native_test_interrupted'; break
            row['after'] = op(verify, '0:0')
    except (ValueError, KeyError, TypeError) as exc:
        result['error'] = str(exc) if re.fullmatch(r'worker_native_test_[a-z_]+', str(exc)) else 'worker_native_test_evidence_unavailable'
    return result


def validate_evidence(value, discovery, config, group, *, enclosing_duration_ms=None):
    """Reconstruct binary identity, instrumentation observations and test outcomes."""
    from nico.assessment_cpp_configuration import decode_stream
    from nico.assessment_cpp_full_project import _json
    if enclosing_duration_ms is not None and (type(enclosing_duration_ms) is not int
            or not 0 <= enclosing_duration_ms <= 302000):
        raise ValueError('worker_native_test_duration_invalid')
    observed_duration_ms = 0
    fields = {'schema', 'configuration', 'discovery_sha256', 'snapshot_operation', 'snapshots',
              'inspections', 'tests', 'error'}
    if (not isinstance(value, dict) or set(value) != fields
            or value['schema'] != 'nico.cpp-native-test-binding.v1' or value['configuration'] != group
            or value['discovery_sha256'] != hashlib.sha256(discovery).hexdigest()
            or not isinstance(value['snapshots'], dict) or not isinstance(value['inspections'], list)
            or not isinstance(value['tests'], list) or (value['error'] is not None and
                (not isinstance(value['error'], str) or not re.fullmatch(r'worker_native_test_[a-z_]+', value['error'])))):
        raise ValueError('worker_native_test_evidence_invalid')
    def read(row, argv, user):
        nonlocal observed_duration_ms
        if (not isinstance(row, dict) or set(row) != {'invocation', 'user', 'exit_code', 'timed_out',
                'output_truncated', 'duration_ms', 'output', 'output_sha256'}
                or row['invocation'] != argv or row['user'] != user
                or type(row['exit_code']) is not int or not -255 <= row['exit_code'] <= 255
                or type(row['timed_out']) is not bool or type(row['output_truncated']) is not bool
                or type(row['duration_ms']) is not int or not 0 <= row['duration_ms'] <= 32000):
            raise ValueError('worker_native_test_operation_invalid')
        observed_duration_ms += row['duration_ms']
        # These operations are serial children of the enclosing controller.
        # The same two-millisecond allowance as bounded fuzz preserves rounding
        # without letting individually valid operations hide aggregate runtime.
        if enclosing_duration_ms is not None and observed_duration_ms > enclosing_duration_ms + 2:
            raise ValueError('worker_native_test_duration_contradiction')
        raw = decode_stream(row['output'])
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != row['output_sha256']:
            raise ValueError('worker_native_test_output_mismatch')
        return row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated'], raw
    try:
        plans = test_plan(discovery, config, group)
    except ValueError as exc:
        if (value['error'] != str(exc) or value['snapshot_operation'] is not None
                or value['snapshots'] or value['inspections'] or value['tests']):
            raise ValueError('worker_native_test_unsupported_execution') from None
        return {'required_tests': sorted(config['unit_tests'] + config['integration_tests']),
            'executed_tests': [], 'binary_bound_tests': [], 'passed_tests': [],
            'binary_instrumentation_verified': False, 'tests_passed': False,
            'snapshot_hashes': {}, 'runtime_users': [], 'native_outcomes': [], 'scope': 'unsupported native-test replay', 'error': str(exc)}
    binaries = sorted({p['argv'][0] for p in plans})
    expected_names = [p['name'] for p in plans]
    attempted, bound, passed, outcomes = [], [], [], []
    if value['snapshot_operation'] is None:
        if value['snapshots'] or value['tests'] or value['inspections'] or value['error'] is None:
            raise ValueError('worker_native_test_missing_snapshot')
    else:
        valid, raw = read(value['snapshot_operation'], ['python3', '-I', '-S', '-c', SNAPSHOT_PROGRAM], '0:0')
        if valid:
            if _json(raw) != value['snapshots'] or set(value['snapshots']) != set(binaries):
                raise ValueError('worker_native_test_snapshot_mismatch')
        elif value['snapshots'] or value['tests'] or value['inspections']:
            raise ValueError('worker_native_test_unbound_execution')
    for index, source in enumerate(binaries):
        snap = value['snapshots'].get(source)
        if snap is None: continue
        if (not isinstance(snap, dict) or set(snap) != {'snapshot', 'sha256', 'bytes', 'uid', 'mode'}
                or snap['snapshot'] != ROOT + '/' + group + '/b' + str(index)
                or not isinstance(snap['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', snap['sha256']) is None
                or type(snap['bytes']) is not int or not 64 <= snap['bytes'] <= 67108864
                or type(snap['uid']) is not int or snap['uid'] != 0
                or type(snap['mode']) is not int or snap['mode'] != 0o555):
            raise ValueError('worker_native_test_snapshot_invalid')
    if sum(s['bytes'] for s in value['snapshots'].values()) > 134217728:
        raise ValueError('worker_native_test_snapshot_budget')
    inspected = set(); inspection_sources = []
    for item in value['inspections']:
        if not isinstance(item, dict) or set(item) != {'source', 'nm', 'dynamic'} or item['source'] not in binaries:
            raise ValueError('worker_native_test_inspection_invalid')
        source = item['source']; inspection_sources.append(source)
        snapshot = value['snapshots'][source]['snapshot']
        nm_ok, symbols = read(item['nm'], ['/usr/bin/nm', '-D', '--undefined-only', snapshot], '1001:1001')
        dynamic_ok, dynamic = read(item['dynamic'], ['/usr/bin/readelf', '-dW', snapshot], '1001:1001')
        if nm_ok and dynamic_ok and inspect_dynamic_paths(dynamic) and sanitizer_symbols(symbols, group):
            inspected.add(source)
    if inspection_sources != binaries[:len(inspection_sources)]:
        raise ValueError('worker_native_test_inspection_population')
    if len(value['tests']) > len(plans): raise ValueError('worker_native_test_population_invalid')
    for test_index, (row, plan) in enumerate(zip(value['tests'], plans)):
        source = plan['argv'][0]
        if not isinstance(row, dict) or set(row) != {'name', 'source', 'before', 'probe', 'execution', 'after'} or row['name'] != plan['name'] or row['source'] != source:
            raise ValueError('worker_native_test_population_invalid')
        snapshot = value['snapshots'][source]
        verify = ['python3', '-I', '-S', '-c', VERIFY_PROGRAM, snapshot['snapshot']]
        checks = {}
        for key in ('before', 'after'):
            if row[key] is not None:
                good, raw = read(row[key], verify, '0:0')
                checks[key] = good and _json(raw) == snapshot
        user = runtime_user(group, test_index)
        probe_ok = False
        if row['probe'] is not None:
            good, raw = read(row['probe'], ['python3', '-I', '-S', '-c', PROBE_PROGRAM, snapshot['snapshot']], user)
            probe_ok = good and _probe_matches(raw, snapshot, user)
        if row['execution'] is not None:
            good, _ = read(row['execution'], [snapshot['snapshot'], *plan['argv'][1:]], user)
            attempted.append(row['name'])
            if source in inspected and probe_ok and checks.get('before') and checks.get('after'):
                bound.append(row['name'])
                if good: passed.append(row['name'])
            outcomes.append({k: row['execution'][k] for k in ('exit_code', 'timed_out', 'output_truncated', 'duration_ms')} |
                {'name': row['name'], 'binary_bound': row['name'] in bound, 'runtime_user': user})
    complete = value['error'] is None and bound == expected_names
    return {'required_tests': expected_names, 'executed_tests': attempted, 'binary_bound_tests': bound,
        'passed_tests': passed, 'binary_instrumentation_verified': complete,
        'tests_passed': complete and passed == expected_names,
        'snapshot_hashes': {p: s['sha256'] for p, s in value['snapshots'].items()},
        'runtime_users': [row['runtime_user'] for row in outcomes],
        'configured_runtime_users': [runtime_user(group, i) for i in range(len(plans))],
        'native_outcomes': outcomes,
        'instrumentation_basis': 'undefined sanitizer runtime symbols in the immutable executed binary; not coverage of every code path',
        'scope': 'immutable selected native test binary replays in a snapshot working directory; not original CTest execution-time identity or coverage of every code path'}
