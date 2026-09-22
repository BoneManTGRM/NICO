"""Original-byte acquisition identities, distinct from decoded report text.

This manifest does not choose a build configuration, execution budget or image.
Only a later qualified internal contract can select its required population.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re


def raw_input_record(raw: bytes) -> dict:
    return {'blob_sha': hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw,
                                    usedforsecurity=False).hexdigest(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def matches_tree(record: dict, entry: dict) -> bool:
    return (entry.get('type') == 'blob' and entry.get('mode') in {'100644', '100755'}
            and record['blob_sha'] == entry.get('sha')
            and type(entry.get('size')) is int and record['bytes'] == entry['size'])


def execution_input_manifest(profile: dict, snapshot: dict) -> dict:
    """Freeze acquired member identities without promoting missing raw bytes."""
    selected = sorted(set(profile.get('raw_input_selected_paths') or []) | set(profile.get('files') or {}))
    records = profile.get('raw_input_records') or {}
    excluded = (set(profile.get('symlink_paths_not_followed') or [])
        | {row['path'] for row in profile.get('submodule_entries') or []}
        | {row['path'] for row in profile.get('lfs_pointer_entries') or []})
    members = {path: deepcopy(records[path]) for path in selected if path in records and path not in excluded}
    commit, tree = snapshot.get('commit_sha', ''), snapshot.get('tree_sha', '')
    identity_verified = (isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{40}', commit) is not None
        and isinstance(tree, str) and re.fullmatch(r'[0-9a-f]{40}', tree) is not None
        and tree == profile.get('tree_sha'))
    inventory_complete = (profile.get('tree_collection_succeeded') is True
                          and profile.get('tree_truncated') is not True)
    missing = sorted(set(selected) - set(members))
    result = {'schema': 'nico.snapshot-execution-inputs.v1',
        'snapshot_commit_sha': commit, 'snapshot_tree_sha': tree,
        'snapshot_identity_verified': identity_verified, 'inventory_complete': inventory_complete,
        'inventory_paths': sorted(set(profile.get('tree_paths') or [])),
        'selected_paths': selected, 'members': members, 'unverified_paths': missing,
        'excluded_paths': sorted(excluded), 'selected_bytes': sum(row['bytes'] for row in members.values()),
        'selected_population_verified': bool(selected and identity_verified and inventory_complete and not missing
                                             and set(selected) <= set(profile.get('tree_paths') or [])),
        'assessment_contract_selected': False,
        'scope': 'Acquisition identities for selected report inputs; no execution or whole-repository assessment claim.'}
    result['manifest_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result
