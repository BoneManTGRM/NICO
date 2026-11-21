"""Materialize missing configured inputs through bound CMake utility targets.

Native reconstruction is inert. Only the controller invokes the selected
public CMake targets inside its existing worker and remaining build budget.
Existence, generation, compilation and analyzer visitation remain distinct.
"""
from __future__ import annotations

import errno
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import stat

from nico.assessment_cpp_native_commands import _decode_files, _target_directories
from nico.assessment_cpp_fileapi_membership import _json
from nico.assessment_cpp_project_snapshot import (
    _project_request, PROJECT_GENERATED_MAX_FILE_BYTES, PROJECT_GENERATED_STREAM_LIMIT,
)

OBSERVATION_SCHEMA = 'nico.cpp-generated-input-observation.v1'
PLAN_SCHEMA = 'nico.cpp-generated-input-plan.v1'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(value):
    if not value:
        raise ValueError('worker_generated_input_evidence_invalid')


def observe_generated_inputs(root, request):
    """Readability metadata via no-follow descriptors; only ENOENT is missing.

    The embedded worker entry point requires analyst1001. This function also
    supports explicit owned roots for bounded development controls. No file
    bodies, host error strings or secrets enter the returned observation.
    """
    _project_request(request)
    root = Path(root)
    _require(root.is_absolute() and not root.is_symlink() and root.resolve(strict=True) == root)
    files = {}
    for name in request['generated_units']:
        descriptors = []
        try:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(fd)
            parts = name.split('/')
            for part in parts[:-1]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                descriptors.append(fd)
            info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and 0 <= info.st_size <= PROJECT_GENERATED_MAX_FILE_BYTES)
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            descriptors.append(file_fd)
            before = os.fstat(file_fd)
            _require((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_nlink)
                == (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_nlink))
            os.read(file_fd, 1)  # Permission/readability, not a byte snapshot or hash.
            after = os.fstat(file_fd)
            _require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
            files[name] = {'state': 'readable', 'errno': None, 'bytes': after.st_size,
                'links': after.st_nlink, 'mode': stat.S_IMODE(after.st_mode)}
        except OSError as exc:
            files[name] = {'state': 'missing' if exc.errno == errno.ENOENT else 'unavailable',
                'errno': exc.errno, 'bytes': None, 'links': None, 'mode': None}
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
    return {'schema': OBSERVATION_SCHEMA, 'request_sha256': _sha(_canonical(request)),
        'uid': os.getuid(), 'gid': os.getgid(), 'files': files}


def validate_observation(value, request, *, analyst=True):
    _project_request(request)
    _require(isinstance(value, dict) and set(value) == {'schema', 'request_sha256', 'uid', 'gid', 'files'}
        and value['schema'] == OBSERVATION_SCHEMA and value['request_sha256'] == _sha(_canonical(request))
        and type(value['uid']) is int and type(value['gid']) is int
        and (not analyst or (value['uid'], value['gid']) == (1001, 1001))
        and isinstance(value['files'], dict) and set(value['files']) == set(request['generated_units']))
    for row in value['files'].values():
        _require(isinstance(row, dict) and set(row) == {'state', 'errno', 'bytes', 'links', 'mode'})
        if row['state'] == 'readable':
            _require(row['errno'] is None and type(row['bytes']) is int
                and 0 <= row['bytes'] <= PROJECT_GENERATED_MAX_FILE_BYTES
                and type(row['links']) is int and row['links'] == 1
                and type(row['mode']) is int and 0 <= row['mode'] <= 0o7777)
        else:
            _require(row['state'] in {'missing', 'unavailable'} and type(row['errno']) is int
                and row['errno'] > 0 and all(row[k] is None for k in ('bytes', 'links', 'mode'))
                and (row['state'] == 'missing') is (row['errno'] == errno.ENOENT))
    return value


