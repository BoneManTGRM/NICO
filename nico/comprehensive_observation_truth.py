"""Retained runtime observations are distinct from supplied prose and approval.

production_acceptance records refer to retained_runtime_executions by execution_id.
Only exact-source, performed, actual executions with retained results establish an
observation. Independent verification additionally binds that execution's digest.
This projection never interprets supplied human text as execution authority.
"""
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json


def observation_truth(canonical, key):
    empty = {'observed': False, 'verified': False, 'result': None}
    acceptance = canonical.get('production_acceptance') or {}
    record = acceptance.get(key) if isinstance(acceptance, Mapping) else None
    if not isinstance(record, Mapping):
        return empty
    if not isinstance(record.get('execution_id'), str):
        return empty
    executions = canonical.get('retained_runtime_executions') or {}
    execution = executions.get(record.get('execution_id')) if isinstance(executions, Mapping) else None
    if not isinstance(execution, Mapping):
        return empty
    identity = canonical.get('identity') or {}
    if (execution.get('kind') != 'actual' or execution.get('performed') is not True
            or execution.get('scope') != key
            or not identity.get('commit_sha') or not identity.get('repository')
            or execution.get('commit_sha') != identity.get('commit_sha')
            or execution.get('repository') != identity.get('repository')
            or not execution.get('evidence_reference')
            or execution.get('result') not in {'pass', 'fail'}
            or not isinstance(execution.get('retained_results'), (list, dict))
            or not execution.get('retained_results')):
        return empty
    try:
        when = datetime.fromisoformat(execution['observed_at'].replace('Z', '+00:00'))
        if when.tzinfo is None:
            return empty
    except (KeyError, TypeError, ValueError, AttributeError):
        return empty
    digest = sha256(json.dumps(dict(execution), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    verification = record.get('independent_review') or {}
    verified = (isinstance(verification, Mapping)
                and verification.get('status') == 'verified'
                and verification.get('execution_sha256') == digest
                and bool(verification.get('reviewer'))
                and bool(execution.get('observer'))
                and verification.get('reviewer') != execution.get('observer')
                and bool(verification.get('evidence_reference')))
    try:
        reviewed_at = datetime.fromisoformat(verification['reviewed_at'].replace('Z', '+00:00'))
        verified = verified and reviewed_at.tzinfo is not None and reviewed_at >= when
    except (KeyError, TypeError, ValueError, AttributeError):
        verified = False
    return {'observed': True, 'verified': bool(verified), 'result': execution['result'],
            'execution_sha256': digest, 'evidence_reference': execution['evidence_reference'],
            'observed_at': execution['observed_at'], 'commit_sha': execution['commit_sha']}
