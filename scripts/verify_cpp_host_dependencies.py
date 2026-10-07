"""Verify a new isolated CPython3.11 host installation before decoder imports.

Uses only public immutable wheel pins. No fetch, installation, subprocess,
container, native target or historical environment proof is provided here.
"""
from __future__ import annotations

import argparse
import base64
import csv
import email.parser
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys
import sysconfig
import zipfile

MAX_WHEEL = 4 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_ENTRIES = 2048
MAX_PROOF = 1024 * 1024
VERSIONS = {'requests': '2.34.2', 'certifi': '2026.7.22',
            'charset-normalizer': '3.5.2', 'idna': '3.20', 'urllib3': '2.8.0'}
MODULES = {'requests': 'requests', 'certifi': 'certifi',
           'charset-normalizer': 'charset_normalizer', 'idna': 'idna', 'urllib3': 'urllib3'}
WHEEL_PINS = {
    'requests': {'filename': 'requests-2.34.2-py3-none-any.whl', 'bytes': 73075,
        'sha256': '2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0',
        'url': 'https://files.pythonhosted.org/packages/a0/f4/c67b0b3f1b9245e8d266f0f112c500d50e5b4e83cb6f3b71b6528104182a/requests-2.34.2-py3-none-any.whl'},
    'certifi': {'filename': 'certifi-2026.7.22-py3-none-any.whl', 'bytes': 136983,
        'sha256': '62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775',
        'url': 'https://files.pythonhosted.org/packages/0b/a7/71ac2cff56fec219ed242bb11b8efb69fcc4bec75db06fb7bfe35de520e6/certifi-2026.7.22-py3-none-any.whl'},
    'charset-normalizer': {'filename': 'charset_normalizer-3.5.2-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl',
        'bytes': 269972, 'sha256': '211d5a3eb6af8f513b8d4ca19a8c1b7accab1b5f0d3175f9826b03c1a920dc1f',
        'url': 'https://files.pythonhosted.org/packages/e4/ed/cf505d3011ffceb12c2067a7a5d3cfe92b875d4d44bb0ff0d69375e2c184/charset_normalizer-3.5.2-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl'},
    'idna': {'filename': 'idna-3.20-py3-none-any.whl', 'bytes': 69583,
        'sha256': 'ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c',
        'url': 'https://files.pythonhosted.org/packages/58/a2/bb081bab032533a855d44de1d56f8e8426114ff1ba5d1f07a438a0a654f8/idna-3.20-py3-none-any.whl'},
    'urllib3': {'filename': 'urllib3-2.8.0-py3-none-any.whl', 'bytes': 135717,
        'sha256': '0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3',
        'url': 'https://files.pythonhosted.org/packages/92/9d/c4e665119135114480843e7ab388fa94d8480650450e6f8e26b70d323a4c/urllib3-2.8.0-py3-none-any.whl'}
}


class VerificationRejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise VerificationRejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def normalized(name):
    require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.-]+', name), 'distribution_name')
    return re.sub(r'[-_.]+', '-', name).lower()


def unique(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, 'nonfinite_json'))


def regular(path, maximum=MAX_FILE):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and not path.is_symlink(), 'regular_canonical_path')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'regular_file_bound')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and len(raw) == before.st_size and
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'file_changed')
    return raw


def relative(name):
    require(type(name) is str and 0 < len(name) <= 300 and not name.startswith('/')
            and '\\' not in name and '\x00' not in name
            and PurePosixPath(name).as_posix() == name
            and all(part not in {'', '.', '..'} for part in name.split('/')), 'unsafe_wheel_member')
    return name


def record_rows(raw):
    require(0 < len(raw) <= MAX_PROOF, 'record_bound')
    result = {}
    for row in csv.reader(io.StringIO(raw.decode('utf-8', 'strict'), newline='')):
        require(len(row) == 3 and row[0] not in result and row[0], 'record_duplicate_or_shape')
        if row[1]:
            require(re.fullmatch(r'sha256=[A-Za-z0-9_-]{43}', row[1]) is not None
                    and re.fullmatch(r'0|[1-9][0-9]*', row[2]) is not None, 'record_hash_or_size')
            require(int(row[2]) <= MAX_FILE, 'record_file_bound')
        else:
            require(row[2] == '', 'record_unhashed_size')
        result[row[0]] = {'hash': row[1], 'bytes': int(row[2]) if row[2] else None}
        require(len(result) <= MAX_ENTRIES, 'record_entry_bound')
    return result


