"""One bounded, candidate-aware capture before the verified scan workspace closes."""
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import re
import os
import selectors
import subprocess
import time

from nico.candidate_investigation_pipeline_v1 import VERSION, scope_of
from nico.candidate_source_observations_v1 import candidate_source_path, observe_python_source

INPUT_LIMIT = 8 * 1024 * 1024
OUTPUT_LIMIT = 2 * 1024 * 1024
FILE_LIMIT = 262144
CANDIDATE_LIMIT = 10000
SUPPORTED = frozenset({'B101', 'B404', 'B405', 'B603', 'B607'})


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True).encode('utf-8')


def capture_candidates(rows, scope, inventory, read_blob, *, started=None, clock=time.monotonic):
    """Inventory/read callbacks share the deadline; never follow a candidate path.

    Inventory maps paths to verified regular Git blob (object ID, size) pairs.
    Parser deadline is cooperative between bounded 256 KiB parses, as before.
    The entire serialized returned observation envelope is limited in UTF-8 bytes.
    """
    started = clock() if started is None else started
    deadline = started + 5
    scope = scope_of(scope)
    reasons = Counter()
    result = {'artifact_schema': VERSION, 'scope': scope, 'observations': {},
              'source_bytes_read': 0, 'unavailable_reasons': reasons,
              'raw_source_retained': False, 'selection_policy': 'supported-rule-paths-then-other-candidate-paths.v1',
              'deadline_kind': 'cooperative_between_bounded_parses',
              'candidate_record_count': len(rows), 'candidate_records_considered': min(len(rows), CANDIDATE_LIMIT),
              'candidate_inventory_complete': len(rows) <= CANDIDATE_LIMIT,
              'input_byte_limit': INPUT_LIMIT, 'output_byte_limit': OUTPUT_LIMIT}
    priorities = {}
    if not all(scope.values()) or any(len(v) > 1024 for v in scope.values()):
        result['scope'] = {key: value if len(value) <= 1024 else '' for key, value in scope.items()}
        reasons['source_scope_missing'] += 1
        return result
    for row in rows[:CANDIDATE_LIMIT]:
        if clock() >= deadline:
            reasons['source_time_budget'] += 1
            break
        if not isinstance(row, Mapping):
            reasons['unsupported_source'] += 1
            continue
        path = candidate_source_path(row.get('source_path') or row.get('path'))
        if (path is None or '.git' in path.split('/') or not path.endswith('.py')
                or row.get('category') != 'static' or row.get('exact_commit_sha') != scope['commit_sha']
                or row.get('source_commit_sha', scope['commit_sha']) not in ('', scope['commit_sha'])
                or row.get('source_repository', scope['repository']) not in ('', scope['repository'])):
            reasons['unsupported_source'] += 1
            continue
        priority = int((row.get('rule_id') or row.get('rule')) not in SUPPORTED)
        priorities[path] = min(priority, priorities.get(path, 1))
    result['candidate_path_count'] = len(priorities)
    if len(rows) > CANDIDATE_LIMIT:
        reasons['candidate_inventory_limit'] = len(rows) - CANDIDATE_LIMIT
    try:
        ordered = sorted(priorities, key=lambda path: (priorities[path], path))
        entries = inventory(deadline, ordered) if priorities and clock() < deadline else {}
        metadata_size = 0
        if isinstance(entries, tuple):
            entries, metadata_size = entries
        result['inventory_metadata_bytes'] = metadata_size
        retained = 0
        for index, path in enumerate(ordered):
            if clock() >= deadline:
                reasons['source_time_budget'] += len(ordered) - index
                break
            entry = entries.get(path)
            if entry is None:
                reasons['source_missing_or_unsupported'] += 1
                continue
            oid, size = entry
            if type(size) is not int or size < 0 or size > FILE_LIMIT or result['source_bytes_read'] + metadata_size + size > INPUT_LIMIT:
                reasons['source_size_budget'] += 1
                continue
            # Charge reserved bytes even if reading fails; no refund/retry budget.
            result['source_bytes_read'] += size
            data = read_blob(oid, size, deadline)
            if not isinstance(data, bytes) or len(data) != size or hashlib.sha1(
                    b'blob ' + str(size).encode() + b'\0' + data, usedforsecurity=False).hexdigest() != oid:
                reasons['source_analysis_failed'] += 1
                continue
            observation = observe_python_source(data, repository=scope['repository'],
                commit_sha=scope['commit_sha'], path=path, blob_oid=oid)
            if clock() >= deadline:
                reasons['source_time_budget'] += len(ordered) - index
                break
            size = len(encoded({path: observation}))
            # Reserve a bounded envelope allowance; final serialization is checked too.
            if retained + size > OUTPUT_LIMIT - 32768:
                reasons['observation_size_budget'] += 1
                continue
            result['observations'][path] = observation
            retained += size
    except (OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
        reasons['source_time_budget' if clock() >= deadline else 'source_analysis_failed'] += 1
    result['unavailable_reasons'] = dict(reasons)
    result['elapsed_seconds'] = round(clock() - started, 6)
    result['deadline_exhausted'] = clock() >= deadline
    if len(encoded(result)) > OUTPUT_LIMIT:
        result['observations'] = {}
        result['unavailable_reasons']['observation_size_budget'] = len(priorities)
    return result


def capture_workspace(repo_path, payload, actual_commit, results, *, env, clock=time.monotonic):
    started = clock()
    scope = scope_of({**payload, 'commit_sha': actual_commit})
    if actual_commit != payload.get('snapshot_commit_sha') or not re.fullmatch(r'[a-f0-9]{40}', actual_commit):
        return capture_candidates([], {}, lambda *args: {}, lambda *args: b'', started=started, clock=clock)
    from nico.comprehensive_native_providers_v5 import _normalized_record
    rows = []
    count = sum(len(item.get('findings') or []) for item in results if isinstance(item, Mapping) and isinstance(item.get('findings'), list))
    for item in results:
        if not isinstance(item, Mapping) or not isinstance(item.get('findings'), list):
            continue
        for finding in item['findings']:
            if len(rows) >= CANDIDATE_LIMIT or clock() >= started + 5:
                break
            if isinstance(finding, Mapping):
                rows.append(_normalized_record(commit_sha=actual_commit,
                    scanner=str(item.get('tool') or item.get('scanner_name') or ''),
                    category=str(item.get('category') or 'unknown'), finding=finding))
    git_env = {**env, 'GIT_NO_LAZY_FETCH': '1', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_LITERAL_PATHSPECS': '1'}
    metadata_bytes = [0]
    def git(args, deadline, limit):
        if deadline <= clock():
            raise TimeoutError('capture_deadline')
        # Bounded streaming prevents a large/malformed tree from being buffered.
        process = subprocess.Popen(['git', *args], cwd=repo_path, env=git_env,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, shell=False)
        output = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - clock()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TimeoutError('capture_deadline')
                    block = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
                    if not block:
                        break
                    output.extend(block)
                    if len(output) > limit:
                        raise ValueError('capture_git_output_limit')
            if process.wait(timeout=max(0.001, deadline - clock())) != 0:
                raise ValueError('capture_git_read_failed')
            return bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    def inventory(deadline, paths):
        metadata_bytes[0] = FILE_LIMIT  # conservative reservation on failed inventory reads
        raw = git(['ls-tree', '-rz', '-l', actual_commit, '--', *paths], deadline, FILE_LIMIT)
        metadata_bytes[0] = len(raw)
        entries = {}
        for line in raw.split(b'\0'):
            if clock() >= deadline:
                raise TimeoutError('capture_deadline')
            if not line:
                continue
            meta, raw_path = line.split(b'\t', 1)
            mode, kind, oid, size = meta.split()
            path = raw_path.decode('utf-8', errors='strict')
            if (path in paths and mode in (b'100644', b'100755') and kind == b'blob'
                    and size.isdigit() and re.fullmatch(b'[a-f0-9]{40}', oid)):
                entries[path] = (oid.decode('ascii'), int(size))
        return entries, len(raw)
    result = capture_candidates(rows, scope, inventory,
        lambda oid, size, deadline: git(['cat-file', 'blob', oid], deadline, size), started=started, clock=clock)
    result['inventory_metadata_bytes'] = metadata_bytes[0]
    result['total_input_bytes_charged'] = result['source_bytes_read'] + metadata_bytes[0]
    result['inventory_basis'] = 'retained_detailed_scanner_findings_only'
    result['scanner_collection_complete'] = bool(results) and all(isinstance(item, Mapping) and item.get('status') in {'completed', 'not_applicable'} for item in results)
    result.update(candidate_record_count=count, candidate_records_considered=len(rows),
                  candidate_inventory_complete=len(rows) == count)
    if count > len(rows):
        result['unavailable_reasons']['candidate_inventory_limit'] = count - len(rows)
    result['elapsed_seconds'] = round(clock() - started, 6)
    result['deadline_exhausted'] = clock() >= started + 5
    result['retained_output_bytes'] = 0
    for _ in range(4):
        result['retained_output_bytes'] = len(encoded(result))
    return result
