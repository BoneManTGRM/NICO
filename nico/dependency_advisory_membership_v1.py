"""Positive explicit-list observations, never installed affectedness or clearance."""
from collections.abc import Mapping
import hashlib
import json
import math
import re
import time
from nico import dependency_identity_evidence_v1 as identity

VERSION = 'nico.dependency-advisory-explicit-membership.v1'
RESULT_LIMIT = 1048576
CAPTURE_LIMIT = 262144
RECORD_LIMIT = 128
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def key(row):
    return digest({'fingerprint': row.get('raw_fingerprint'), 'request': row.get('dependency_identity_request'),
                   'scanner': row.get('scanner'), 'source_path': row.get('source_path'), 'rule_id': row.get('rule_id')})


def _bounded_json(value, *, deadline, clock):
    # Conservative upper bound before JSON escaping/sorting allocates output.
    # Containers are ordinary parsed JSON only; no custom iterators/default repr.
    stack, nodes, upper = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 8192 or depth > 32 or (nodes % 128 == 1 and clock() >= deadline):
            return False
        if type(item) is dict:
            if len(item) > 8192 or nodes + len(stack) + 2 * len(item) > 8192:
                return False
            upper += 2 + 2 * len(item)
            for key, child in item.items():
                if type(key) is not str:
                    return False
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(item) is list:
            if len(item) > 8192 or nodes + len(stack) + len(item) > 8192:
                return False
            upper += 2 + len(item)
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > 16384:
                return False
            upper += 2 + 12 * len(item)
        elif item is None or type(item) is bool:
            upper += 5
        elif type(item) is int and -(2**63) <= item < 2**63:
            upper += 21
        elif type(item) is float and math.isfinite(item):
            upper += 32
        else:
            return False
        if upper > RESULT_LIMIT:
            return False
    return clock() < deadline


def verified_result(result, scope, *, deadline=float('inf'), clock=time.monotonic):
    """Validate the existing persisted-result commitment without reading its store."""
    from nico.scanner_raw_artifact_storage_v1 import binding_from_record, _artifact_id
    if not isinstance(result, Mapping) or result.get('status') != 'completed' or result.get('scanner_name') != 'osv-scanner':
        return None, 0
    if not _bounded_json(result, deadline=deadline, clock=clock):
        return None, RESULT_LIMIT
    if (result.get('timed_out') is not False or result.get('output_limit_exceeded') is not False
            or result.get('output_capture_complete') is not True or result.get('returncode_valid') is not True
            or result.get('verified_for_this_report') is not True):
        return None, 0
    binding = binding_from_record(result)
    artifact = result.get('raw_artifact')
    durability = result.get('raw_artifact_durability')
    if (binding is None or any(binding.get(k) != scope.get(k) for k in identity.SCOPE)
            or not isinstance(artifact, Mapping) or artifact.get('storage_backend') != 'postgres'
            or artifact.get('artifact_id') != _artifact_id(binding) or not HEX.fullmatch(str(artifact.get('sha256','')))
            or result.get('raw_artifact_retention_complete') is not True
            or not isinstance(durability, Mapping) or durability.get('status') != 'persisted'
            or durability.get('original_compressed_bytes_preserved') is not True):
        return None, 0
    hasher, size = hashlib.sha256(), 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':'), default=str).iterencode({k:v for k,v in result.items() if k != 'artifact_hash'}):
            if clock() >= deadline:
                return None, RESULT_LIMIT
            data=chunk.encode(); size+=len(data)
            if size > RESULT_LIMIT:
                return None, RESULT_LIMIT
            hasher.update(data)
    except (ValueError, TypeError, RecursionError):
        return None, min(size, RESULT_LIMIT)
    if hasher.hexdigest() != result.get('artifact_hash'):
        return None, size
    return {'scanner_artifact_id':artifact['artifact_id'], 'scanner_raw_sha256':artifact['sha256'],
            'scanner_result_sha256':result['artifact_hash']}, size


def observe(raw, row, scope, proof):
    req=row.get('dependency_identity_request')
    advisory_id=raw.get('id')
    affected=raw.get('affected')
    if (row.get('category') != 'dependency' or row.get('scanner') != 'osv-scanner'
            or not isinstance(req, Mapping) or not isinstance(advisory_id,str) or not ID.fullmatch(advisory_id)
            or row.get('rule_id') != advisory_id or raw.get('withdrawn')
            or raw.get('scanner_context_schema') != 'nico.osv-scanner-context-patch.v1'
            or not isinstance(affected,list) or len(affected)!=1):
        return None
    entry=affected[0]
    if not isinstance(entry,Mapping) or entry.get('package') != {'name':req['package'],'ecosystem':'npm'}:
        return None
    versions=entry.get('versions')
    if (not isinstance(versions,list) or not 1 <= len(versions) <= 256
            or any(not isinstance(v,str) or len(v)>128 or not identity.SEMVER.fullmatch(v) for v in versions)
            or len(set(versions)) != len(versions)):
        return None
    selected={'advisory_id':advisory_id,'package':req['package'],'ecosystem':'npm','versions':sorted(versions)}
    return {'artifact_schema':VERSION,'scope':dict(scope),'candidate_key':key(row), **selected,
            'selected_evidence_sha256':digest(selected), **proof}


