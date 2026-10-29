"""Bounded source observations and persisted reviewer assistance; no score/disposition writes."""
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import re
import time

from nico.candidate_source_observations_v1 import observe_python_source, investigate_candidate

VERSION = 'nico.persisted-candidate-investigation.v1'
REASONS = frozenset({'source_scope_unavailable_or_stale', 'investigation_budget_exhausted', 'source_identity_mismatch', 'unsupported_or_missing_exact_source_evidence', 'source_parse_unavailable', 'source_file_binding_mismatch', 'source_line_missing', 'rule_semantics_require_specialist_review', 'rule_source_line_mismatch', 'ambiguous_call_expression', 'retained_observation_invalid', 'exact_line_structure_only'})
SCOPE_KEYS = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')


def scope_of(value):
    return {k: str(value.get(k) or '') for k in SCOPE_KEYS}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def capture_sources(files, scope, *, clock=time.monotonic):
    """Consume already acquired snapshot text; never fetch or retain source prose.

    Five-second cooperative budget, 256 KiB per parse, 8 MiB input and 2 MiB
    retained output. The deadline is checked after each bounded parse as well.
    """
    scope = scope_of(scope)
    if not all(scope.values()):
        return {'artifact_schema': VERSION, 'scope': scope, 'observations': {}, 'unavailable_reasons': {'source_scope_missing': 1}, 'raw_source_retained': False}
    started = clock()
    observations, reasons, read_bytes, retained_bytes = {}, Counter(), 0, 0
    for path, text in sorted(files.items()):
        if not isinstance(path, str) or not path.endswith('.py') or not isinstance(text, str):
            reasons['unsupported_source'] += 1
            continue
        if clock() - started >= 5:
            reasons['source_time_budget'] += 1
            continue
        data = text.encode('utf-8')
        if len(data) > 262144 or read_bytes + len(data) > 8 * 1024 * 1024:
            reasons['source_size_budget'] += 1
            continue
        read_bytes += len(data)
        try:
            # Git-format compatibility only, never the observation fingerprint.
            oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data, usedforsecurity=False).hexdigest()
            observation = observe_python_source(data, repository=scope['repository'],
                commit_sha=scope['commit_sha'], path=path, blob_oid=oid)
        except (ValueError, TypeError, RecursionError):
            reasons['source_analysis_failed'] += 1
            continue
        if clock() - started >= 5:
            reasons['source_time_budget'] += 1
            continue
        if 'source_binding' in observation:
            # Text was decoded by the existing snapshot collector. Never label
            # its re-encoding as original Git bytes or an authenticated Git OID.
            observation['source_binding'].pop('blob_oid', None)
            observation['source_binding']['origin'] = 'snapshot_decoded_text'
        size = len(json.dumps(observation))
        if retained_bytes + size > 2 * 1024 * 1024:
            reasons['observation_size_budget'] += 1
            continue
        retained_bytes += size
        observations[path] = observation
    return {'artifact_schema': VERSION, 'scope': scope_of(scope), 'observations': observations,
            'source_bytes_read': read_bytes, 'unavailable_reasons': dict(reasons),
            'raw_source_retained': False, 'deadline_kind': 'cooperative_between_bounded_parses'}


