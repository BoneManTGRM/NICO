"""Bounded source observations and persisted reviewer assistance; no score/disposition writes."""
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import re
import time

from nico.candidate_source_observations_v1 import observe_python_source, investigate_candidate, candidate_source_path

from nico.candidate_source_reason_detail_v1 import capture_detail, packet_detail
from nico.candidate_call_resolution_v1 import candidate_call_fact, VERSION as CALL_VERSION, QUALIFIED_APIS

from nico import dependency_identity_evidence_v1 as dependency_identity

VERSION = 'nico.persisted-candidate-investigation.v1'
REASONS = frozenset({'source_scope_unavailable_or_stale', 'investigation_budget_exhausted', 'source_identity_mismatch', 'unsupported_or_missing_exact_source_evidence', 'source_parse_unavailable', 'source_file_binding_mismatch', 'source_line_missing', 'rule_semantics_require_specialist_review', 'rule_source_line_mismatch', 'ambiguous_call_expression', 'retained_observation_invalid', 'exact_line_structure_only'})
SCOPE_KEYS = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')


# Optional evidence extension; legacy packets remain readable but cannot claim binding.
BINDING_VERSION = 'nico.reviewer-lexical-binding.v1'
BINDING_MAX_BYTES = 2048
BINDING_TOTAL_BYTES = 256 * 1024
BINDING_FIELDS = frozenset({'version', 'resolver_version', 'api', 'import_line', 'line',
    'source_sha256', 'blob_oid', 'scope', 'path', 'candidate_input_sha256'})


ARGUMENT_ENUMS = {
    'argument_form': frozenset({'sequence_expression', 'literal_text', 'dynamic_or_absent'}),
    'executable_path': frozenset({'absolute_literal', 'relative_literal', 'unknown'}),
    'shell_keyword': frozenset({'true', 'false', 'unspecified', 'dynamic'}),
}


def _sanitize_arguments(value):
    """Preserve existing syntax enums only; absence never means shell=False.

    At most three short enum strings. Embedded API binding is not qualified proof
    and neither it nor source/argument values belong in persisted assistance.
    """
    if not isinstance(value, Mapping):
        return {}
    return {key: value[key] for key, allowed in ARGUMENT_ENUMS.items()
            if isinstance(value.get(key), str) and value[key] in allowed}


def _binding_size(value):
    return len(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())


def _display_binding(value, row, scope, reference):
    """Validate a trusted persisted proof, not an issuer authentication mechanism.

    Reads never parse source. Only investigate_register issues this extension from
    the trusted capture; a scanner-supplied field on a candidate is never consumed.
    """
    if not isinstance(value, Mapping) or set(value) != BINDING_FIELDS:
        return None
    if (value.get('version') != BINDING_VERSION or value.get('resolver_version') != CALL_VERSION
            or not isinstance(value.get('api'), str) or value.get('api') not in QUALIFIED_APIS or value.get('scope') != scope
            or not all(isinstance(scope.get(k), str) and scope[k] for k in SCOPE_KEYS)
            or value.get('candidate_input_sha256') != fingerprint(row)
            or value.get('path') != candidate_source_path(row.get('source_path') or row.get('path'))
            or not value.get('path') or row.get('category') != 'static'
            or (row.get('scanner') or row.get('tool')) != 'bandit'
            or (row.get('rule_id') or row.get('rule')) not in {'B603', 'B607'}
            or type(value.get('line')) is not int or value['line'] != row.get('line')
            or type(value.get('import_line')) is not int or not 0 < value['import_line'] < value['line']
            or value.get('source_sha256') != reference.get('source_sha256')
            or value.get('line') != reference.get('line')
            or not re.fullmatch('[0-9a-f]{64}', str(value.get('source_sha256', '')))
            or not re.fullmatch('[0-9a-f]{40}', str(value.get('blob_oid', '')))):
        return None
    try:
        if _binding_size(value) > BINDING_MAX_BYTES:
            return None
    except (TypeError, ValueError):
        return None
    return dict(value)