def _rules(raw):
    """Prerequisites only, after the existing complete native Make validation."""
    result, recipes, current = {}, set(), None
    for line in re.sub(r'\\\n[ \t]*', ' ', raw.decode('utf-8', 'strict')).splitlines():
        if line.startswith('\t'):
            if current and not line.startswith('\t@$(CMAKE_COMMAND) -E cmake_echo_color '):
                recipes.add(current)
            continue
        current = None
        if not line or line.startswith(('#', '.', '%', '$')) or ':' not in line or ' = ' in line:
            continue
        target, dependencies = line.split(':', 1)
        target = target.strip()
        _require(re.fullmatch(r'[A-Za-z0-9_./+-]+', target) is not None
            and ':' not in dependencies and not any(c in dependencies for c in '$;`\\'))
        values = dependencies.split()
        _require(all(re.fullmatch(r'[A-Za-z0-9_./+-]+', p) is not None for p in values))
        result.setdefault(target, set()).update(values)
        current = target
    return result, recipes


def generated_input_plan(native_raw, fileapi_raw, membership, native_plan, request, observation, *, analyst=True):
    """Select utility targets whose declared output graph covers missing inputs.

    Callers reconstruct membership/native_plan with the existing verifier first.
    Target names or FileAPI source fragments alone never confer output ownership.
    """
    validate_observation(observation, request, analyst=analyst)
    native, fileapi = _json(native_raw), _json(fileapi_raw)
    _require(native_plan['native_capture_sha256'] == _sha(native_raw)
        and membership['capture_sha256'] == native_plan['fileapi_capture_sha256'] == _sha(fileapi_raw)
        and native['fileapi_capture_sha256'] == _sha(fileapi_raw)
        and native['database_sha256'] == native_plan['original_database_sha256']
        and native['cache_sha256'] == native_plan['configuration_cache_sha256'] == membership['configuration_cache_sha256']
        and native['source_root'] == membership['source_root'] and native['build_root'] == membership['build_root']
        and request['database_sha256'] == native_plan['analysis_database_sha256']
        and request['source_population_sha256'] == native_plan['source_population_sha256'])
    build = membership['build_root']
    required = sorted({c['file'][len(build) + 1:] for c in native_plan['contexts']
        if c['file'].startswith(build + '/')})
    _require(required == request['generated_units'])
    # Do not regenerate to bypass denied/nonregular/unknown input access.
    _require(all(row['state'] in {'missing', 'readable'} for row in observation['files'].values()))
    missing = {p for p, row in observation['files'].items() if row['state'] == 'missing'}
    files = _decode_files(native)
    top_rules, _ = _rules(files['Makefile'])
    models = {_json(raw).get('id'): _json(raw) for raw in _decode_files(fileapi).values() if _json(raw).get('type') == 'UTILITY'}
    candidates = []
    for target_id, directory in _target_directories(fileapi, membership).items():
        if directory['compiled']:
            continue
        name = models[target_id]['name']
        _require(name in top_rules)
        rules, recipes = _rules(files[directory['relative'] + '/build.make'])
        _require(name in rules and directory['relative'] + '/build' in rules
            and name in rules[directory['relative'] + '/build'])
        visited, pending = set(), [name]
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            _require(len(visited) <= 40000)
            pending.extend(rules.get(node, ()))
        # Every selected input has a reachable file rule with an actual recipe;
        # secondary outputs can depend on the primary generator's file rule.
        covered = sorted(p for p in missing if p in visited and p in rules and p in recipes)
        if covered:
            candidates.append({'target_id': target_id, 'target_name': name, 'required_outputs': covered,
                'native_build_make_sha256': _sha(files[directory['relative'] + '/build.make'])})
    selected, remaining = [], set(missing)
    while remaining:
        useful = [r for r in candidates if remaining.intersection(r['required_outputs'])]
        _require(useful and len(selected) < 128)
        chosen = min(useful, key=lambda r: (-len(remaining.intersection(r['required_outputs'])), r['target_name'], r['target_id']))
        selected.append(chosen)
        remaining.difference_update(chosen['required_outputs'])
    return {'schema': PLAN_SCHEMA, 'native_capture_sha256': _sha(native_raw),
        'fileapi_capture_sha256': _sha(fileapi_raw), 'request_sha256': _sha(_canonical(request)),
        'before_observation_sha256': _sha(_canonical(observation)), 'required_units': required,
        'missing_units': sorted(missing), 'selected_targets': selected,
        'analysis_executed': False, 'header_coverage_verified': False}


