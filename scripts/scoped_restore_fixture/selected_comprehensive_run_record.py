"""Static source-pinned selected definitions; checked by verifier before import."""
import json
import hashlib
from typing import Any
from collections.abc import Mapping
from nico.report_delivery_timing_v1 import report_delivery_phase
from selected_comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from selected_strategic_human_evidence_v1 import VERSION as HUMAN_EVIDENCE_VERSION, verify_strategic_human_evidence
VERSION = 'nico.comprehensive_run_record.v5'
LEGACY_VERSION = 'nico.comprehensive_run_record.v2'
TERMINAL_STATUSES = {'review_required', 'approved', 'rejected', 'failed', 'blocked'}
_HASH_BATCH_BYTES = 64 * 1024
_HASH_NATIVE_NODE_LIMIT = 8192
_HASH_NATIVE_BYTES_LIMIT = 1024 * 1024

def _bounded_native_json(value: Any, *, max_depth: int=64) -> bool:
    """Limit native encoding to small plain-JSON subtrees, including escaped bytes."""
    pending = [value]
    depths = [0]
    nodes_left = _HASH_NATIVE_NODE_LIMIT
    bytes_left = _HASH_NATIVE_BYTES_LIMIT
    while pending:
        item = pending.pop()
        depth = depths.pop()
        nodes_left -= 1
        if nodes_left < 0:
            return False
        kind = type(item)
        if kind in (dict, list, tuple) and depth >= max_depth:
            return False
        if kind is dict:
            if len(pending) + 2 * len(item) > nodes_left:
                return False
            if any((type(key) is not str for key in item)):
                return False
            bytes_left -= 2 + 2 * len(item)
            pending_before = len(pending)
            pending.extend(item.keys())
            pending.extend(item.values())
            depths.extend([depth + 1] * (len(pending) - pending_before))
        elif kind in (list, tuple):
            if len(pending) + len(item) > nodes_left:
                return False
            bytes_left -= 2 + len(item)
            pending_before = len(pending)
            pending.extend(item)
            depths.extend([depth + 1] * (len(pending) - pending_before))
        elif kind is str:
            bytes_left -= 2 + 6 * len(item)
        elif kind is int:
            bytes_left -= 3 + item.bit_length() // 3
        elif kind is float:
            bytes_left -= 32
        elif kind is bool or item is None:
            bytes_left -= 5
        else:
            return False
        if bytes_left < 0:
            return False
    return True

class _LegacyHashEncodingRequired(Exception):
    pass

def _canonical_hash_chunks(value: Any, encoder: json.JSONEncoder, ancestors: set[int]):
    frames = [('value', value)]
    while frames:
        event, current = frames.pop()
        if event == 'close':
            closing, identity = current
            ancestors.remove(identity)
            yield closing
            continue
        if event in ('dict_items', 'list_items'):
            iterator, index = current
            try:
                item = next(iterator)
            except StopIteration:
                continue
            frames.append((event, (iterator, index + 1)))
            if index:
                yield ','
            if event == 'dict_items':
                key, item = item
                yield encoder.encode(key)
                yield ':'
            frames.append(('value', item))
            continue
        kind = type(current)
        if kind is str:
            yield encoder.encode(current)
            continue
        if kind is int:
            yield str(current)
            continue
        if kind is bool:
            yield ('true' if current else 'false')
            continue
        if current is None:
            yield 'null'
            continue
        if kind not in (float, dict, list, tuple) or (kind is dict and any((type(key) is not str for key in current))) or len(ancestors) >= 64:
            raise _LegacyHashEncodingRequired
        if _bounded_native_json(current, max_depth=64 - len(ancestors)):
            yield from encoder.iterencode(current, _one_shot=True)
            continue
        identity = id(current)
        if identity in ancestors:
            raise ValueError('Circular reference detected')
        ancestors.add(identity)
        if kind is dict:
            yield '{'
            frames.append(('close', ('}', identity)))
            frames.append(('dict_items', (iter(sorted(current.items())), 0)))
        else:
            yield '['
            frames.append(('close', (']', identity)))
            frames.append(('list_items', (iter(current), 0)))

@report_delivery_phase('record_integrity_hash')
def _canonical_hash(payload: Any) -> str:
    """Preserve canonical bytes with bounded native encoding and digest batching."""
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    digest = hashlib.sha256()
    pending = bytearray()
    try:
        for chunk in _canonical_hash_chunks(payload, encoder, set()):
            encoded = chunk.encode('utf-8')
            if len(encoded) >= _HASH_BATCH_BYTES:
                if pending:
                    digest.update(pending)
                    pending.clear()
                digest.update(encoded)
            else:
                if len(pending) + len(encoded) > _HASH_BATCH_BYTES:
                    digest.update(pending)
                    pending.clear()
                pending.extend(encoded)
    except _LegacyHashEncodingRequired:
        digest = hashlib.sha256()
        for chunk in encoder.iterencode(payload):
            digest.update(chunk.encode('utf-8'))
        return digest.hexdigest()
    if pending:
        digest.update(pending)
    return digest.hexdigest()

def _record_hash(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != 'integrity_sha256'}
    return _canonical_hash(payload)