def verify_record_body(raw, row):
    require(row['hash'].startswith('sha256=') and row['bytes'] == len(raw), 'record_actual_length')
    require(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=') ==
            row['hash'][7:], 'record_actual_hash')


def public_manifest(path, expected_sha256):
    raw = regular(path, MAX_PROOF)
    require(re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None
            and sha(raw) == expected_sha256, 'wheel_manifest_digest')
    value = decode(raw)
    require(value.get('schema') == 'nico.diagnostic.cp311-host-wheels.v1'
            and type(value.get('wheels')) is list and len(value['wheels']) == 5, 'wheel_manifest_schema')
    found = {}
    for row in value['wheels']:
        name = normalized(row['name'])
        require(name in VERSIONS and name not in found and row['version'] == VERSIONS[name]
                and all(row.get(k) == v for k, v in WHEEL_PINS[name].items()), 'wheel_manifest_pin')
        found[name] = row
    require(set(found) == set(VERSIONS), 'wheel_manifest_population')
    return found, sha(raw)


def wheel_contents(path, name):
    require(name in WHEEL_PINS, 'wheel_package')
    raw = regular(path, MAX_WHEEL)
    require(len(raw) == WHEEL_PINS[name]['bytes'] and sha(raw) == WHEEL_PINS[name]['sha256'], 'wheel_digest')
    files, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(len(archive.infolist()) <= MAX_ENTRIES, 'wheel_member_bound')
        seen = set()
        for row in archive.infolist():
            member = relative(row.filename.rstrip('/') if row.is_dir() else row.filename)
            require(member not in seen and not row.flag_bits & 1, 'wheel_duplicate_or_encrypted')
            seen.add(member)
            kind = stat.S_IFMT(row.external_attr >> 16)
            require(kind in {0, stat.S_IFDIR if row.is_dir() else stat.S_IFREG}, 'wheel_special_member')
            if row.is_dir():
                require(row.file_size == 0, 'wheel_directory_size')
                continue
            require(0 <= row.file_size <= MAX_FILE and '.data/' not in member, 'wheel_member_size_or_layout')
            total += row.file_size
            require(total <= MAX_TOTAL, 'wheel_expanded_bound')
            body = archive.read(row)  # CRC verified by zipfile; nothing extracted or executed.
            require(len(body) == row.file_size, 'wheel_member_length')
            files[member] = body
    prefixes = {n.rsplit('/', 1)[0] for n in files if n.endswith('.dist-info/METADATA')}
    require(len(prefixes) == 1, 'wheel_metadata_population')
    dist_info = prefixes.pop()
    parser = email.parser.BytesParser()
    metadata = parser.parsebytes(files[dist_info + '/METADATA'])
    require(metadata.get_all('Name') is not None and len(metadata.get_all('Name')) == 1
            and metadata.get_all('Version') == [VERSIONS[name]]
            and normalized(metadata['Name']) == name, 'wheel_metadata_identity')
    wheel = parser.parsebytes(files[dist_info + '/WHEEL'])
    tags = wheel.get_all('Tag', [])
    expected_tags = (['cp311-cp311-manylinux2014_x86_64', 'cp311-cp311-manylinux_2_17_x86_64',
                      'cp311-cp311-manylinux_2_28_x86_64'] if name == 'charset-normalizer' else ['py3-none-any'])
    require(wheel.get_all('Wheel-Version') == ['1.0'] and len(tags) == len(set(tags))
            and set(tags) == set(expected_tags), 'wheel_tags')
    record_name = dist_info + '/RECORD'
    record_raw = files[record_name]
    record = record_rows(record_raw)
    require(set(record) == set(files) and record[record_name] == {'hash': '', 'bytes': None}, 'wheel_record_population')
    for member, body in files.items():
        if member != record_name:
            verify_record_body(body, record[member])
    scripts = set()
    if dist_info + '/entry_points.txt' in files:
        import configparser
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(files[dist_info + '/entry_points.txt'].decode('utf-8'))
        for script in config.options('console_scripts') if config.has_section('console_scripts') else []:
            require(re.fullmatch(r'[A-Za-z0-9_-]+', script) is not None, 'wheel_console_script')
            scripts.add(script)
    return {'files': files, 'dist_info': dist_info, 'record_name': record_name,
            'record': record, 'console_scripts': scripts,
            'proof': {**WHEEL_PINS[name], 'metadata_name': metadata['Name'], 'metadata_version': metadata['Version'],
                'wheel_tags': sorted(tags), 'wheel_record_sha256': sha(record_raw),
                'wheel_record_hashed_files_verified': len(files) - 1}}


