"""Bounded lockfile identity assistance; never installed-state or safety verdicts."""
import hashlib
import json
import re
from collections.abc import Mapping
from nico.candidate_source_observations_v1 import candidate_source_path
VERSION = 'nico.dependency-lock-identity.v1'
SCOPE = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')
NAME = re.compile(r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+\Z')
SEMVER = re.compile(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z')


ROOT_VERSION = 'nico.lockfile-root-declaration.v1'
ROOT_ROLES = ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies')


def _root_declarations(root):
    # Literal lockfile metadata only. Never interpret ranges, installation or use.
    if not isinstance(root, dict):
        return None
    declarations = {}
    for role in ROOT_ROLES:
        if role not in root:
            continue
        group = root[role]
        if not isinstance(group, dict) or len(group) > 4096:
            return None
        for name, spec in group.items():
            if (not isinstance(name, str) or len(name) > 214 or not NAME.fullmatch(name) or name in ('.', '..')
                    or not isinstance(spec, str) or not spec or len(spec) > 1024
                    or spec != spec.strip() or spec.startswith('npm:')
                    or any(ord(c) < 32 for c in spec)):
                return None
            declarations.setdefault(name, []).append(role)
            if len(declarations) > 4096:
                return None
    return {'artifact_schema': ROOT_VERSION, 'declarations': dict(sorted(declarations.items()))} if declarations else None


def _qualified_root_declaration(observation, name, location):
    value = observation.get('root_declarations')
    if (location != 'node_modules/' + name or not isinstance(value, Mapping)
            or set(value) != {'artifact_schema', 'declarations'} or value.get('artifact_schema') != ROOT_VERSION):
        return None
    declarations = value.get('declarations')
    if not isinstance(declarations, Mapping) or len(declarations) > 4096:
        return None
    for package, roles in declarations.items():
        if (not isinstance(package, str) or len(package) > 214 or not NAME.fullmatch(package) or package in ('.', '..')
                or not isinstance(roles, list) or not roles or len(roles) > 4
                or any(not isinstance(r, str) or r not in ROOT_ROLES for r in roles)
                or roles != [r for r in ROOT_ROLES if r in roles]):
            return None
    roles = declarations.get(name)
    return {'artifact_schema': ROOT_VERSION, 'roles': list(roles)} if roles else None


def request(finding, path):
    ecosystems = [finding[k] for k in ('ecosystem', 'osv_scanned_ecosystem') if k in finding]
    if any(not isinstance(e, str) or e.lower() != 'npm' for e in ecosystems):
        return None
    names = [finding[k] for k in ('package', 'package_name', 'osv_scanned_package', 'scanned_package_name') if k in finding]
    versions = [finding[k] for k in ('installed_version', 'resolved_version', 'osv_scanned_version') if k in finding]
    if not names or any(not isinstance(n, str) or len(n) > 214 or not NAME.fullmatch(n) for n in names) or len(set(names)) != 1:
        return None
    if any(not isinstance(v, str) or len(v) > 128 or not SEMVER.fullmatch(v) for v in versions) or len(set(versions)) > 1:
        return None
    path = candidate_source_path(path)
    if path is None or '.git' in path.split('/') or path.split('/')[-1] != 'package-lock.json':
        return None
    return {'package': names[0], 'lockfile_path': path, 'claimed_version': versions[0] if versions else None}


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate_json_key')
        out[key] = value
    return out


def observe(data, *, scope, path, blob_oid):
    if not isinstance(data, bytes) or len(data) > 262144:
        return {'status': 'unavailable'}
    if (not all(scope.get(k) for k in SCOPE) or not re.fullmatch('[a-f0-9]{40}', str(scope.get('commit_sha', '')))
            or candidate_source_path(path) != path or path.split('/')[-1] != 'package-lock.json'
            or '.git' in path.split('/') or hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data, usedforsecurity=False).hexdigest() != blob_oid):
        return {'status': 'unavailable'}
    try:
        lock = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs)
        if not isinstance(lock, dict) or type(lock.get('lockfileVersion')) is not int or lock['lockfileVersion'] not in (2, 3):
            raise ValueError('unsupported_lockfile')
        packages = lock.get('packages')
        if not isinstance(packages, dict) or len(packages) > 4096:
            raise ValueError('package_inventory_unavailable')
        entries = []
        for location, item in packages.items():
            if location == '':
                continue
            if candidate_source_path(location) != location or '.git' in location.split('/') or not re.search(r'(^|/)node_modules/', location) or not isinstance(item, dict):
                raise ValueError('invalid_package_entry')
            name = location.rsplit('node_modules/', 1)[1]
            version = item.get('version')
            if not NAME.fullmatch(name) or len(name) > 214 or name in ('.', '..'):
                raise ValueError('invalid_package_name')
            if (not NAME.fullmatch(name) or len(name) > 214 or item.get('link') or item.get('name', name) != name
                    or not isinstance(version, str) or len(version) > 128 or not SEMVER.fullmatch(version)):
                entries.append({'package': name if len(name) <= 214 else '', 'unsupported': True})
            else:
                entries.append({'package': name, 'locked_version': version, 'package_path': location})
        root = _root_declarations(packages.get(''))
        return {**({'root_declarations': root} if root else {}), 'artifact_schema': VERSION, 'status': 'observed', 'scope': dict(scope), 'origin': 'verified_git_blob',
                'path': path, 'blob_oid': blob_oid, 'source_sha256': hashlib.sha256(data).hexdigest(), 'entries': entries}
    except (ValueError, UnicodeError, TypeError, RecursionError):
        return {'artifact_schema': VERSION, 'status': 'unavailable'}