def capture(results, scope, normalize, *, deadline, clock=time.monotonic):
    observations, conflicts, charged, attempts = {}, set(), 0, 0
    if not isinstance(results, list) or len(results) > 64:
        return {}, 0, 0
    candidates = [r for r in results if isinstance(r, Mapping) and (r.get('scanner_name') or r.get('tool')) == 'osv-scanner']
    if len(candidates) != 1 or not isinstance(candidates[0].get('findings'), list) or len(candidates[0]['findings']) > RECORD_LIMIT or any(not isinstance(f, Mapping) for f in candidates[0]['findings']):
        return {}, 0, 0
    results = candidates
    for result in results:
        if clock() >= deadline or attempts >= RECORD_LIMIT or charged >= RESULT_LIMIT:
            break
        proof,size=verified_result(result,scope,deadline=deadline,clock=clock)
        charged+=size
        if charged > RESULT_LIMIT or clock() >= deadline:
            break
        if proof is None:
            continue
        findings=result.get('findings')
        if not isinstance(findings,list):
            continue
        for raw in findings:
            if attempts >= RECORD_LIMIT or clock() >= deadline:
                break
            attempts+=1
            if not isinstance(raw,Mapping):
                continue
            row=normalize(commit_sha=scope['commit_sha'],scanner='osv-scanner',category='dependency',finding=raw)
            k=key(row)
            observation=observe(raw,row,scope,proof)
            # A second conflicting or unsupported record for the same claim
            # invalidates the mapping. Never select by occurrence order.
            if k in observations and observations[k] != observation:
                conflicts.add(k)
            if observation is None:
                conflicts.add(k)
            elif k not in conflicts:
                observations[k]=observation
    for k in conflicts:
        observations.pop(k,None)
    if len(json.dumps(observations).encode()) > CAPTURE_LIMIT or clock() >= deadline:
        observations={}
    return observations, min(charged, RESULT_LIMIT), attempts


def qualify(row, locked, capture, scope):
    if (not isinstance(locked, Mapping) or locked.get('scope') != scope or locked.get('artifact_schema') != identity.VERSION
            or not isinstance(capture, Mapping) or capture.get('scope') != scope):
        return None
    values=capture.get('dependency_advisory_observations')
    if not isinstance(values,Mapping) or len(values)>RECORD_LIMIT:
        return None
    observation=values.get(key(row))
    if (not isinstance(observation,Mapping) or observation.get('artifact_schema')!=VERSION
            or observation.get('scope')!=scope or observation.get('candidate_key')!=key(row)
            or observation.get('package')!=locked.get('package') or observation.get('ecosystem')!='npm'
            or observation.get('advisory_id')!=row.get('rule_id') or not ID.fullmatch(str(observation.get('advisory_id','')))):
        return None
    versions=observation.get('versions')
    if (not isinstance(versions,list) or not 1<=len(versions)<=256
            or any(not isinstance(v,str) or len(v)>128 or not identity.SEMVER.fullmatch(v) for v in versions)
            or len(set(versions))!=len(versions)):
        return None
    selected={k:observation[k] for k in ('advisory_id','package','ecosystem','versions')}
    if observation.get('selected_evidence_sha256')!=digest(selected):
        return None
    if (any(not HEX.fullmatch(str(observation.get(k,''))) for k in ('scanner_raw_sha256','scanner_result_sha256'))
            or not re.fullmatch('scanartifact_[a-f0-9]{64}',str(observation.get('scanner_artifact_id','')))
            or locked.get('locked_version') not in versions):
        return None
    return {'artifact_schema':VERSION,'status':'explicitly_listed','advisory_id':observation['advisory_id'],
            'package':locked['package'],'locked_version':locked['locked_version'],
            'scope':dict(scope),'lockfile_source_sha256':locked['source_sha256'],
            **{k:observation[k] for k in ('selected_evidence_sha256','scanner_raw_sha256','scanner_result_sha256','scanner_artifact_id')},
            'installed_affectedness':'unknown','reachability':'unknown','disposition_effect':'none'}