def runtime_snapshot():
    return {'executable': str(Path(sys.executable).absolute()),
            'resolved_executable': str(Path(sys.executable).resolve(strict=True)),
            'version': sys.version, 'version_info': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(), 'sys_prefix': str(Path(sys.prefix).resolve()),
            'sys_base_prefix': str(Path(sys.base_prefix).resolve()), 'isolated': sys.flags.isolated == 1,
            'dont_write_bytecode': sys.dont_write_bytecode is True}


def verify_runtime(value, venv, site):
    require(value['implementation'] == 'CPython' and value['version_info'][:2] == [3, 11], 'actual_cp311_required')
    require(value['isolated'] is True and value['dont_write_bytecode'] is True, 'isolated_no_bytecode_required')
    require(value['sys_prefix'] == str(venv) and value['sys_base_prefix'] != str(venv)
            and Path(value['executable']).parent == venv / 'bin'
            and site == venv / 'lib/python3.11/site-packages', 'isolated_venv_identity')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'host_platform')


def verify_sys_path(paths, site, stdlib, stdlib_zip):
    require(type(paths) is list and paths and all(type(p) is str and p for p in paths), 'interpreter_search_path')
    for name in paths:
        path = Path(name).absolute().resolve()
        require(path == site or path == stdlib_zip or path.is_relative_to(stdlib), 'external_interpreter_path')
    require(sum(Path(p).absolute().resolve() == site for p in paths) == 1, 'venv_search_path_population')


def inventory(site, distributions):
    found = {}
    for dist in distributions:
        name = normalized(dist.metadata['Name'])
        require(name not in found and name in set(VERSIONS) | {'pip', 'setuptools'}, 'distribution_population')
        location = Path(dist.locate_file('')).absolute()
        require(location.resolve(strict=True) == site and location == site, 'distribution_location')
        if name in VERSIONS:
            require(dist.version == VERSIONS[name], 'distribution_version')
        found[name] = dist
    require(set(VERSIONS) <= set(found), 'missing_distribution')
    return found


def installed_member(site, venv, member, scripts):
    if member.startswith('../../../bin/'):
        script = member[len('../../../bin/'):]
        require(script in scripts and '/' not in script, 'installed_script_path')
        path = venv / 'bin' / script
    else:
        path = site / relative(member)
    require(path.resolve(strict=True) == path and path.is_relative_to(venv), 'installed_member_escape_or_symlink')
    return path


def verify_installed(site, venv, name, wheel):
    record_path = site / wheel['record_name']
    raw = regular(record_path, MAX_PROOF)
    rows = record_rows(raw)
    require(rows.get(wheel['record_name']) == {'hash': '', 'bytes': None}, 'installed_record_self')
    additions = {wheel['dist_info'] + '/' + n for n in ('INSTALLER', 'REQUESTED', 'direct_url.json')}
    scripts = {'../../../bin/' + n for n in wheel['console_scripts']}
    require(set(wheel['files']) <= set(rows) and set(rows) <= set(wheel['files']) | additions | scripts,
            'installed_record_population')
    verified, total, bound = 0, 0, {}
    for member, row in rows.items():
        path = installed_member(site, venv, member, wheel['console_scripts'])
        body = regular(path)
        total += len(body)
        require(total <= MAX_TOTAL, 'installed_total_bound')
        if member == wheel['record_name']:
            continue
        verify_record_body(body, row)
        verified += 1
        if member in wheel['files']:
            require(body == wheel['files'][member], 'installed_differs_from_pinned_wheel')
        bound[str(path)] = sha(body)
    package_root = site / MODULES[name]
    require(package_root.is_dir() and not package_root.is_symlink(), 'installed_package_root')
    for path in package_root.rglob('*'):
        require(not path.is_symlink() and (path.is_file() or path.is_dir()), 'installed_package_type')
        require(path.name != '__pycache__' and path.suffix not in {'.pyc', '.pyo'}, 'cached_package_bytecode')
        if path.is_file():
            require(str(path) in bound, 'unrecorded_package_file')
    for path in (site / wheel['dist_info']).rglob('*'):
        require(not path.is_symlink() and (path.is_file() or path.is_dir()), 'installed_metadata_type')
        if path.is_file():
            require(path == record_path or str(path) in bound, 'unrecorded_metadata_file')
    return {'path': str(record_path), 'bytes': len(raw), 'sha256': sha(raw), 'hashed_files_verified': verified,
            'unhashed_paths': [wheel['record_name']], 'all_hashed_files_verified': True}, bound


