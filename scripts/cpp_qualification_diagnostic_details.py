"""Read-only failure details; never acceptance proof or raw native log output.

The caller supplies live validated evidence, not a deserialized qualification
receipt. Public path authority is created only after successful source freezing.
"""
import base64
import hashlib
import json
import re

from nico.assessment_cpp_full_project import _json

PUBLIC_MANIFEST_SHA256 = '66c3d940128ce3625fad9411448e71c06000a1b045adadde59246ea8ba2637b9'
PUBLIC_COMMIT = 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24'
PUBLIC_TREE = '186194c9de7f613d2d323db41cb8ce6bf1e3e549'
MAX_RECORD_BYTES = 60 * 1024
MAX_ARTIFACT_BYTES = 56 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024
_HASH = re.compile(r'[0-9a-f]{64}')
_PATH = re.compile(r'src/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:cpp|cc|c|h|hpp)')
_LOCATION = re.compile(r'(?P<path>(?:/work/source/)?src/[A-Za-z0-9_./-]{1,240}):'
                       r'(?P<line>[1-9][0-9]{0,6}):(?P<column>[1-9][0-9]{0,6}): '
                       r'(?P<kind>fatal error|error|runtime error): (?P<message>[^\r\n]*)')


def public_paths_after_freeze(manifest_sha256, source):
    """Call only with the result of the current successful freeze invocation."""
    if (manifest_sha256 != PUBLIC_MANIFEST_SHA256
            or source.get('repository') != 'bitcoin/bitcoin'
            or source.get('commit_sha') != PUBLIC_COMMIT
            or source.get('tree_sha') != PUBLIC_TREE
            or source.get('inventory_complete') is not True):
        return frozenset()
    return frozenset(path for path in source['targets']
                     if len(path) <= 240 and _PATH.fullmatch(path)
                     and all(part not in ('.', '..', '') for part in path.split('/')))


def _decoded_output(row, maximum=MAX_LOG_BYTES):
    text = row['output']
    if type(text) is not str or len(text) > 4 * ((maximum + 2) // 3):
        raise ValueError('diagnostic_output_invalid')
    raw = base64.b64decode(text, validate=True)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != row['output_sha256']:
        raise ValueError('diagnostic_output_invalid')
    return raw


def _category(kind, message):
    if kind != 'runtime error':
        return 'compiler_' + kind.replace(' ', '_')
    # Observed diagnostic category, not proof of a source defect.
    for prefix, category in (
        ('signed integer overflow:', 'signed_integer_overflow'),
        ('shift exponent ', 'shift_out_of_bounds'),
        ('left shift of ', 'shift_out_of_bounds'),
        ('load of null pointer', 'null_pointer'),
        ('store to null pointer', 'null_pointer'),
        ('member access within null pointer', 'null_pointer'),
        ('reference binding to null pointer', 'null_pointer'),
        ('load of misaligned address', 'alignment'),
        ('store to misaligned address', 'alignment'),
        ('index ', 'out_of_bounds'),
    ):
        if message.startswith(prefix):
            return category
    return 'runtime_error_other'


def locations(raw, public_paths):
    """Exact inventory matches only; never extract a path from message text."""
    if type(raw) is not bytes or len(raw) > MAX_LOG_BYTES:
        raise ValueError('diagnostic_output_invalid')
    selected, total = [], 0
    for line in raw.decode('utf-8', errors='strict').splitlines():
        if len(line) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in line):
            continue
        match = _LOCATION.fullmatch(line)
        if match is None:
            continue
        path = match['path'].removeprefix('/work/source/')
        if path not in public_paths:
            continue
        total += 1
        if len(selected) < 8:
            selected.append({'path': path, 'line': int(match['line']),
                'column': int(match['column']), 'observed_category': _category(match['kind'], match['message'])})
    return {'locations': selected, 'locations_omitted': total - len(selected)}


def _outcome(execution):
    if execution is None:
        return 'not_executed'
    if execution['timed_out']:
        return 'timed_out'
    if execution['output_truncated']:
        return 'output_truncated'
    return 'nonzero_exit' if execution['exit_code'] != 0 else 'record_error'


