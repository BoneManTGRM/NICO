"""Hash-bound AST helper diagnostic; no native or target execution."""
import argparse
import ast
import base64
import hashlib
import json
import os

import importlib.machinery, importlib.util
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import stat
import sys
import time

sys.dont_write_bytecode = True
MAX_MEMBER = 64 * 1024 * 1024
MAX_RECEIPT = 8 * 1024 * 1024
HERE = Path(__file__).resolve().parent
PACKAGE = HERE / 'cpp-parser-diagnostic-inputs'
EVENTS = []



class _VerifiedBufferLoader(importlib.machinery.SourceFileLoader):
    """Import one already verified source buffer, never cached bytecode."""
    def __init__(self, name, path, raw):
        super().__init__(name, str(path))
        self.verified_raw = raw

    def get_data(self, path):
        if path != self.path:
            raise OSError('verified_source_bytecode_unavailable')
        return self.verified_raw

    def set_data(self, path, data, **kwargs):
        # No bytecode cache or source mutation is part of this diagnostic.
        return None


def _import_verified_buffer(path, raw, label, namespace=None):
    loader = _VerifiedBufferLoader(label, path, raw)
    spec = importlib.util.spec_from_loader(label, loader)
    module = importlib.util.module_from_spec(spec)
    if namespace is not None:
        module.__dict__.update(namespace)
    loader.exec_module(module)
    return module

def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: require(False, 'nonfinite_json'))


def safe_path(name):
    require(isinstance(name, str) and 0 < len(name) <= 240
            and not name.startswith('/') and PurePosixPath(name).as_posix() == name
            and re.fullmatch(r'[A-Za-z0-9._/-]+', name) is not None
            and all(part not in {'', '.', '..'} for part in name.split('/')), 'unsafe_member_path')
    return name


def regular(path, maximum=MAX_MEMBER, expected=None, length=None):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path, 'symlink_or_noncanonical_input')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'member_size_or_type')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and (before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino,
            after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'input_changed_while_reading')
    require(expected is None or sha(raw) == expected, 'input_digest')
    require(length is None or len(raw) == length, 'input_length')
    return raw