def verify_site_population(site, venv, installed, wheels):
    """No unrecorded top-level modules, metadata or path injection files.

    Pip/setuptools are optional standard venv bootstrap distributions, not among
    the five wheel-pinned dependencies. Their unused generated bytecode is
    allowed only as an explicitly listed unhashed RECORD entry. Five dependency
    package bytecode is rejected separately before any imports.
    """
    owned = set()
    bootstrap = []
    for name, dist in installed.items():
        if name in VERSIONS:
            record_name = wheels[name]['record_name']
            scripts = wheels[name]['console_scripts']
        else:
            candidates = [str(p) for p in (dist.files or []) if str(p).endswith('.dist-info/RECORD')]
            require(len(candidates) == 1, 'bootstrap_record_population')
            record_name = relative(candidates[0])
            scripts = {'pip', 'pip3', 'pip3.11'} if name == 'pip' else set()
        rows = record_rows(regular(site / record_name, MAX_PROOF))
        require(rows.get(record_name) == {'hash': '', 'bytes': None}, 'site_record_self')
        verified = 0
        for member, row in rows.items():
            path = installed_member(site, venv, member, scripts)
            require(str(path) not in owned, 'installed_cross_distribution_duplicate')
            owned.add(str(path))
            body = regular(path)
            if member == record_name:
                continue
            if row['hash']:
                verify_record_body(body, row)
                verified += 1
            else:
                require(name in {'pip', 'setuptools'} and path.suffix == '.pyc'
                        and '__pycache__' in path.parts, 'unhashed_installed_file')
        if name not in VERSIONS:
            bootstrap.append({'name': name, 'version': dist.version,
                'record_sha256': sha(regular(site / record_name, MAX_PROOF)),
                'hashed_files_verified': verified, 'pinned_wheel_dependency': False})
    count = 0
    for path in site.rglob('*'):
        require(not path.is_symlink() and (path.is_file() or path.is_dir()), 'site_special_entry')
        if path.is_file():
            count += 1
            require(count <= 20000 and str(path) in owned, 'unowned_site_file')
    return {'all_site_files_record_owned': True, 'site_file_count': count,
            'optional_bootstrap': bootstrap}


def verify_loaded(name, module, bound, all_bound):
    prefix = MODULES[name]
    require(getattr(module, '__version__', None) == VERSIONS[name], 'actual_import_version')
    path = Path(module.__file__).absolute()
    require(str(path) in bound and sha(regular(path)) == bound[str(path)], 'actual_import_binding')
    count = 0
    for key, value in list(sys.modules.items()):
        if key == prefix or key.startswith(prefix + '.'):
            origin = getattr(value, '__file__', None)
            require(type(origin) is str and origin.endswith(('.py', '.so')), 'loaded_module_kind')
            target = Path(origin).absolute()
            # Requests exposes supported aliases of the other verified packages.
            # Aliases must still be the exact canonical loaded module object and
            # originate in one of the five already wheel-verified installations.
            actual_name = getattr(value, '__name__', '')
            require(any(actual_name == p or actual_name.startswith(p + '.') for p in MODULES.values())
                    and sys.modules.get(actual_name) is value, 'loaded_module_alias_identity')
            require(str(target) in all_bound and sha(regular(target)) == all_bound[str(target)], 'loaded_module_source_binding')
            cached = getattr(value, '__cached__', None)
            require(cached is None or not Path(cached).exists(), 'loaded_cached_bytecode')
            count += 1
    require(count > 0, 'loaded_module_population')
    return {'import_module': prefix, 'import_path': str(path), 'loaded_module_count': count,
            'source_or_extension_origins_verified': True, 'no_cached_bytecode': True}


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'urllib.', 'http.')) or event in {
            'os.system', 'os.posix_spawn', 'os.fork', 'os.exec'}:
        raise VerificationRejected('dependency_verification_external_execution')