def validate_generation_evidence(raw, native_raw, fileapi_raw, membership, native_plan,
                                 request, operations, image, baseline):
    """Reconstruct output cover, exact worker commands and shared elapsed budget."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= PROJECT_GENERATED_STREAM_LIMIT)
    value = _json(raw)
    _require(isinstance(value, dict) and set(value) == {'schema', 'image_config_digest', 'request',
        'plan', 'before', 'after', 'build_elapsed_ms', 'complete'}
        and value['schema'] == 'nico.cpp-generated-input-evidence.v1'
        and value['image_config_digest'] == image and value['request'] == request)
    before = validate_observation(value['before'], request)
    after = validate_observation(value['after'], request)
    plan = generated_input_plan(native_raw, fileapi_raw, membership, native_plan, request, before)
    _require(value['plan'] == plan and value['complete'] is True
        and all(row['state'] == 'readable' for row in after['files'].values()))
    create = operations['create'][0]['invocation']
    container = create[create.index('--name') + 1]
    observer = ['docker', 'exec', '--user=1001:1001', '--interactive', container,
        'python3', '-I', '-S', '-c', OBSERVE_PROGRAM]
    for key, observed in [('generation-inputs-before', before), ('generation-inputs-after', after)]:
        row, data = operations[key]
        _require(row['invocation'] == observer and row.get('input_sha256') == _sha(_canonical(request))
            and _json(data) == observed)
    expected = {'generation-target-'+str(i).zfill(3) for i in range(len(plan['selected_targets']))}
    _require({k for k in operations if k.startswith('generation-target-')} == expected)
    order=list(operations)
    start,end=order.index('baseline-build'),order.index('post-build-database')
    _require(order[start+1:end]==['generation-inputs-before',
        *('generation-target-'+str(i).zfill(3) for i in range(len(plan['selected_targets']))),
        'generation-inputs-after'])
    duration = operations['baseline-build'][0]['duration_ms']
    for i, target in enumerate(plan['selected_targets']):
        row = operations['generation-target-'+str(i).zfill(3)][0]
        _require(row['invocation'] == ['docker', 'exec', container, 'cmake', '--build', '/work/build',
            '--target', target['target_name'], '--parallel', str(baseline['parallel'])])
        duration += row['duration_ms']
    duration += sum(operations[k][0]['duration_ms'] for k in ('generation-inputs-before', 'generation-inputs-after'))
    _require(type(value['build_elapsed_ms']) is int and duration <= value['build_elapsed_ms'] + 5
        and value['build_elapsed_ms'] <= baseline['build_seconds'] * 1000)
    return value


_PRELUDE = "import errno, hashlib, json, os, re, stat\nfrom pathlib import Path\n"
# Reuse the snapshot's exact request/path validator; keep this small program
# standalone so it can run as1001 without importing assessed packages.
from nico.assessment_cpp_project_snapshot import _project_paths
from nico.assessment_cpp_generated_context import build_directory
OBSERVE_PROGRAM = (_PRELUDE + f"PROJECT_GENERATED_MAX_FILE_BYTES={PROJECT_GENERATED_MAX_FILE_BYTES}\n"
    + f"PROJECT_GENERATED_MAX_FILES=2048\nOBSERVATION_SCHEMA={OBSERVATION_SCHEMA!r}\n"
    + '\n'.join(inspect.getsource(f) for f in (build_directory, _project_paths, _project_request,
        _canonical, _sha, _require, observe_generated_inputs))
    + "\nimport sys\nif (os.getuid(),os.getgid())!=(1001,1001): raise SystemExit('generated_input_identity')\n"
    + "raw=sys.stdin.buffer.read(4194305)\nif len(raw)>4194304: raise SystemExit('generated_input_request_limit')\n"
    + "request=json.loads(raw.decode('utf-8','strict'))\n"
    + "sys.stdout.buffer.write(_canonical(observe_generated_inputs(Path(build_directory(request['configuration'])),request)))\n")