def audit(event, args):
    blocked = (event.startswith(('subprocess.', 'socket.', 'http.', 'urllib.'))
               or event in {'os.system', 'os.posix_spawn', 'os.fork', 'os.exec',
                            'ctypes.dlopen', 'os.remove', 'os.unlink', 'os.rename',
                            'os.mkdir', 'os.rmdir', 'os.symlink', 'os.link', 'os.chmod'})
    if event == 'open':
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        blocked = blocked or (isinstance(mode, str) and any(c in mode for c in 'wax+'))
        blocked = blocked or (isinstance(flags, int) and flags &
                             (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        name = args[0]
        if isinstance(name, (str, bytes)):
            name = os.fsdecode(name)
            blocked = blocked or name.startswith(('/work/source/', '/work/build/',
                                                  '/work/analysis/generated-baseline/'))
    if blocked:
        EVENTS.append(event)
        raise RuntimeError('diagnostic_forbidden_event:' + event)


def function(source, name, expected_ast):
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    require(len(matches) == 1, 'actual_function_population')
    node = matches[0]
    require(sha(ast.dump(node, include_attributes=False).encode()) == expected_ast, 'actual_function_ast')
    require(not node.decorator_list and not any(isinstance(child, (ast.Import, ast.ImportFrom,
            ast.Global, ast.Nonlocal)) for child in ast.walk(node)), 'function_scope')
    return node


def scopes(pins):
    sources = {}
    for name, row in pins['sources'].items():
        source = HERE.parent / row['path']
        sources[name] = regular(source, MAX_MEMBER, row['sha256'], row['bytes'])
    path_node = function(sources['source_path'], '_source_path', pins['functions']['source_path'])
    pairs = []
    for name in ('baseline', 'candidate'):
        parser = function(sources[name], '_dependency_populations', pins['functions'][name])
        tree = ast.fix_missing_locations(ast.Module(body=[path_node, parser], type_ignores=[]))
        scope = {'__builtins__': __builtins__, 're': re, 'posixpath': posixpath, 'shlex': shlex,
                 '__name__': 'owned_hash_bound_ast_' + name}
        module = _import_verified_buffer('actual_hash_bound_AST_' + name,
            ast.unparse(tree).encode('utf-8'), 'owned_hash_bound_ast_' + name, scope)
        pairs.append(module._dependency_populations)
    node = function(sources['fixtures'], 'fixtures', pins['functions']['fixtures'])
    scope = {'__builtins__': __builtins__}
    definitions = ast.unparse(ast.Module(body=[node], type_ignores=[])).encode('utf-8')
    module = _import_verified_buffer('actual_hash_bound_owned_fixture_AST', definitions,
        'owned_fixture_definitions', scope)
    return pairs, module.fixtures()


def inputs(root, pins):
    root = root.absolute()
    require(root.resolve(strict=True) == root, 'input_root')
    expected = {safe_path(row['path']): row for row in pins['baseline']['members']}
    require(len(expected) == 32, 'decoded_member_manifest_population')
    actual = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            require(not (Path(directory) / name).is_symlink(), 'decoded_directory_symlink')
        for name in files:
            actual.add((Path(directory) / name).relative_to(root).as_posix())
    require(actual == set(expected), 'decoded_member_population')
    for name, row in expected.items():
        regular(root / name, MAX_MEMBER, row['sha256'], row['bytes'])
    receipt_raw = regular(root / 'cpp-baseline-qualification/receipt.json', MAX_MEMBER,
                          pins['baseline']['receipt_sha256'])
    receipt = decode(receipt_raw)
    source, probe = receipt['source'], receipt['probe']
    require(receipt['producer_source_sha'] == pins['baseline']['producer_source']
            and probe['image_config_digest'] == pins['baseline']['historical_image_id'],
            'historical_producer_image_binding')
    targets = source['targets']
    frozen = pins['frozen_target']
    require(source['repository'] == frozen['repository'] and source['commit_sha'] == frozen['commit']
            and source['tree_sha'] == frozen['tree'] and len(targets) == 3031
            and sha(canonical(targets)) == frozen['target_population_sha256']
            and probe['source_population_sha256'] == frozen['target_population_sha256'], 'frozen_target_binding')
    def artifact(ref, pinned):
        require(ref == pinned, 'actual_artifact_reference')
        return regular(root / 'cpp-baseline-qualification' / safe_path(ref['path']),
                       MAX_MEMBER, ref['sha256'], ref['bytes'])
    compiler_raw = artifact(probe['project_compiler']['artifact'], pins['baseline']['compiler'])
    snapshot_raw = artifact(probe['generated_context']['artifact'], pins['baseline']['snapshot'])
    compiler, snapshot = decode(compiler_raw), decode(snapshot_raw)
    require(len(compiler['records']) == 577 and len(snapshot['files']) == 143
            and len(snapshot['generated_units']) == 42, 'bound_raw_input_population')
    metadata = {}
    captured = 0
    for name, row in snapshot['files'].items():
        body = base64.b64decode(row['base64'], validate=True)
        require(len(body) == row['bytes'] and sha(body) == row['sha256'], 'raw_snapshot_file_binding')
        metadata[name] = {'bytes': row['bytes'], 'sha256': row['sha256']}
        captured += len(body)
    require(metadata == probe['generated_context']['files'] and captured == snapshot['captured_bytes']
            and snapshot['file_population_sha256'] == pins['baseline']['snapshot_population_sha256'],
            'retained_snapshot_metadata_binding')
    # Only these two actual request fields are accessed by the extracted helper.
    request = {'targets': targets, 'generated_files': metadata}
    dependencies = []
    expected_outputs = []
    for index, row in enumerate(compiler['records']):
        if row['dependency_bytes']:
            body = base64.b64decode(row['dependency_bytes'], validate=True)
            require(sha(body) == row['dependency_sha256'], 'raw_dependency_binding')
            dependencies.append((index, body))
            expected_outputs.append((row['source_dependencies'], row['generated_dependencies'],
                                     row['toolchain_dependencies']))
    require(len(dependencies) == 576, 'retained_nonempty_dependency_list_population')
    dummy = base64.b64decode(snapshot['files']['dummy_cxx_source.cpp']['base64'], validate=True)
    require(dummy == b'#error', 'genuine_generated_error_input_changed')
    return request, dependencies, expected_outputs, {
        'decoded_members_verified': 32, 'decoded_member_bytes': sum(row['bytes'] for row in expected.values()),
        'historical_ZIP_reverified_by_this_decoded_transport': False,
        'receipt_sha256': sha(receipt_raw), 'compiler_sha256': sha(compiler_raw),
        'snapshot_sha256': sha(snapshot_raw), 'target_digest_population': 3031,
        'raw_compiler_records': 577, 'snapshot_files': 143, 'generated_units': 42,
        'nonempty_dependency_lists': 576, 'fallback_obligations_executed': 0,
        'snapshot_header_dependencies_verified': snapshot['header_dependencies_verified'],
        'genuine_dummy_error': {'bytes': len(dummy), 'sha256': sha(dummy), 'retained': True}}


def outcome(subject, *args):
    try:
        return {'kind': 'return', 'value': subject(*args)}
    except (ValueError, UnicodeError, TypeError, KeyError) as error:
        return {'kind': 'raise', 'type': type(error).__name__, 'message': str(error)}


def environment(pins):
    require(sys.flags.isolated == 1 and sys.flags.no_site == 1, 'python_not_I_S')
    require(os.getuid() == 1000 and os.getgid() == 1000, 'container_uid_gid')
    cpu = regular('/sys/fs/cgroup/cpu.max', 1024).decode().split()
    memory = regular('/sys/fs/cgroup/memory.max', 1024).decode().strip()
    pids = regular('/sys/fs/cgroup/pids.max', 1024).decode().strip()
    require(len(cpu) == 2 and cpu[0] != 'max' and int(cpu[0]) == 4 * int(cpu[1])
            and memory == '12884901888' and pids == '256', 'fixed_cgroup_limits')
    mounts = [line.split() for line in regular('/proc/' + str(os.getpid()) + '/mountinfo',
                                              1024 * 1024).decode().splitlines()]
    root = [row for row in mounts if row[4] == '/']
    work = [row for row in mounts if row[4] == '/work']
    require(len(root) == 1 and 'ro' in root[0][5].split(',') and len(work) == 1, 'read_only_root_work_mount')
    sep = work[0].index('-')
    options = work[0][5].split(',') + work[0][sep + 3].split(',')
    require(work[0][sep + 1] == 'tmpfs' and all(value in options for value in ['noexec', 'nosuid', 'nodev'])
            and any(value in options for value in ['size=9437184k', 'size=9663676416']), 'fixed_tmpfs_mount')
    identity = decode(regular('/identity/container-identity.json', MAX_RECEIPT))
    require(identity['image_config_id'] == pins['image']['image_config_id']
            and identity['image_archive_sha256'] == pins['image']['tar_sha256']
            and identity['complete_archive_verified'] is True and identity['network'] == 'none'
            and identity['read_only'] is True and identity['user'] == '1000:1000', 'outer_verified_image_binding')
    return {'python': sys.version, 'executable': sys.executable, 'isolated': bool(sys.flags.isolated),
            'no_site': bool(sys.flags.no_site), 'uid': os.getuid(), 'gid': os.getgid(),
            'kernel': list(os.uname()), 'cpu_max': cpu, 'memory_max': memory, 'pids_max': pids,
            'root_read_only': True, 'tmpfs_options': options, 'outer_identity': identity,
            'network_none_verified_by_outer_driver': True}


def controls(before, after, rows):
    require(len(rows) == 41, 'owned_fixture_population')
    checks = []
    for row in rows:
        left = outcome(before, row['raw'], row['request'])
        right = outcome(after, row['raw'], row['request'])
        require(left == right, 'fixture_semantics_changed:' + row['name'])
        require((left['kind'] == 'return') == row['accepted'], 'fixture_expected_acceptance:' + row['name'])
        checks.append({'name': row['name'], 'accepted': row['accepted'],
                       'same_output_or_exact_error': True, 'outcome_sha256': sha(canonical(left))})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--plan-only', action='store_true')
    modes.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    sys.addaudithook(audit)
    pins_raw = regular(PACKAGE / 'pins.json', MAX_RECEIPT)
    pins = decode(pins_raw)
    result = {'schema': 'nico.c34.same_image_dependency_parser_diagnostic.v1',
              'status': 'UNPROVEN', 'production_qualified': False, 'target_execution': False,
              'native_execution': False, 'analyzer_execution': False, 'assessed_compiler_execution': False,
              'diagnostic_container_executed': False, 'full_producer_sequence_executed': False,
              'historical001f_diagnosis_reused': True, 'historical_image_recovered': False,
              'scope': 'Actual AST definitions of _dependency_populations and _source_path only.',
              'module_or_PROGRAM_executed': False, 'pins_sha256': sha(pins_raw),
              'sources': pins['sources'], 'function_AST_sha256': pins['functions'], 'timings': [],
              'required_full_obligations_unchanged': {'contexts': 577, 'fallback_contexts': 576,
                  'full_headers_and_generated_inputs': True, 'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}}
    try:
        if args.plan_only:
            result.update(status='PLAN_ONLY', mode='plan_only', fixture_pairs_planned=41,
                          individual_fixture_calls_planned=82, retained_nonempty_lists_planned=576,
                          image=pins['image'], baseline=pins['baseline'], functions_executed=False)
        else:
            (before, after), fixtures = scopes(pins)
            if args.controls_only:
                result.update(mode='owned_host_controls_only', fixture_checks=controls(before, after, fixtures),
                              status='OWNED_AST_CONTROLS_VERIFIED', same_image_measurement=False)
            else:
                require(args.inputs is not None, 'input_root_required')
                result['mode'] = 'same_retrieved_diagnostic_image_ast_helpers'
                result['environment'] = environment(pins)
                result['diagnostic_container_executed'] = True
                request, dependencies, retained, provenance = inputs(args.inputs, pins)
                result['input_provenance'] = provenance
                untouched = sha(canonical(request)), sha(canonical([(index, sha(raw)) for index, raw in dependencies]))
                values = []
                for variant, subject in [('baseline', before), ('candidate', after)]:
                    started = time.perf_counter_ns(); cpu = time.process_time_ns()
                    outputs = [subject(raw, request) for index, raw in dependencies]
                    elapsed = time.perf_counter_ns() - started; used = time.process_time_ns() - cpu
                    result['timings'].append({'variant': variant, 'dependency_lists': len(dependencies),
                        'wall_ms': elapsed / 1e6, 'process_cpu_ms': used / 1e6,
                        'includes': 'Actual helper lexical parsing, path validation and namespace membership only.'})
                    values.append(outputs)
                require(values[0] == values[1] == retained, 'actual_retained_helper_outputs_changed')
                require(untouched == (sha(canonical(request)), sha(canonical([(index, sha(raw))
                        for index, raw in dependencies]))), 'actual_inputs_mutated')
                result.update(status='SAME_IMAGE_AST_HELPERS_VERIFIED', outputs_sha256=sha(canonical(values[0])),
                    actual_retained_outputs_identical=True, original_inputs_unchanged=True,
                    fixture_checks=controls(before, after, fixtures), fixture_pairs=41, individual_fixture_calls=82,
                    timing_limitations='One fixed baseline-then-candidate sequence, same process/image/request/raw input; '
                    'prepared and parsed inputs, unknown cache state; no cold claim, repeats, analyzer, setup, allocation, '
                    'full validator, full producer or complete-qualification evidence.')
                peak = regular('/sys/fs/cgroup/memory.peak', 1024).decode().strip()
                require(peak.isdecimal() and int(peak) <= 12884901888, 'memory_peak_bound')
                result['memory_peak_bytes_including_untimed_preparation_and_controls'] = int(peak)
        result['forbidden_events'] = EVENTS
        payload = canonical(result) + b'\n'
        require(len(payload) <= MAX_RECEIPT, 'compact_receipt_bound')
        sys.stdout.buffer.write(payload)
    except BaseException as error:
        result.update(status='UNPROVEN', error={'type': type(error).__name__, 'message': str(error)}, forbidden_events=EVENTS)
        payload = canonical(result) + b'\n'
        require(len(payload) <= MAX_RECEIPT, 'compact_failure_receipt_bound')
        sys.stdout.buffer.write(payload)
        raise


if __name__ == '__main__':
    main()