def current_record(site, venv, pin):
    """Recheck a previously verified RECORD and every hashed installed byte."""
    path = Path(pin['path']).absolute()
    require(path.is_relative_to(site) and path.name == 'RECORD', 'current_record_path')
    raw = regular(path, MAX_PROOF)
    require(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'current_record_anchor')
    record_name = path.relative_to(site).as_posix()
    rows = record_rows(raw)
    require(rows.get(record_name) == {'hash': '', 'bytes': None}
            and pin['unhashed_paths'] == [record_name]
            and pin['all_hashed_files_verified'] is True, 'current_record_schema')
    scripts = {name[len('../../../bin/'):] for name in rows if name.startswith('../../../bin/')}
    require(all(re.fullmatch(r'[A-Za-z0-9_-]+', n) is not None for n in scripts), 'current_script_shape')
    bound = {}
    for member, row in rows.items():
        if member == record_name:
            continue
        target = installed_member(site, venv, member, scripts)
        body = regular(target)
        verify_record_body(body, row)
        bound[str(target)] = sha(body)
    require(len(bound) == pin['hashed_files_verified'], 'current_record_population')
    return record_name, scripts, bound


def validate_current_receipt(proof, expected_verifier_sha256, expected_manifest_sha256):
    """Pure caller gate: no imports, audit hook, fetch or subprocess operation.

    The caller first verifies the complete receipt bytes against its expected
    SHA. Run produce separately: its permanent no-subprocess audit hook must
    never be installed into a full-static host process that calls Docker.
    """
    require(proof.get('schema') == 'nico.diagnostic.cp311-installed-dependencies.v1'
            and proof.get('status') == 'INSTALLED_DEPENDENCIES_VERIFIED'
            and proof.get('verifier_sha256') == expected_verifier_sha256 == sha(regular(__file__))
            and proof.get('wheel_manifest_sha256') == expected_manifest_sha256
            and proof.get('historical_environment_proof') is False
            and proof.get('pair_host_installation_binding_required') is True,
            'current_dependency_proof_identity')
    venv, site = Path(proof['venv_root']).absolute(), Path(proof['site_packages']).absolute()
    require(venv.resolve(strict=True) == venv and site.resolve(strict=True) == site, 'current_venv_path')
    actual = runtime_snapshot()
    verify_runtime(actual, venv, site)
    require(actual == proof['python'], 'current_interpreter_changed')
    require(site == Path(sysconfig.get_paths()['purelib']).absolute() == Path(sysconfig.get_paths()['platlib']).absolute(),
            'current_site_path_changed')
    stdlib = Path(sysconfig.get_paths()['stdlib']).absolute().resolve()
    verify_sys_path(sys.path, site, stdlib, stdlib.parent / 'python311.zip')
    installed = inventory(site, importlib.metadata.distributions())
    actual_inventory = [{'name': n, 'version': installed[n].version,
        'kind': 'pinned_diagnostic_dependency' if n in VERSIONS else 'permitted_bootstrap_only'} for n in sorted(installed)]
    require(actual_inventory == proof['package_inventory'], 'current_inventory_changed')
    rows, wheels, bounds = {}, {}, {}
    require(type(proof.get('packages')) is list and len(proof['packages']) == 5, 'current_package_population')
    for row in proof['packages']:
        name = normalized(row['name'])
        require(name in VERSIONS and name not in rows and row['version'] == VERSIONS[name]
                and row['distribution_path'] == str(site)
                and all(row['wheel'].get(k) == v for k, v in WHEEL_PINS[name].items()), 'current_package_identity')
        record_name, scripts, bounds[name] = current_record(site, venv, row['installed_record'])
        wheels[name] = {'record_name': record_name, 'console_scripts': scripts}
        rows[name] = row
    require(set(rows) == set(VERSIONS), 'current_missing_package')
    require(verify_site_population(site, venv, installed, wheels) == proof['site_population'], 'current_site_population_changed')
    all_bound = {}
    for group in bounds.values():
        require(not set(all_bound).intersection(group), 'current_cross_package_collision')
        all_bound.update(group)
    for name, row in rows.items():
        require(str(Path(row['import_path']).absolute()) in bounds[name], 'current_import_source_binding')
        if MODULES[name] in sys.modules:
            verify_loaded(name, sys.modules[MODULES[name]], bounds[name], all_bound)
    return {'status': 'CURRENT_INSTALLED_DEPENDENCIES_VERIFIED',
            'package_versions': dict(VERSIONS), 'installation_rehashed': True,
            'historical_environment_proof': False}


