"""Validate numeric diagnostic snapshots; never turn them into qualification."""
from __future__ import annotations

import re

from scripts.native_stage_counters.instrument import ORIGINAL_BINARY_SHA256

PREFIX = b'NICO_STAGE_V1 '
FIELDS = ('phase', 'pass', 'call', 'alias', 'outer_visits', 'inner_visits',
          'scope_nodes', 'match_calls', 'base_queries', 'base_visits', 'scope_queries',
          'child_visits', 'replacements', 'instantiations', 'using_calls', 'aliases',
          'rhs_distance_calls', 'rhs_distance_tokens', 'rhs_parses', 'prelude_visits')
TEMPLATE_FIELDS = ('selection_cpu_ns', 'matching_cpu_ns', 'expansion_cpu_ns', 'replacement_cpu_ns',
    'selection_entered', 'matching_entered', 'expansion_entered', 'replacement_entered',
    'selection_completed', 'matching_completed', 'expansion_completed', 'replacement_completed',
    'selection_visits', 'specialization_visits', 'specialization_token_visits',
    'expansion_outer_visits', 'expansion_body_visits', 'replacement_visits', 'replacement_nested_visits',
    'active_bucket', 'bucket_depth', 'thread_clock_status')
FIELDS_V2 = FIELDS + TEMPLATE_FIELDS
MAX_RECORDS = 128
MAX_RECORD_BYTES = 1024


def parse_snapshots(stderr: bytes, *, timed_out: bool, binary_sha256: str,
                   output_truncated: bool | None = None, expected_version: int | None = None) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', binary_sha256) or binary_sha256 == ORIGINAL_BINARY_SHA256:
        raise ValueError('instrumented_binary_requires_distinct_identity')
    if expected_version is not None and (type(expected_version) is not int or expected_version not in (1, 2)):
        raise ValueError('stage_version_invalid')
    version = expected_version
    records = []
    lanes = {}
    incomplete_tail = False
    for raw_line in stderr.splitlines(keepends=True):
        line = raw_line.rstrip(b'\r\n')
        if line.startswith(b'NICO_STAGE_') and len(line) >= MAX_RECORD_BYTES:
            raise ValueError('stage_output_bound_exceeded')
        if line.startswith(b'NICO_STAGE_') and b' ' in line and line.split(b' ', 1)[0] not in (b'NICO_STAGE_V1', b'NICO_STAGE_V2'):
            raise ValueError('stage_version_mismatch')
        for known, known_version in ((b'NICO_STAGE_V1 ', 1), (b'NICO_STAGE_V2 ', 2)):
            if line.startswith(known) and version is not None and known_version != version:
                raise ValueError('stage_version_mismatch')
            if line.startswith(known):
                version = known_version
        if not raw_line.endswith(b'\n') and (line.startswith(b'NICO_STAGE_') or b'NICO_STAGE_'.startswith(line)):
            # SIGKILL/output caps can interrupt fwrite. Keep already validated records.
            incomplete_tail = True
            break
        if not line.startswith(b'NICO_STAGE_'):
            continue
        prefix = line.split(b' ', 1)[0]
        current_version = {b'NICO_STAGE_V1': 1, b'NICO_STAGE_V2': 2}.get(prefix)
        if current_version is None or (version is not None and current_version != version):
            raise ValueError('stage_version_mismatch')
        version = current_version
        fields = FIELDS if version == 1 else FIELDS_V2
        if len(line) + 1 > MAX_RECORD_BYTES or len(records) >= MAX_RECORDS:
            raise ValueError('stage_output_bound_exceeded')
        words = line[len(prefix) + 1:].split(b' ')
        if len(words) != 7 + len(fields) or any(not re.fullmatch(rb'-?[0-9]{1,20}', w) for w in words):
            raise ValueError('stage_record_invalid')
        values = [int(w) for w in words]
        seq, event, kind, lane, wall_us, cpu_ticks, clock_scale, *counts = values
        if (seq != len(records) + 1 or event not in (0, 1, 2) or kind not in (1, 2, 3)
                or lane < 0 or wall_us < 0 or cpu_ticks < -1 or clock_scale <= 0
                or any(v < 0 or v > 2**64 - 1 for v in counts)
                or counts[0] not in (1, 2, 3)):
            raise ValueError('stage_record_invalid')
        row = dict(zip(fields, counts))
        if version == 2:
            if (any(v > 2**64 - 1 for v in values) or lane > 2**32 - 1
                    or (records and (wall_us < records[-1]['wall_us']
                                     or clock_scale != records[-1]['clock_scale']))):
                raise ValueError('stage_record_invalid')
            if (row['active_bucket'] not in range(5) or row['thread_clock_status'] not in (0, 1, 2)
                    or bool(row['active_bucket']) != bool(row['bucket_depth'])
                    or any(row[b+'_completed'] > row[b+'_entered'] for b in ('selection','matching','expansion','replacement'))
                    or (row['thread_clock_status'] == 0 and any(row[b+'_cpu_ns'] for b in ('selection','matching','expansion','replacement')))):
                raise ValueError('stage_record_invalid')
            buckets = ('selection', 'matching', 'expansion', 'replacement')
            if row['active_bucket']:
                active = buckets[row['active_bucket'] - 1]
                if (row['thread_clock_status'] == 0 or row[active+'_entered'] == 0
                        or (row[active+'_entered'] != 2**64-1 and row[active+'_entered'] <= row[active+'_completed'])
                        or row['bucket_depth'] > sum(row[b+'_entered'] for b in buckets)):
                    raise ValueError('stage_record_invalid')
            previous = lanes.get(lane)
            cumulative = TEMPLATE_FIELDS[:-3]
            if previous and (any(row[k] < previous[k] for k in cumulative)
                             or row['thread_clock_status'] < previous['thread_clock_status']):
                raise ValueError('stage_record_regressed')
            lanes[lane] = row
        records.append({'sequence': seq, 'event': event, 'kind': kind, 'lane': lane,
                        'wall_us': wall_us, 'cpu_ticks': cpu_ticks, 'clock_scale': clock_scale,
                        **row})
    return {'schema': 'nico.cppcheck-stage-counter-evidence.v' + str(version or 1),
            'instrumented_binary_sha256': binary_sha256,
            'original_binary_sha256': ORIGINAL_BINARY_SHA256,
            'timed_out': timed_out, 'records': records,
            'incomplete_tail': incomplete_tail, 'output_truncated': output_truncated,
            'last_observed_snapshot': records[-1] if records else None,
            'clock_interpretation': {'wall_us': 'monotonic wall time',
                'cpu_ticks': 'process CPU; -1 means unavailable; divide by clock_scale',
                'template_cpu_ns': 'exclusive thread CPU; status 0 unattempted, 1 available, 2 unavailable; retained totals may be partial'},
            'precise_termination_hotspot_known': False,
            'analysis_completed': False, 'qualification_claimed': False}