def compiler_details(proof, read, public_paths):
    """Proof must come from this invocation's validate_project_compiler result."""
    ref = proof['artifact']
    sha = proof['native_evidence_sha256']
    if (type(sha) is not str or not _HASH.fullmatch(sha)
            or ref != {'path': 'artifacts/project-compiler-evidence-' + sha + '.json',
                       'sha256': sha, 'bytes': ref.get('bytes')}
            or type(ref['bytes']) is not int or not 0 < ref['bytes'] <= MAX_ARTIFACT_BYTES):
        raise ValueError('diagnostic_artifact_invalid')
    raw = read(ref['path'], MAX_ARTIFACT_BYTES)
    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('diagnostic_artifact_invalid')
    value = _json(raw)
    records = value['records']
    if (value['schema'] not in ('nico.cpp-project-compiler-evidence.v1', 'nico.cpp-project-compiler-evidence.v2')
            or len(records) > 10000
            or [row['context_id'] for row in records] != proof['required_contexts']):
        raise ValueError('diagnostic_population_invalid')
    rows, total = [], 0
    for index, record in enumerate(records):
        execution = record['execution']
        if record['error'] is None and execution is not None and _outcome(execution) == 'record_error':
            continue
        total += 1
        if len(rows) == 16:
            continue
        # Index is bound to validated request order. Do not echo a hash-shaped
        # untrusted identifier or the command that produced it.
        row = {'context_index': index, 'outcome': _outcome(execution)}
        if execution is not None:
            row.update(locations(_decoded_output(execution), public_paths))
        rows.append(row)
    return {'state': 'available', 'failed_records': total, 'omitted': total - len(rows), 'records': rows}


def runtime_details(runtime, public_paths):
    """Runtime must have passed validate_retained_runtime in this invocation.

    Reuse its discovery/JUnit-validated results; do not reparse arbitrary XML or
    expose names. No test is blamed for a log location without a proven binding.
    """
    rows, remaining_tests = [], 16
    diagnostics = {row['kind']: row for row in runtime.get('failure_diagnostics', [])}
    for sanitizer in runtime['sanitizers']:
        kind = sanitizer['kind']
        if kind not in ('address', 'undefined'):
            raise ValueError('diagnostic_kind_invalid')
        tests = sanitizer.get('tests')
        if tests is None or _outcome(tests) == 'record_error':
            continue
        known_results = sanitizer.get('results') is not None
        result = sanitizer.get('results') or {}
        required = result.get('required', [])
        if len(required) > 10000:
            raise ValueError('diagnostic_population_invalid')
        executed, passed = set(result.get('executed', [])), set(result.get('passed', []))
        failures = [(i, name) for i, name in enumerate(required) if name in executed and name not in passed]
        selected = failures[:remaining_tests]
        remaining_tests -= len(selected)
        row = {'kind': kind, 'phase': 'tests', 'outcome': _outcome(tests),
               'results_state': 'available' if known_results else 'unavailable',
               'failed_tests': len(failures) if known_results else None,
               'omitted': len(failures) - len(selected) if known_results else None,
               'tests': [{'population_index': i, 'name_sha256': hashlib.sha256(name.encode()).hexdigest()}
                         for i, name in selected], 'locations_state': 'unavailable'}
        diagnostic = diagnostics.get(kind)
        if diagnostic is not None and diagnostic.get('log_read') is not None:
            # The native read wrapper has its own digest in addition to the
            # validated runtime artifact; never print the wrapper or inner text.
            try:
                log_read = diagnostic['log_read']
                if log_read['output_truncated']:
                    row['locations_state'] = 'truncated'
                elif log_read['exit_code'] == 0 and not log_read['timed_out']:
                    wrapper = _json(_decoded_output(log_read, 2 * MAX_LOG_BYTES + 4096))
                    if set(wrapper) != {'data', 'truncated'} or type(wrapper['truncated']) is not bool:
                        raise ValueError('diagnostic_output_invalid')
                    if wrapper['truncated']:
                        row['locations_state'] = 'truncated'
                    else:
                        if type(wrapper['data']) is not str or len(wrapper['data']) > 4 * ((MAX_LOG_BYTES + 2) // 3):
                            raise ValueError('diagnostic_output_invalid')
                        row.update(locations(base64.b64decode(wrapper['data'], validate=True), public_paths))
                        row['locations_state'] = 'available'
            except (Exception, KeyboardInterrupt):
                pass  # Missing log detail must not erase validated test identity.
        rows.append(row)
    return {'state': 'available', 'sanitizers': rows}


def add_failure_details(summary, context, read):
    """Fail closed independently per source, preserving the original aggregates."""
    details = {'schema': 'nico.cpp-qualification-failure-details.v1'}
    public_paths = context.get('public_paths', frozenset())
    for key, project in (('compiler', lambda value: compiler_details(value, read, public_paths)),
                         ('runtime', lambda value: runtime_details(value, public_paths))):
        details[key] = {'state': 'unavailable'}
        if context.get(key) is not None:
            try:
                details[key] = project(context[key])
            except (Exception, KeyboardInterrupt):
                pass
    result = {**summary, 'details': details}
    if len(json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode()) > MAX_RECORD_BYTES:
        result['details'] = {'state': 'output_budget_exceeded'}
    return result