def investigate_register(register, retained, scope, *, clock=time.monotonic):
    """One packet per original candidate; caller persists alongside unchanged findings."""
    started = clock()
    scope = scope_of(scope)
    valid = (all(scope.values()) and isinstance(retained, Mapping)
             and retained.get('artifact_schema') == VERSION and retained.get('scope') == scope)
    observations = retained.get('observations', {}) if valid else {}
    if not isinstance(observations, Mapping):
        observations = {}
    packets = []
    for index, row in enumerate(register.get('findings') or []):
        if index >= 10000 or clock() - started >= 2:
            reason = 'investigation_budget_exhausted'
        elif not valid:
            reason = 'source_scope_unavailable_or_stale'
        else:
            reason = None
        if reason:
            packet = {'candidate_id': row.get('candidate_id'), 'bounded_rule_analysis_completed': False,
                      'reason': reason, 'unresolved_questions': [reason], 'rationale': [], 'counterevidence': []}
        else:
            observation = observations.get(row.get('source_path') or row.get('path'), {})
            try:
                packet = investigate_candidate(row, observation, observed_commit=scope['commit_sha'],
                    expected_commit=scope['commit_sha'], expected_repository=scope['repository'])
            except (ValueError, TypeError, AttributeError, RecursionError):
                packet = {'candidate_id': row.get('candidate_id'), 'bounded_rule_analysis_completed': False,
                          'reason': 'retained_observation_invalid', 'unresolved_questions': ['retained_observation_invalid']}

        reference = packet.get('source_reference') or {}
        # Persist compact versioned reasoning codes, not repeated prose and scope.
        packets.append({'candidate_id': row.get('candidate_id'),
            'candidate_input_sha256': fingerprint(row), 'rule_id': row.get('rule_id') or row.get('rule'),
            'bounded_rule_analysis_completed': packet['bounded_rule_analysis_completed'],
            'reason': packet.get('reason', 'unresolved'),
            'source_reference': {k: reference[k] for k in ('source_sha256', 'line') if k in reference},
            'argument_observations': packet.get('argument_observations', {})})
    return {'artifact_schema': VERSION, 'scope': scope, 'input_sha256': fingerprint(register.get('findings') or []),
            'candidate_count': len(packets), 'bounded_rule_analysis_completed': sum(p['bounded_rule_analysis_completed'] for p in packets),
            'unresolved_reasons': dict(Counter(p.get('reason', 'unresolved') for p in packets if not p['bounded_rule_analysis_completed'])),
            'source_capture': {
                'scope_valid': bool(valid),
                'observation_count': len(observations),
                'parsed_observation_count': sum(isinstance(item, Mapping) and item.get('status') == 'parsed' for item in observations.values()),
                'unavailable_reasons': {key: value for key, value in (retained.get('unavailable_reasons', {}) if valid and isinstance(retained.get('unavailable_reasons'), Mapping) else {}).items()
                    if key in {'source_scope_missing', 'unsupported_source', 'source_time_budget', 'source_size_budget', 'source_analysis_failed', 'observation_size_budget'} and type(value) is int and value >= 0},
            },
            'packets': packets, 'human_review_required': True, 'client_delivery_allowed': False, 'model_invocations': 0}


def display_investigation(register, scope):
    """Read-only projection. Repeated GETs never parse source or launch work."""
    value = register.get('candidate_investigation') or {}
    rows = register.get('findings') or []
    if (not isinstance(value, Mapping) or not isinstance(rows, list)
            or not isinstance(value.get('packets'), list)
            or value.get('artifact_schema') != VERSION or value.get('scope') != scope_of(scope)
            or value.get('input_sha256') != fingerprint(rows) or len(value.get('packets', [])) != len(rows)):
        return {'available': False, 'reason': 'retained_investigation_missing_or_stale', 'packets': []}
    packets = []
    for row, packet in zip(rows, value['packets']):
        if (not isinstance(row, Mapping) or not isinstance(packet, Mapping)
                or not isinstance(packet.get('source_reference', {}), Mapping)
                or packet.get('candidate_input_sha256') != fingerprint(row)):
            return {'available': False, 'reason': 'retained_investigation_missing_or_stale', 'packets': []}
        # No arbitrary retained narrative reaches the browser. Authored bilingual
        # explanations are selected by supported rule IDs in the presentation.
        reference = packet.get('source_reference') or {}
        path = row.get('source_path') or row.get('path')
        safe_path = isinstance(path, str) and 0 < len(path) <= 1024 and not path.startswith('/') and '\\' not in path and all(p not in {'', '.', '..'} for p in path.split('/')) and all(ord(c) >= 32 for c in path)
        source_hash = reference.get('source_sha256')
        valid_hash = isinstance(source_hash, str) and re.fullmatch(r'[0-9a-f]{64}', source_hash) is not None
        valid_line = (type(row.get('line')) is int and row['line'] > 0
                      and type(reference.get('line')) is int and reference['line'] == row['line'])
        claimed_complete = packet.get('bounded_rule_analysis_completed') is True
        valid_reference = safe_path and valid_hash and valid_line
        reason = packet.get('reason') if isinstance(packet.get('reason'), str) and packet['reason'] in REASONS else 'unresolved'
        if claimed_complete and not valid_reference:
            reason = 'retained_observation_invalid'
        packets.append({'source_path': path if safe_path else None, 'candidate_id': row.get('candidate_id'), 'rule_id': row.get('rule_id') or row.get('rule'),
                        'completed': claimed_complete and valid_reference and (row.get('rule_id') or row.get('rule')) in {'B101', 'B404', 'B405', 'B603', 'B607'},
                        'source_sha256': source_hash if valid_hash else None,
                        'line': row.get('line') if type(row.get('line')) is int and row['line'] > 0 else None,
                        'reason': reason})
    return {'available': True, 'candidate_count': len(rows), 'completed_count': sum(p['completed'] for p in packets),
            'unresolved_reasons': dict(Counter(p['reason'] for p in packets if not p['completed'])), 'packets': packets}