def collect_case_snapshots(output, binding, expected_context_ids):
    """Read completed per-case prefixes even when the outer collector is killed."""
    import base64
    import hashlib
    import json
    selected = {}
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, UnicodeError):
            continue  # Original operation bytes retain any incomplete JSON tail.
        if not isinstance(item, dict):
            continue
        row = item.get('diagnostic_partial_record')
        if isinstance(row, dict) and row.get('context_id') in expected_context_ids:
            selected[row['context_id']] = row
    result = []
    for context_id in expected_context_ids:
        row = selected.get(context_id)
        execution = row.get('execution') if row else None
        record = {'context_id': context_id, 'snapshots': None, 'error': None}
        try:
            if not isinstance(execution, dict):
                raise ValueError('stage_execution_not_retained')
            raw = base64.b64decode(execution['output'], validate=True)
            if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != execution['output_sha256']:
                raise ValueError('stage_execution_output_binding')
            record['snapshots'] = parse_snapshots(raw, timed_out=execution['timed_out'],
                output_truncated=execution['output_truncated'], binary_sha256=binding['instrumented_binary_sha256'],
                expected_version=binding['record_version'])
            record['native_output_sha256'] = execution['output_sha256']
        except (ValueError, KeyError, TypeError) as exc:
            record['error'] = str(exc) if str(exc).startswith(('stage_', 'instrumented_')) else type(exc).__name__
        result.append(record)
    return result
