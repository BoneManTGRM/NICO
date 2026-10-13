"""Validate numeric diagnostic snapshots; never turn them into qualification."""
from __future__ import annotations

import re

from scripts.native_stage_counters.instrument import ORIGINAL_BINARY_SHA256

PREFIX = b'NICO_STAGE_V1 '
FIELDS = ('phase', 'pass', 'call', 'alias', 'outer_visits', 'inner_visits',
          'scope_nodes', 'match_calls', 'base_queries', 'base_visits', 'scope_queries',
          'child_visits', 'replacements', 'instantiations', 'using_calls', 'aliases',
          'rhs_distance_calls', 'rhs_distance_tokens', 'rhs_parses', 'prelude_visits')
MAX_RECORDS = 128
MAX_RECORD_BYTES = 1024


def parse_snapshots(stderr: bytes, *, timed_out: bool, binary_sha256: str,
                   output_truncated: bool | None = None) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', binary_sha256) or binary_sha256 == ORIGINAL_BINARY_SHA256:
        raise ValueError('instrumented_binary_requires_distinct_identity')
    records = []
    incomplete_tail = False
    for raw_line in stderr.splitlines(keepends=True):
        line = raw_line.rstrip(b'\r\n')
        if not raw_line.endswith(b'\n') and (line.startswith(PREFIX) or PREFIX.startswith(line)):
            # SIGKILL/output caps can interrupt fwrite. Keep already validated records.
            incomplete_tail = True
            break
        if not line.startswith(PREFIX):
            continue
        if len(line) + 1 > MAX_RECORD_BYTES or len(records) >= MAX_RECORDS:
            raise ValueError('stage_output_bound_exceeded')
        words = line[len(PREFIX):].split(b' ')
        if len(words) != 7 + len(FIELDS) or any(not re.fullmatch(rb'-?[0-9]{1,20}', w) for w in words):
            raise ValueError('stage_record_invalid')
        values = [int(w) for w in words]
        seq, event, kind, lane, wall_us, cpu_ticks, clock_scale, *counts = values
        if (seq != len(records) + 1 or event not in (0, 1, 2) or kind not in (1, 2, 3)
                or lane < 0 or wall_us < 0 or cpu_ticks < -1 or clock_scale <= 0
                or any(v < 0 or v > 2**64 - 1 for v in counts)
                or counts[0] not in (1, 2, 3)):
            raise ValueError('stage_record_invalid')
        records.append({'sequence': seq, 'event': event, 'kind': kind, 'lane': lane,
                        'wall_us': wall_us, 'cpu_ticks': cpu_ticks, 'clock_scale': clock_scale,
                        **dict(zip(FIELDS, counts))})
    return {'schema': 'nico.cppcheck-stage-counter-evidence.v1',
            'instrumented_binary_sha256': binary_sha256,
            'original_binary_sha256': ORIGINAL_BINARY_SHA256,
            'timed_out': timed_out, 'records': records,
            'incomplete_tail': incomplete_tail, 'output_truncated': output_truncated,
            'last_observed_snapshot': records[-1] if records else None,
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
                output_truncated=execution['output_truncated'], binary_sha256=binding['instrumented_binary_sha256'])
            record['native_output_sha256'] = execution['output_sha256']
        except (ValueError, KeyError, TypeError) as exc:
            record['error'] = str(exc) if str(exc).startswith(('stage_', 'instrumented_')) else type(exc).__name__
        result.append(record)
    return result