def _validate_record(record: dict[str, Any], *, require_strategic_context: bool) -> list[str]:
    violations: list[str] = []
    identity = record.get('identity') if isinstance(record.get('identity'), dict) else {}
    fields = ['run_id', 'repository', 'commit_sha', 'evidence_ledger_id', 'customer_id', 'project_id']
    if require_strategic_context:
        fields.extend(['assessment_depth', 'report_language'])
    for field in fields:
        if not str(identity.get(field) or '').strip():
            violations.append(f'{field}_required')
    if record.get('service_id') != 'comprehensive':
        violations.append('service_id_must_be_comprehensive')
    if record.get('human_review_required') is not True:
        violations.append('human_review_required')
    status = str(record.get('status') or '').lower()
    delivery_allowed = record.get('client_delivery_allowed') is True
    if status == 'approved':
        if record.get('human_review_completed') is not True:
            violations.append('approved_run_requires_completed_review')
        review_errors = _review_manifest_errors(record, record.get('accepted_edition'))
        violations.extend((f'accepted_edition:{item}' for item in review_errors))
        if delivery_allowed:
            accepted = record.get('accepted_edition') if isinstance(record.get('accepted_edition'), Mapping) else {}
            if accepted.get('client_delivery_allowed') is not False:
                violations.append('approved_delivery_accepted_edition_must_remain_immutable')
            if str(accepted.get('delivery_status') or '') != 'pending_authorization':
                violations.append('approved_delivery_accepted_edition_status_changed')
            try:
                from nico.comprehensive_delivery_authorization_v1 import validate_delivery_authorization
                authorization_validation = validate_delivery_authorization(record, accepted, record.get('delivery_authorization'))
                violations.extend((f'delivery_authorization:{item}' for item in authorization_validation.get('validation_errors') or []))
            except (TypeError, ValueError) as exc:
                violations.append('delivery_authorization:validation_failed:' + str(exc).split(':', 1)[0])
            if not isinstance(record.get('approved_delivery_package'), Mapping):
                violations.append('approved_delivery_package_required')
    elif delivery_allowed:
        from nico.comprehensive_operator_delivery_v1 import validated_operator_delivery
        if not validated_operator_delivery(record):
            violations.append('client_delivery_must_remain_blocked')
    review_decision = record.get('review_decision')
    review_history_value = record.get('review_history')
    review_history = review_history_value if isinstance(review_history_value, list) else []
    if review_history_value is not None and (not isinstance(review_history_value, list)):
        violations.append('review_history_invalid')
    if review_history:
        final_history_entry = review_history[-1]
        if not isinstance(review_decision, Mapping):
            violations.append('review_history_requires_review_decision')
        elif not isinstance(final_history_entry, Mapping) or dict(final_history_entry) != dict(review_decision):
            violations.append('review_decision_history_mismatch')
    if status in {'approved', 'rejected'}:
        if not review_history:
            violations.append(f'{status}_review_history_required')
        if not isinstance(review_decision, Mapping):
            violations.append(f'{status}_review_decision_required')
    if review_decision is not None:
        review_errors = _review_manifest_errors(record, review_decision)
        violations.extend((f'review_decision:{item}' for item in review_errors))
        review_decision_mapping = review_decision if isinstance(review_decision, Mapping) else {}
        review = review_decision_mapping.get('review')
        review = review if isinstance(review, Mapping) else {}
        decision = str(review.get('decision') or '').casefold()
        expected_status = {'approved': 'approved', 'rejected': 'rejected', 'request_more_evidence': 'review_required'}.get(decision)
        if expected_status and status != expected_status:
            violations.append('review_decision_status_mismatch')
        if not review_history:
            violations.append('review_decision_history_required')
        else:
            final_history_entry = review_history[-1]
            if not isinstance(final_history_entry, Mapping) or dict(final_history_entry) != dict(review_decision_mapping):
                violations.append('review_decision_history_mismatch')
        accepted = record.get('accepted_edition')
        if decision == 'approved':
            if not isinstance(accepted, Mapping) or dict(accepted) != dict(review_decision_mapping):
                violations.append('approved_accepted_edition_history_mismatch')
        elif isinstance(accepted, Mapping):
            violations.append('nonapproval_must_not_retain_accepted_edition')
    accepted = record.get('accepted_edition')
    if status == 'approved' and isinstance(accepted, Mapping):
        if not review_history or not isinstance(review_history[-1], Mapping) or dict(accepted) != dict(review_history[-1]):
            violations.append('approved_accepted_edition_history_mismatch')
    if require_strategic_context:
        human_evidence = record.get('human_evidence')
        if not isinstance(human_evidence, dict):
            violations.append('human_evidence_required')
        else:
            if human_evidence.get('artifact_schema') != HUMAN_EVIDENCE_VERSION:
                violations.append('human_evidence_schema_invalid')
            if not verify_strategic_human_evidence(human_evidence):
                violations.append('human_evidence_hash_mismatch')
    completed = list(record.get('completed_stages') or [])
    if completed != list(COMPREHENSIVE_STAGES[:len(completed)]):
        violations.append('completed_stages_must_be_ordered_prefix')
    if len(set(completed)) != len(completed):
        violations.append('duplicate_completed_stages')
    expected_progress = round(len(completed) / len(COMPREHENSIVE_STAGES) * 100, 2)
    if float(record.get('progress_percent') or 0.0) != expected_progress:
        violations.append('progress_must_match_completed_stages')
    if record.get('integrity_sha256') != _record_hash(record):
        violations.append('integrity_hash_mismatch')
    terminal = status in TERMINAL_STATUSES
    if bool(record.get('terminal')) != terminal:
        violations.append('terminal_flag_mismatch')
    return violations

def validate_comprehensive_run_record(record: dict[str, Any]) -> dict[str, Any]:
    schema = str(record.get('artifact_schema') or '')
    violations = _validate_record(record, require_strategic_context=schema != LEGACY_VERSION)
    return {'status': 'valid' if not violations else 'invalid', 'violations': violations}