def _issue_binding(row, capture, scope, reference):
    fact = candidate_call_fact(row, capture, scope)
    if not fact or fact.get('status') != 'resolved':
        return None
    value = {key: fact[key] for key in ('api', 'import_line', 'line', 'source_sha256', 'blob_oid', 'scope', 'path')}
    value.update(version=BINDING_VERSION, resolver_version=CALL_VERSION, candidate_input_sha256=fingerprint(row))
    return _display_binding(value, row, scope, reference)


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


def _capture_accounting(retained, valid):
    if not valid or retained.get('selection_policy') != 'supported-rule-paths-then-other-candidate-paths.v1':
        return {}
    values = {'selection_policy': retained['selection_policy']}
    if retained.get('inventory_basis') == 'retained_detailed_scanner_findings_only':
        values['inventory_basis'] = retained['inventory_basis']
    for key in ('candidate_record_count', 'candidate_records_considered', 'candidate_path_count',
                'source_bytes_read', 'inventory_metadata_bytes', 'total_input_bytes_charged',
                'input_byte_limit', 'output_byte_limit', 'retained_output_bytes'):
        value = retained.get(key)
        if type(value) is int and 0 <= value <= 100000000:
            values[key] = value
    for key in ('candidate_inventory_complete', 'deadline_exhausted', 'scanner_collection_complete'):
        if type(retained.get(key)) is bool:
            values[key] = retained[key]
    return values