def produce(wheel_dir, manifest_path, manifest_sha256, venv):
    venv = Path(venv).absolute()
    require(venv.resolve(strict=True) == venv, 'venv_canonical')
    site = Path(sysconfig.get_paths()['purelib']).absolute()
    require(site.resolve(strict=True) == site and site == Path(sysconfig.get_paths()['platlib']).absolute(), 'venv_site_path')
    runtime = runtime_snapshot()
    verify_runtime(runtime, venv, site)
    stdlib = Path(sysconfig.get_paths()['stdlib']).absolute().resolve()
    stdlib_zip = stdlib.parent / 'python311.zip'
    verify_sys_path(sys.path, site, stdlib, stdlib_zip)
    cfg = regular(venv / 'pyvenv.cfg', 16384).decode('utf-8')
    require(re.findall(r'(?m)^include-system-site-packages\s*=\s*(\S+)\s*$', cfg) == ['false'], 'system_site_packages_enabled')
    manifest, manifest_sha = public_manifest(manifest_path, manifest_sha256)
    installed = inventory(site, importlib.metadata.distributions())
    require(not any(k == p or k.startswith(p + '.') for k in sys.modules for p in MODULES.values()),
            'packages_already_loaded')
    wheels, records, bounds = {}, {}, {}
    for name in sorted(VERSIONS):
        wheels[name] = wheel_contents(Path(wheel_dir) / manifest[name]['filename'], name)
        records[name], bounds[name] = verify_installed(site, venv, name, wheels[name])
    site_population = verify_site_population(site, venv, installed, wheels)
    # Only after every installation and immutable wheel has been checked.
    sys.addaudithook(audit)
    imports = {name: importlib.import_module(MODULES[name]) for name in sorted(VERSIONS)}
    all_bound = {}
    for row in bounds.values():
        require(not set(all_bound).intersection(row), 'cross_dependency_source_collision')
        all_bound.update(row)
    packages = []
    for name in sorted(VERSIONS):
        packages.append({'name': name, 'version': installed[name].version, 'distribution_path': str(site),
            'wheel': wheels[name]['proof'], 'installed_record': records[name],
            **verify_loaded(name, imports[name], bounds[name], all_bound)})
    # Detect import-time distribution changes or unexpected packages.
    require(set(inventory(site, importlib.metadata.distributions())) == set(installed), 'post_import_inventory_changed')
    for name in VERSIONS:
        require(verify_installed(site, venv, name, wheels[name])[0] == records[name], 'post_import_installation_changed')
    require(verify_site_population(site, venv, installed, wheels) == site_population,
            'post_import_site_population_changed')
    return {'schema': 'nico.diagnostic.cp311-installed-dependencies.v1',
            'status': 'INSTALLED_DEPENDENCIES_VERIFIED', 'verifier_sha256': sha(regular(__file__)),
            'wheel_manifest_sha256': manifest_sha, 'python': runtime, 'venv_root': str(venv),
            'site_packages': str(site), 'package_inventory': [{'name': n, 'version': installed[n].version,
                'kind': 'pinned_diagnostic_dependency' if n in VERSIONS else 'permitted_bootstrap_only'} for n in sorted(installed)],
            'packages': packages, 'site_population': site_population,
            'pair_host_installation_binding_required': True,
            'historical_environment_proof': False, 'HTTP_subprocess_or_target_execution': False,
            'global_environment_changed': False, 'qualification_or_human_gate_credit': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel-directory', required=True, type=Path)
    parser.add_argument('--wheel-manifest', required=True, type=Path)
    parser.add_argument('--wheel-manifest-sha256', required=True)
    parser.add_argument('--venv', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    proof = produce(args.wheel_directory, args.wheel_manifest, args.wheel_manifest_sha256, args.venv)
    data = canonical(proof) + b'\n'
    require(len(data) <= MAX_PROOF, 'dependency_proof_bound')
    output = args.output.absolute()
    require(output.parent.resolve(strict=True) == output.parent and not output.exists(), 'new_private_output')
    with output.open('xb') as stream:
        os.chmod(output, 0o600)
        stream.write(data)
    print('{"status":"INSTALLED_DEPENDENCIES_VERIFIED","historical_environment_proof":false}')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        code = str(error) if isinstance(error, VerificationRejected) else 'dependency_verification_failed'
        if re.fullmatch(r'[a-z0-9_]+', code) is None:
            code = 'dependency_verification_failed'
        print(json.dumps({'status': 'UNPROVEN', 'error_code': code, 'historical_environment_proof': False}))
        raise SystemExit(2) from None