def qualify(row, observation, scope):
    req = row.get('dependency_identity_request')
    if not isinstance(req, Mapping) or request({'package': req.get('package'), **({'installed_version': req['claimed_version']} if req.get('claimed_version') is not None else {})}, req.get('lockfile_path')) != req:
        return None
    if (not all(scope.get(k) for k in SCOPE)
            or any(k in row and row[k] != scope[k] for k in ('run_id', 'customer_id', 'project_id'))
            or row.get('exact_commit_sha') != scope['commit_sha']
            or row.get('source_commit_sha', scope['commit_sha']) not in ('', scope['commit_sha'])
            or row.get('source_repository', scope['repository']) not in ('', scope['repository'])
            or candidate_source_path(row.get('source_path')) != req['lockfile_path']):
        return None
    if (not isinstance(observation, Mapping) or observation.get('artifact_schema') != VERSION
            or observation.get('status') != 'observed' or observation.get('scope') != scope
            or observation.get('origin') != 'verified_git_blob' or observation.get('path') != req['lockfile_path']
            or not re.fullmatch('[a-f0-9]{64}', str(observation.get('source_sha256', '')))
            or not re.fullmatch('[a-f0-9]{40}', str(observation.get('blob_oid', '')))):
        return None
    entries = observation.get('entries')
    if not isinstance(entries, list) or len(entries) > 4096:
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            return None
        name = entry.get('package')
        if not isinstance(name, str) or len(name) > 214 or not NAME.fullmatch(name) or name in ('.', '..'):
            return None
        if entry.get('unsupported') is True:
            if set(entry) != {'package', 'unsupported'}:
                return None
        else:
            location, version = entry.get('package_path'), entry.get('locked_version')
            if (set(entry) != {'package', 'package_path', 'locked_version'}
                    or not isinstance(location, str) or len(location) > 1024 or candidate_source_path(location) != location
                    or '.git' in location.split('/') or not (location == 'node_modules/' + name or location.endswith('/node_modules/' + name))
                    or not isinstance(version, str) or len(version) > 128 or not SEMVER.fullmatch(version)):
                return None
    matches = [e for e in entries if e.get('package') == req['package']]
    if len(matches) != 1:
        return None
    item = matches[0]
    version, location = item.get('locked_version'), item.get('package_path')
    if (item.get('unsupported') or not isinstance(version, str) or len(version) > 128 or not SEMVER.fullmatch(version)
            or not isinstance(location, str) or len(location) > 1024 or candidate_source_path(location) != location
            or '.git' in location.split('/') or not (location == 'node_modules/' + req['package'] or location.endswith('/node_modules/' + req['package']))
            or req['claimed_version'] not in (None, version)):
        return None
    root = _qualified_root_declaration(observation, req['package'], location)
    return {**({'root_declaration': root} if root else {}), 'artifact_schema': VERSION, 'package': req['package'], 'locked_version': version, 'ecosystem': 'npm',
            'lockfile_path': req['lockfile_path'], 'package_path': location, 'source_sha256': observation['source_sha256'],
            'blob_oid': observation['blob_oid'], 'scope': dict(scope), 'installed_state': 'unknown',
            'affectedness': 'unknown', 'reachability': 'unknown'}


def retained_capture(record):
    """Use only existing server-persisted stage evidence; never acquire on GET."""
    stages = record.get('stage_results')
    if not isinstance(stages, Mapping):
        return None
    scoring = stages.get('evidence_reconciliation_and_scoring')
    if isinstance(scoring, Mapping) and 'candidate_source_observations' in scoring:
        return scoring['candidate_source_observations']
    stage = stages.get('repository_and_delivery_evidence')
    repo = stage.get('repository_evidence') if isinstance(stage, Mapping) else None
    return repo.get('candidate_source_observations') if isinstance(repo, Mapping) else None


def next_step(row, capture, scope, *, qualified):
    """Authored guidance from retained state, never a diagnosis or new analysis."""
    if qualified:
        return 'verify_installation_and_use'
    req = row.get('dependency_identity_request')
    if not isinstance(req, Mapping) or request({'package': req.get('package'), **({'installed_version': req['claimed_version']} if req.get('claimed_version') is not None else {})}, req.get('lockfile_path')) != req:
        return 'supply_scanner_identity'
    if (row.get('exact_commit_sha') != scope.get('commit_sha')
            or row.get('source_commit_sha', scope.get('commit_sha')) not in ('', scope.get('commit_sha'))
            or row.get('source_repository', scope.get('repository')) not in ('', scope.get('repository'))
            or any(k in row and row[k] != scope.get(k) for k in ('run_id', 'customer_id', 'project_id'))
            or candidate_source_path(row.get('source_path')) != req['lockfile_path']):
        return 'supply_current_capture'
    if (not isinstance(capture, Mapping) or capture.get('artifact_schema') != 'nico.persisted-candidate-investigation.v1'
            or capture.get('scope') != scope or not all(scope.get(k) for k in SCOPE)):
        return 'supply_current_capture'
    observations = capture.get('observations')
    observation = observations.get(req['lockfile_path']) if isinstance(observations, Mapping) else None
    if not isinstance(observation, Mapping):
        return 'supply_lockfile_observation'
    if observation.get('status') != 'observed':
        return 'inspect_lockfile_capture'
    if (observation.get('artifact_schema') != VERSION or observation.get('scope') != scope
            or observation.get('path') != req['lockfile_path'] or observation.get('origin') != 'verified_git_blob'):
        return 'supply_current_capture'
    # Missing receipt can also mean a budget boundary, stale proof or unsupported
    # inventory. Do not turn the existence of an observation into an attempt claim.
    return 'reconcile_lockfile_identity'