def investigate_register(register, retained, scope, *, clock=time.monotonic):
    """One packet per original candidate; caller persists alongside unchanged findings."""
    started = clock()
    scope = scope_of(scope)
    valid = (all(scope.values()) and isinstance(retained, Mapping)
             and retained.get('artifact_schema') == VERSION and retained.get('scope') == scope)
    raw_observations = retained.get('observations') if valid else None
    observations = raw_observations if isinstance(raw_observations, Mapping) else {}
    if not isinstance(observations, Mapping):
        observations = {}
    packets = []
    binding_bytes = 0
    identity_bytes = 0
    identity_cache = {}
    identity_attempted = 0
    for index, row in enumerate(register.get('findings') or []):
        detail = None
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
            path = candidate_source_path(row.get('source_path') or row.get('path'))
            observation = observations.get(path, {}) if path is not None else {}
            try:
                packet = investigate_candidate(row, observation, observed_commit=scope['commit_sha'],
                    expected_commit=scope['commit_sha'], expected_repository=scope['repository'])
            except (ValueError, TypeError, AttributeError, RecursionError):
                packet = {'candidate_id': row.get('candidate_id'), 'bounded_rule_analysis_completed': False,
                          'reason': 'retained_observation_invalid', 'unresolved_questions': ['retained_observation_invalid']}

        if (valid and packet.get('reason') == 'source_parse_unavailable'
                and row.get('source_repository') in (None, '', scope['repository'])):
            detail = capture_detail(raw_observations, candidate_source_path(row.get('source_path') or row.get('path')), scope, retained.get('path_capture_outcomes'))
        identity = None
        if reason is None and valid and row.get('category') == 'dependency' and clock() - started < 2 and identity_bytes < 262144:
            key = fingerprint({'request': row.get('dependency_identity_request'), 'path': row.get('source_path'),
                               'exact_commit_sha': row.get('exact_commit_sha'), 'source_commit_sha': row.get('source_commit_sha'),
                               'source_repository': row.get('source_repository'),
                               'row_scope': {k: row[k] for k in ('run_id', 'customer_id', 'project_id') if k in row}})
            if key not in identity_cache and len(identity_cache) < 128:
                identity_cache[key] = dependency_identity.qualify(row, observations.get(candidate_source_path(row.get('source_path')), {}), scope)
            identity_attempted += int(key in identity_cache)
            proposal = identity_cache.get(key)
            size = len(json.dumps(proposal).encode()) if proposal else 0
            if clock() - started < 2 and identity_bytes + size <= 262144:
                identity = proposal
                identity_bytes += size
        reference = packet.get('source_reference') or {}
        binding = _issue_binding(row, retained, scope, reference) if valid and packet['bounded_rule_analysis_completed'] else None
        if binding is not None:
            size = _binding_size(binding)
            if binding_bytes + size > BINDING_TOTAL_BYTES:
                binding = None
            else:
                binding_bytes += size
        # Persist compact versioned reasoning codes, not repeated prose and scope.
        packets.append({**({'dependency_identity': identity} if identity else {}), 'candidate_id': row.get('candidate_id'),
            'candidate_input_sha256': fingerprint(row), 'rule_id': row.get('rule_id') or row.get('rule'),
            'bounded_rule_analysis_completed': packet['bounded_rule_analysis_completed'],
            'reason': packet.get('reason', 'unresolved'),
            'source_reference': {k: reference[k] for k in ('source_sha256', 'line') if k in reference},
            'argument_observations': _sanitize_arguments(packet.get('argument_observations')),
            **({'lexical_binding': binding} if binding is not None else {}),
            **({'source_availability_detail': detail} if detail is not None else {})})
    return {'artifact_schema': VERSION, 'scope': scope, 'input_sha256': fingerprint(register.get('findings') or []),
            'candidate_count': len(packets),
            'dependency_identity_attempted_count': identity_attempted,
            'dependency_identity_collected_count': sum('dependency_identity' in p for p in packets),
            'dependency_identity_output_byte_limit': 262144,
            'bounded_rule_analysis_completed': sum(p['bounded_rule_analysis_completed'] for p in packets),
            'unresolved_reasons': dict(Counter(p.get('reason', 'unresolved') for p in packets if not p['bounded_rule_analysis_completed'])),
            'source_availability_counts': dict(Counter(packet_detail(p) for p in packets if p.get('reason') == 'source_parse_unavailable' and not p['bounded_rule_analysis_completed'])),
            'source_capture': {
                **_capture_accounting(retained, valid),
                'scope_valid': bool(valid),
                'observation_count': len(observations),
                'parsed_observation_count': sum(isinstance(item, Mapping) and item.get('status') == 'parsed' for item in observations.values()),
                'unavailable_reasons': {key: value for key, value in (retained.get('unavailable_reasons', {}) if valid and isinstance(retained.get('unavailable_reasons'), Mapping) else {}).items()
                    if key in {'source_scope_missing', 'unsupported_source', 'source_time_budget', 'source_size_budget', 'source_analysis_failed', 'observation_size_budget', 'candidate_inventory_limit', 'source_missing_or_unsupported'} and type(value) is int and value >= 0},
            },
            'packets': packets, 'human_review_required': True, 'client_delivery_allowed': False, 'model_invocations': 0}


def display_investigation(register, scope, *, trusted_capture=None):
    """Read-only projection. Repeated GETs never parse source or launch work."""
    value = register.get('final_candidate_investigation') if 'final_candidate_investigation' in register else register.get('candidate_investigation')
    value = value or {}
    rows = register.get('findings') or []
    if (not isinstance(value, Mapping) or not isinstance(rows, list)
            or not isinstance(value.get('packets'), list)
            or value.get('artifact_schema') != VERSION or value.get('scope') != scope_of(scope)
            or value.get('input_sha256') != fingerprint(rows) or len(value.get('packets', [])) != len(rows)):
        return {'available': False, 'reason': 'retained_investigation_missing_or_stale', 'packets': []}
    packets = []
    binding_bytes = 0
    identity_cache = {}
    identity_output_bytes = 0
    for record_index, (row, packet) in enumerate(zip(rows, value['packets'])):
        if (not isinstance(row, Mapping) or not isinstance(packet, Mapping)
                or not isinstance(packet.get('source_reference', {}), Mapping)
                or packet.get('candidate_input_sha256') != fingerprint(row)):
            return {'available': False, 'reason': 'retained_investigation_missing_or_stale', 'packets': []}
        # No arbitrary retained narrative reaches the browser. Authored bilingual
        # explanations are selected by supported rule IDs in the presentation.
        reference = packet.get('source_reference') or {}
        path = candidate_source_path(row.get('source_path') or row.get('path'))
        safe_path = path is not None
        source_hash = reference.get('source_sha256')
        valid_hash = isinstance(source_hash, str) and re.fullmatch(r'[0-9a-f]{64}', source_hash) is not None
        valid_line = (type(row.get('line')) is int and row['line'] > 0
                      and type(reference.get('line')) is int and reference['line'] == row['line'])
        claimed_complete = packet.get('bounded_rule_analysis_completed') is True
        valid_reference = safe_path and valid_hash and valid_line
        reason = packet.get('reason') if isinstance(packet.get('reason'), str) and packet['reason'] in REASONS else 'unresolved'
        if claimed_complete and not valid_reference:
            reason = 'retained_observation_invalid'
        binding = _display_binding(packet.get('lexical_binding'), row, scope_of(scope), reference) if claimed_complete and valid_reference else None
        if binding is not None:
            size = _binding_size(binding)
            if binding_bytes + size > BINDING_TOTAL_BYTES:
                binding = None
            else:
                binding_bytes += size
        identity = packet.get('dependency_identity')
        qualified_identity = None
        if (row.get('category') == 'dependency' and isinstance(identity, Mapping)
                and isinstance(trusted_capture, Mapping) and trusted_capture.get('artifact_schema') == VERSION
                and trusted_capture.get('scope') == scope_of(scope)):
            captured = trusted_capture.get('observations')
            observed = captured.get(path) if isinstance(captured, Mapping) else None
            key = fingerprint({'request': row.get('dependency_identity_request'), 'path': row.get('source_path'),
                               'exact_commit_sha': row.get('exact_commit_sha'), 'source_commit_sha': row.get('source_commit_sha'),
                               'source_repository': row.get('source_repository'),
                               'row_scope': {k: row[k] for k in ('run_id', 'customer_id', 'project_id') if k in row}})
            if key not in identity_cache and len(identity_cache) < 128:
                identity_cache[key] = dependency_identity.qualify(row, observed, scope_of(scope))
            expected = identity_cache.get(key)
            size = len(json.dumps(expected).encode()) if expected else 0
            if expected is not None and identity == expected and identity_output_bytes + size <= 262144:
                qualified_identity = expected
                identity_output_bytes += size
        packets.append({**({'dependency_identity': qualified_identity} if qualified_identity else {}),
                        'record_index': record_index, 'candidate_input_sha256': fingerprint(row),
                        **({'lexical_binding': binding} if binding is not None else {}),
                        'source_path': path if safe_path else None, 'candidate_id': row.get('candidate_id'), 'rule_id': row.get('rule_id') or row.get('rule'),
                        'completed': claimed_complete and valid_reference and (row.get('rule_id') or row.get('rule')) in {'B101', 'B404', 'B405', 'B603', 'B607'},
                        'source_sha256': source_hash if valid_hash else None,
                        'line': row.get('line') if type(row.get('line')) is int and row['line'] > 0 else None,
                        'reason': reason,
                        **({'source_availability_detail': packet_detail(packet)} if reason == 'source_parse_unavailable' and not claimed_complete else {})})
    return {'available': True, 'candidate_count': len(rows), 'completed_count': sum(p['completed'] for p in packets),
            'dependency_identity_collected_count': sum('dependency_identity' in p for p in packets),
            'unresolved_reasons': dict(Counter(p['reason'] for p in packets if not p['completed'])),
            'source_availability_counts': dict(Counter(p['source_availability_detail'] for p in packets if 'source_availability_detail' in p and not p['completed'])), 'packets': packets}
