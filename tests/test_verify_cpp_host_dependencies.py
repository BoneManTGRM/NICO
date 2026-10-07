"""Owned inert guard controls. No wheel modules, HTTP or target code executes."""
import ast
import base64
import copy
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import warnings
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/verify_cpp_host_dependencies.py'
SPEC = importlib.util.spec_from_file_location('owned_dependency_verifier', SOURCE)
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)


def owned_record(files, record_name):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    for name, raw in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
        writer.writerow((name, 'sha256=' + digest, str(len(raw))))
    writer.writerow((record_name, '', ''))
    return stream.getvalue().encode()


def owned_archive(files, *, duplicate=None, symlink=None):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, raw in files.items():
                row = zipfile.ZipInfo(name)
                row.external_attr = (stat.S_IFLNK | 0o777 if name == symlink else stat.S_IFREG | 0o644) << 16
                archive.writestr(row, raw)
            if duplicate:
                archive.writestr(duplicate, files[duplicate])
    return stream.getvalue()


def owned_wheel(*, metadata_name='requests', version='2.34.2', tag='py3-none-any',
                extra=None, duplicate=None, symlink=None, wrong_record=False):
    prefix = 'requests-2.34.2.dist-info'
    record_name = prefix + '/RECORD'
    files = {'requests/__init__.py': b'# owned inert bytes, never imported\n',
        prefix + '/METADATA': ('Metadata-Version: 2.1\nName: ' + metadata_name + '\nVersion: ' + version + '\n').encode(),
        prefix + '/WHEEL': ('Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: ' + tag + '\n').encode()}
    if extra:
        files[extra] = b'owned-extra'
    raw_record = owned_record(files, record_name)
    if wrong_record:
        raw_record = raw_record.replace(b'sha256=', b'sha256=A', 1)
    files[record_name] = raw_record
    raw = owned_archive(files, duplicate=duplicate, symlink=symlink)
    pins = {'filename': 'owned.whl', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'url': 'https://files.pythonhosted.org/owned.whl'}
    return raw, files, pins


class OwnedDist:
    def __init__(self, name, version, site, files=()):
        self.metadata, self.version, self.site, self.files = {'Name': name}, version, site, list(files)
    def locate_file(self, name):
        return self.site / name


@contextlib.contextmanager
def owned_modules(rows):
    # Other CI tests may already have Requests imported. Keep stdlib/other state,
    # but the controlled namespace contains only the inert owned package objects.
    filtered = {key: value for key, value in sys.modules.items()
                if not any(key == prefix or key.startswith(prefix + '.') for prefix in SUBJECT.MODULES.values())}
    filtered.update(rows)
    with patch.dict(sys.modules, filtered, clear=True):
        yield


class Controls(unittest.TestCase):
    def rejected(self, code, subject, *args):
        with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$'):
            subject(*args)

    def wheel_case(self, **kwargs):
        raw, files, pins = owned_wheel(**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'owned.whl'
            path.write_bytes(raw)
            with patch.dict(SUBJECT.WHEEL_PINS, {'requests': pins}):
                return SUBJECT.wheel_contents(path, 'requests')

    def test_owned_wheel_data_only_positive(self):
        wheel = self.wheel_case()
        self.assertEqual(wheel['proof']['metadata_name'], 'requests')
        self.assertEqual(wheel['proof']['wheel_record_hashed_files_verified'], 3)
        self.assertEqual(wheel['console_scripts'], set())

    def test_wrong_whole_wheel_digest_rejected(self):
        raw, files, pins = owned_wheel()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'owned.whl'
            path.write_bytes(raw + b'owned corruption')
            with patch.dict(SUBJECT.WHEEL_PINS, {'requests': pins}):
                self.rejected('wheel_digest', SUBJECT.wheel_contents, path, 'requests')

    def test_rebound_owned_wrong_metadata_and_abi_still_rejected(self):
        for changes, code in [({'metadata_name': 'wrong'}, 'wheel_metadata_identity'),
                              ({'version': '0.0'}, 'wheel_metadata_identity'),
                              ({'tag': 'cp312-cp312-manylinux2014_x86_64'}, 'wheel_tags')]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$'):
                    self.wheel_case(**changes)

    def test_owned_archive_escape_duplicate_link_rejected(self):
        for changes, code in [({'extra': '../escape'}, 'unsafe_wheel_member'),
                ({'duplicate': 'requests/__init__.py'}, 'wheel_duplicate_or_encrypted'),
                ({'symlink': 'requests/__init__.py'}, 'wheel_special_member')]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$'):
                    self.wheel_case(**changes)

    def test_record_hash_size_duplicate_and_unhashed_guards(self):
        good = {'hash': 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(b'owned').digest()).decode().rstrip('='), 'bytes': 5}
        SUBJECT.verify_record_body(b'owned', good)
        self.rejected('record_actual_length', SUBJECT.verify_record_body, b'owned', {**good, 'bytes': 6})
        self.rejected('record_actual_hash', SUBJECT.verify_record_body, b'other', good)
        self.rejected('record_duplicate_or_shape', SUBJECT.record_rows, b'owned,,\nowned,,\n')
        self.rejected('record_hash_or_size', SUBJECT.record_rows, b'owned,md5=invalid,5\n')
        self.rejected('record_unhashed_size', SUBJECT.record_rows, b'owned,,1\n')

    def test_pinned_manifest_digest_population_and_version(self):
        rows = [{'name': n, 'version': SUBJECT.VERSIONS[n], **p} for n, p in SUBJECT.WHEEL_PINS.items()]
        value = {'schema': 'nico.diagnostic.cp311-host-wheels.v1', 'wheels': rows}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'manifest.json'
            raw = SUBJECT.canonical(value)
            path.write_bytes(raw)
            found, digest = SUBJECT.public_manifest(path, SUBJECT.sha(raw))
            self.assertEqual(set(found), set(SUBJECT.VERSIONS))
            self.rejected('wheel_manifest_digest', SUBJECT.public_manifest, path, '0' * 64)
            changed = copy.deepcopy(value)
            changed['wheels'][0]['version'] = '0.0'
            raw = SUBJECT.canonical(changed);path.write_bytes(raw)
            self.rejected('wheel_manifest_pin', SUBJECT.public_manifest, path, SUBJECT.sha(raw))
            changed = copy.deepcopy(value)
            changed['wheels'][-1] = copy.deepcopy(changed['wheels'][0])
            raw = SUBJECT.canonical(changed);path.write_bytes(raw)
            self.rejected('wheel_manifest_pin', SUBJECT.public_manifest, path, SUBJECT.sha(raw))

    def test_actual_wrong_interpreter_and_nonisolated_venv_rejected(self):
        # Owned guard values; no claim of actual CPython3.11 execution.
        venv = Path('/owned/venv')
        value = {'implementation': 'CPython', 'version_info': [3, 11, 1], 'isolated': True,
                 'dont_write_bytecode': True, 'sys_prefix': str(venv), 'sys_base_prefix': '/owned/base',
                 'executable': '/owned/venv/bin/python'}
        site = venv / 'lib/python3.11/site-packages'
        SUBJECT.verify_runtime(value, venv, site)
        self.rejected('actual_cp311_required', SUBJECT.verify_runtime, {**value, 'version_info': [3, 12, 14]}, venv, site)
        self.rejected('isolated_no_bytecode_required', SUBJECT.verify_runtime, {**value, 'isolated': False}, venv, site)
        self.rejected('isolated_no_bytecode_required', SUBJECT.verify_runtime, {**value, 'dont_write_bytecode': False}, venv, site)
        self.rejected('isolated_venv_identity', SUBJECT.verify_runtime, {**value, 'sys_base_prefix': str(venv)}, venv, site)

    def test_interpreter_paths_reject_injected_external_or_duplicate_site(self):
        site, stdlib = Path('/owned/venv/lib/python3.11/site-packages'), Path('/owned/base/lib/python3.11')
        zip_path = stdlib.parent / 'python311.zip'
        SUBJECT.verify_sys_path([str(stdlib), str(stdlib / 'lib-dynload'), str(zip_path), str(site)], site, stdlib, zip_path)
        self.rejected('external_interpreter_path', SUBJECT.verify_sys_path,
                      [str(site), '/owned/foreign'], site, stdlib, zip_path)
        self.rejected('venv_search_path_population', SUBJECT.verify_sys_path,
                      [str(site), str(site)], site, stdlib, zip_path)

    def test_distribution_inventory_extra_duplicate_wrong_version_location(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory).resolve()
            rows = [OwnedDist(n, v, site) for n, v in SUBJECT.VERSIONS.items()]
            self.assertEqual(set(SUBJECT.inventory(site, rows + [OwnedDist('pip', 'owned', site)])), set(SUBJECT.VERSIONS) | {'pip'})
            self.rejected('distribution_population', SUBJECT.inventory, site, rows + [OwnedDist('unknown', '1', site)])
            self.rejected('distribution_population', SUBJECT.inventory, site, rows + [rows[0]])
            bad = [OwnedDist(n, '0' if n == 'requests' else v, site) for n, v in SUBJECT.VERSIONS.items()]
            self.rejected('distribution_version', SUBJECT.inventory, site, bad)
            other = site / 'other';other.mkdir()
            self.rejected('distribution_location', SUBJECT.inventory, site,
                          [OwnedDist(n, v, other) for n, v in SUBJECT.VERSIONS.items()])

    def staged(self, directory):
        venv = Path(directory).resolve()
        site = venv / 'lib/python3.11/site-packages'
        site.mkdir(parents=True)
        wheel = self.wheel_case()
        for name, raw in wheel['files'].items():
            destination = site / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        return venv, site, wheel

    def test_installed_owned_bytes_match_wheel_and_record(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site, wheel = self.staged(directory)
            proof, bound = SUBJECT.verify_installed(site, venv, 'requests', wheel)
            self.assertTrue(proof['all_hashed_files_verified'])
            self.assertEqual(proof['hashed_files_verified'], 3)
            self.assertEqual(len(bound), 3)

    def test_current_receipt_record_rehash_rejects_stale_or_changed_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site, wheel = self.staged(directory)
            proof, bound = SUBJECT.verify_installed(site, venv, 'requests', wheel)
            record, scripts, current = SUBJECT.current_record(site, venv, proof)
            self.assertEqual(current, bound)
            self.assertEqual(record, wheel['record_name'])
            self.assertEqual(scripts, set())
            (site / 'requests/__init__.py').write_bytes(b'owned changed after proof')
            with self.assertRaises(SUBJECT.VerificationRejected):
                SUBJECT.current_record(site, venv, proof)
            (site / wheel['record_name']).write_bytes(b'owned stale RECORD')
            self.rejected('current_record_anchor', SUBJECT.current_record, site, venv, proof)

    def test_installed_changed_bytes_rejected_even_with_self_updated_record(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site, wheel = self.staged(directory)
            changed = {n: raw for n, raw in wheel['files'].items() if n != wheel['record_name']}
            changed['requests/__init__.py'] = b'owned changed package bytes'
            (site / 'requests/__init__.py').write_bytes(changed['requests/__init__.py'])
            (site / wheel['record_name']).write_bytes(owned_record(changed, wheel['record_name']))
            self.rejected('installed_differs_from_pinned_wheel', SUBJECT.verify_installed, site, venv, 'requests', wheel)

    def test_unrecorded_extra_cached_and_symlinked_package_files_rejected(self):
        for kind, code in [('extra', 'unrecorded_package_file'), ('cache', 'cached_package_bytecode'),
                           ('link', 'installed_package_type')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                venv, site, wheel = self.staged(directory)
                path = site / 'requests/owned-extra'
                if kind == 'cache':
                    path = site / 'requests/__pycache__';path.mkdir()
                elif kind == 'link':
                    path.symlink_to(site / 'requests/__init__.py')
                else:
                    path.write_bytes(b'owned')
                self.rejected(code, SUBJECT.verify_installed, site, venv, 'requests', wheel)

    def test_installed_record_population_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site, wheel = self.staged(directory)
            raw = (site / wheel['record_name']).read_bytes()
            (site / wheel['record_name']).write_bytes(raw + b'../../../outside,,\n')
            self.rejected('installed_record_population', SUBJECT.verify_installed, site, venv, 'requests', wheel)
            self.rejected('unsafe_wheel_member', SUBJECT.installed_member, site, venv, '../escape', set())
            self.rejected('installed_script_path', SUBJECT.installed_member, site, venv, '../../../bin/unknown', {'idna'})

    def test_site_population_rejects_unowned_top_level_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site, wheel = self.staged(directory)
            installed = {'requests': OwnedDist('requests', '2.34.2', site)}
            proof = SUBJECT.verify_site_population(site, venv, installed, {'requests': wheel})
            self.assertTrue(proof['all_site_files_record_owned'])
            self.assertEqual(proof['site_file_count'], 4)
            (site / 'owned-unrecorded.pth').write_bytes(b'# owned path injection fixture\n')
            self.rejected('unowned_site_file', SUBJECT.verify_site_population, site, venv, installed, {'requests': wheel})

    def test_regular_path_and_record_bounds_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            file = root / 'owned';file.write_bytes(b'owned')
            link = root / 'link';link.symlink_to(file)
            self.rejected('regular_canonical_path', SUBJECT.regular, link)
            self.rejected('regular_file_bound', SUBJECT.regular, file, 4)
        self.rejected('record_bound', SUBJECT.record_rows, b'x' * (SUBJECT.MAX_PROOF + 1))

    def test_verified_requests_aliases_remain_bound_to_other_verified_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            left, right = root / 'requests.py', root / 'urllib3.py'
            left.write_bytes(b'owned requests');right.write_bytes(b'owned urllib3')
            requests = types.ModuleType('requests');requests.__file__ = str(left);requests.__version__ = '2.34.2'
            urllib3 = types.ModuleType('urllib3');urllib3.__file__ = str(right)
            modules = {'requests': requests, 'urllib3': urllib3, 'requests.packages.urllib3': urllib3}
            bound = {str(left): SUBJECT.sha(left.read_bytes())}
            all_bound = {**bound, str(right): SUBJECT.sha(right.read_bytes())}
            with owned_modules(modules):
                proof = SUBJECT.verify_loaded('requests', requests, bound, all_bound)
                self.assertEqual(proof['loaded_module_count'], 2)
                self.rejected('loaded_module_source_binding', SUBJECT.verify_loaded,
                              'requests', requests, bound, bound)

    def test_loaded_wrong_version_alias_identity_or_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            file = root / 'owned.py';file.write_bytes(b'owned')
            module = types.ModuleType('requests');module.__file__ = str(file);module.__version__ = '0.0'
            bound = {str(file): SUBJECT.sha(file.read_bytes())}
            self.rejected('actual_import_version', SUBJECT.verify_loaded, 'requests', module, bound, bound)
            module.__version__ = '2.34.2'
            other = types.ModuleType('unknown');other.__file__ = str(file)
            with owned_modules({'requests': module, 'requests.unknown': other}):
                self.rejected('loaded_module_alias_identity', SUBJECT.verify_loaded, 'requests', module, bound, bound)

    def test_external_execution_audit_rejects_network_and_subprocess(self):
        for event in ('socket.connect', 'subprocess.Popen', 'urllib.Request', 'os.system', 'os.fork'):
            self.rejected('dependency_verification_external_execution', SUBJECT.audit, event, ())
        SUBJECT.audit('open', ())

    def test_source_has_no_fetch_install_or_process_command_route(self):
        # Inspect syntax only; do not execute wheel/package modules or main.
        tree = ast.parse(SOURCE.read_bytes())
        routes = [(node.func.value.id, node.func.attr) for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)]
        self.assertNotIn(('urllib', 'urlopen'), routes)
        self.assertNotIn(('subprocess', 'Popen'), routes)
        self.assertNotIn(('os', 'system'), routes)
        self.assertNotIn(('subprocess', 'check_call'), routes)


class OwnedBootstrap:
    def __init__(self, name, version, site, files):
        self.metadata = {'Name': name, 'Version': version}
        self.version, self.site, self.files = version, site, list(files)

    def locate_file(self, name):
        return self.site / name


def bootstrap_owned_record(files, record_name):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    for name, raw in sorted(files.items()):
        value = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
        writer.writerow((name, 'sha256=' + value, str(len(raw))))
    writer.writerow((record_name, '', ''))
    return stream.getvalue().encode()


def stage_bootstrap(site, name='pip', version='1.0', nested=True, extra_files=None):
    prefix = name + '-' + version + '.dist-info'
    record_name = prefix + '/RECORD'
    files = {prefix + '/METADATA': ('Metadata-Version: 2.1\nName: ' + name
             + '\nVersion: ' + version + '\n').encode(),
             name + '/__init__.py': b'# owned bytes; never imported\n'}
    if nested:
        files[name + '/_vendor/owned-0.1.dist-info/RECORD'] = b'owned nested vendor record\n'
        files[name + '/_vendor/owned_vendor.py'] = b'# owned vendor payload\n'
    files.update(extra_files or {})
    for member, raw in {**files, record_name: bootstrap_owned_record(files, record_name)}.items():
        path = site / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return OwnedBootstrap(name, version, site, [*files, record_name]), record_name, files


def bootstrap_site_root(directory):
    venv = Path(directory).resolve() / 'owned-venv'
    site = venv / 'lib/python3.11/site-packages'
    site.mkdir(parents=True)
    return venv, site


class BootstrapControls(unittest.TestCase):
    def reject(self, code, function, *args):
        with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$') as caught:
            function(*args)
        return caught.exception

    def test_before_after_root_and_nested_record_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site = bootstrap_site_root(directory)
            dist, record_name, files = stage_bootstrap(site)
            # Exact source-derived old suffix predicate; smallest owned case.
            old_candidates = [str(p) for p in (dist.files or [])
                              if str(p).endswith('.dist-info/RECORD')]
            self.assertEqual(len(old_candidates), 2)
            self.reject('bootstrap_record_population', SUBJECT.require,
                        len(old_candidates) == 1, 'bootstrap_record_population')
            self.assertEqual(SUBJECT.bootstrap_record_name(site, 'pip', dist), record_name)
            proof = SUBJECT.verify_site_population(site, venv, {'pip': dist}, {})
            self.assertTrue(proof['all_site_files_record_owned'])
            self.assertEqual(proof['site_file_count'], len(files) + 1)
            self.assertEqual(proof['optional_bootstrap'][0]['hashed_files_verified'], len(files))
            self.assertEqual(proof['optional_bootstrap'][0]['version'], '1.0')

    def test_no_nested_single_root_remains_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site = bootstrap_site_root(directory)
            dist, record_name, files = stage_bootstrap(site, 'setuptools', nested=False)
            self.assertEqual(SUBJECT.bootstrap_record_name(site, 'setuptools', dist), record_name)
            proof = SUBJECT.verify_site_population(site, venv, {'setuptools': dist}, {})
            self.assertEqual(proof['optional_bootstrap'][0]['hashed_files_verified'], len(files))

    def test_no_root_and_two_roots_rejected_with_safe_current_counts(self):
        for case in ('missing', 'ambiguous'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                venv, site = bootstrap_site_root(directory)
                dist, record_name, files = stage_bootstrap(site)
                if case == 'missing':
                    dist.files.remove(record_name)
                else:
                    dist.files.append('pip-2.0.dist-info/RECORD')
                error = self.reject('bootstrap_record_population', SUBJECT.bootstrap_record_name,
                                    site, 'pip', dist)
                diagnostic = SUBJECT.bootstrap_failure_diagnostic(error)
                self.assertEqual(diagnostic, {'package': 'pip', 'version': '1.0',
                    'total_suffix_count': 1 if case == 'missing' else 3,
                    'own_top_level_count': 0 if case == 'missing' else 2, 'nested_count': 1})
                self.assertNotIn(str(site), json.dumps(diagnostic))

    def test_own_record_directory_and_distribution_identity_rejected(self):
        for case in ('wrong-directory-name', 'wrong-directory-version', 'unsafe-path',
                     'wrong-distribution-name', 'wrong-distribution-version'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                venv, site = bootstrap_site_root(directory)
                dist, record_name, files = stage_bootstrap(site, nested=False)
                code = 'bootstrap_record_identity'
                if case == 'wrong-directory-name':
                    dist.files[dist.files.index(record_name)] = 'setuptools-1.0.dist-info/RECORD'
                elif case == 'wrong-directory-version':
                    dist.files[dist.files.index(record_name)] = 'pip-2.0.dist-info/RECORD'
                elif case == 'unsafe-path':
                    dist.files[dist.files.index(record_name)] = '../pip-1.0.dist-info/RECORD'
                    code = 'bootstrap_record_population'
                elif case == 'wrong-distribution-name':
                    dist.metadata['Name'] = 'setuptools'
                    code = 'bootstrap_distribution_identity'
                else:
                    dist.metadata['Version'] = '2.0'
                    code = 'bootstrap_distribution_identity'
                self.reject(code, SUBJECT.bootstrap_record_name, site, 'pip', dist)

    def test_metadata_missing_wrong_or_duplicate_identity_rejected(self):
        for case in ('unlisted', 'missing-file', 'wrong-name', 'wrong-version', 'duplicate-name', 'duplicate-version'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                venv, site = bootstrap_site_root(directory)
                dist, record_name, files = stage_bootstrap(site, nested=False)
                metadata_name = 'pip-1.0.dist-info/METADATA'
                code = 'bootstrap_metadata_identity'
                if case == 'unlisted':
                    dist.files.remove(metadata_name)
                    code = 'bootstrap_metadata_missing'
                elif case == 'missing-file':
                    (site / metadata_name).unlink()
                    with self.assertRaises(FileNotFoundError):
                        SUBJECT.bootstrap_record_name(site, 'pip', dist)
                    continue
                else:
                    body = files[metadata_name]
                    if case == 'wrong-name':
                        body = body.replace(b'Name: pip', b'Name: setuptools')
                    elif case == 'wrong-version':
                        body = body.replace(b'Version: 1.0', b'Version: 2.0')
                    elif case == 'duplicate-name':
                        body += b'Name: pip\n'
                    else:
                        body += b'Version: 1.0\n'
                    (site / metadata_name).write_bytes(body)
                self.reject(code, SUBJECT.bootstrap_record_name, site, 'pip', dist)

    def test_nested_vendor_record_and_payload_mutations_still_rejected(self):
        for member in ('pip/_vendor/owned-0.1.dist-info/RECORD', 'pip/_vendor/owned_vendor.py'):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                venv, site = bootstrap_site_root(directory)
                dist, record_name, files = stage_bootstrap(site)
                raw = files[member]
                (site / member).write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                self.reject('record_actual_hash', SUBJECT.verify_site_population,
                            site, venv, {'pip': dist}, {})

    def test_symlink_metadata_record_and_vendor_are_rejected(self):
        for member, code in (('pip-1.0.dist-info/METADATA', 'regular_canonical_path'),
                             ('pip-1.0.dist-info/RECORD', 'regular_canonical_path'),
                             ('pip/_vendor/owned_vendor.py', 'installed_member_escape_or_symlink')):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                venv, site = bootstrap_site_root(directory)
                dist, record_name, files = stage_bootstrap(site)
                path = site / member
                body = path.read_bytes()
                backing = venv / 'owned-backing'
                backing.write_bytes(body)
                path.unlink()
                path.symlink_to(backing)
                self.reject(code, SUBJECT.verify_site_population, site, venv, {'pip': dist}, {})

    def test_all_site_unowned_and_cross_distribution_files_remain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            venv, site = bootstrap_site_root(directory)
            dist, record_name, files = stage_bootstrap(site)
            (site / 'owned-injection.pth').write_bytes(b'# unowned fixture\n')
            self.reject('unowned_site_file', SUBJECT.verify_site_population, site, venv, {'pip': dist}, {})
        with tempfile.TemporaryDirectory() as directory:
            venv, site = bootstrap_site_root(directory)
            shared = {'owned-shared.py': b'# shared owned bytes\n'}
            left, _, _ = stage_bootstrap(site, 'pip', nested=False, extra_files=shared)
            right, _, _ = stage_bootstrap(site, 'setuptools', nested=False, extra_files=shared)
            self.reject('installed_cross_distribution_duplicate', SUBJECT.verify_site_population,
                        site, venv, {'pip': left, 'setuptools': right}, {})

    def test_failure_diagnostic_rejects_extra_paths_bad_version_and_false_counts(self):
        clean = {'package': 'pip', 'version': '1.0', 'total_suffix_count': 2,
                 'own_top_level_count': 1, 'nested_count': 1}
        for key, value in (('extra', '/workspace/private'), ('package', 'unknown'), ('package', []),
                           ('version', '/owner/secret'), ('version', 'a' * 81),
                           ('nested_count', True), ('nested_count', -1),
                           ('total_suffix_count', 20001), ('total_suffix_count', 3)):
            with self.subTest(key=key, value=value):
                error = SUBJECT.VerificationRejected('bootstrap_record_population')
                error.bootstrap_record_selection = {**clean, key: value}
                self.assertIsNone(SUBJECT.bootstrap_failure_diagnostic(error))
        error = ValueError('owned non-verification failure')
        error.bootstrap_record_selection = clean
        self.assertIsNone(SUBJECT.bootstrap_failure_diagnostic(error))

    def test_actual_failure_main_guard_emits_only_typed_diagnostic_and_exit2(self):
        error = SUBJECT.VerificationRejected('bootstrap_record_population')
        error.bootstrap_record_selection = {'package': 'setuptools', 'version': '1.0',
            'total_suffix_count': 2, 'own_top_level_count': 1, 'nested_count': 1}
        tree = ast.parse(SOURCE.read_bytes())
        guards = [node for node in tree.body if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Compare)
                  and isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__']
        self.assertEqual(len(guards), 1)
        scope = dict(SUBJECT.__dict__)
        scope['__name__'] = '__main__'
        with patch.object(SUBJECT, 'main', side_effect=error) as main:
            scope['main'] = main
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), self.assertRaises(SystemExit) as stopped:
                exec(compile(ast.Module(body=guards, type_ignores=[]), '<actual-bound-main-guard>', 'exec'), scope)
        self.assertEqual(stopped.exception.code, 2)
        main.assert_called_once_with()
        result = json.loads(capture.getvalue())
        self.assertEqual(set(result), {'status', 'error_code', 'historical_environment_proof',
                                     'bootstrap_record_selection'})
        self.assertEqual(result['status'], 'UNPROVEN')
        self.assertFalse(result['historical_environment_proof'])
        self.assertEqual(result['bootstrap_record_selection'], error.bootstrap_record_selection)


CERTIFI_INIT = b'from .core import contents, where\n\n__all__ = ["contents", "where"]\n__version__ = "2026.07.22"\n'


def owned_dependency_proof():
    """Owned scalar fixture only: no claim of actual CPython3.11 or installation."""
    rows = []
    for name in sorted(SUBJECT.VERSIONS):
        rows.append({'name': name, 'version': SUBJECT.VERSIONS[name],
            'module_version': SUBJECT.expected_import_version(name),
            'distribution_path': '/owned/private/site', 'import_path': '/owned/private/module.py',
            'wheel': {**SUBJECT.WHEEL_PINS[name], 'metadata_version': SUBJECT.VERSIONS[name]},
            'installed_record': {'path': '/owned/private/RECORD', 'bytes': 123, 'sha256': 'a' * 64,
                'hashed_files_verified': 3, 'all_hashed_files_verified': True},
            'loaded_module_count': 2, 'source_or_extension_origins_verified': True, 'no_cached_bytecode': True})
    return {'schema': 'nico.diagnostic.cp311-installed-dependencies.v1',
        'status': 'INSTALLED_DEPENDENCIES_VERIFIED', 'verifier_sha256': SUBJECT.sha(SOURCE.read_bytes()),
        'wheel_manifest_sha256': 'b' * 64,
        'python': {'implementation': 'CPython', 'version_info': [3, 11, 17],
            'isolated': True, 'dont_write_bytecode': True, 'executable': '/owned/private/python',
            'sys_prefix': '/owned/private/venv', 'sys_base_prefix': '/owned/private/base'},
        'venv_root': '/owned/private/venv', 'site_packages': '/owned/private/site',
        'packages': rows, 'site_population': {'all_site_files_record_owned': True, 'site_file_count': 27,
            'optional_bootstrap': [{'name': 'setuptools', 'version': '84.0.0', 'record_sha256': 'c' * 64,
                'hashed_files_verified': 13, 'pinned_wheel_dependency': False}]},
        'pair_host_installation_binding_required': True, 'historical_environment_proof': False,
        'HTTP_subprocess_or_target_execution': False, 'global_environment_changed': False,
        'qualification_or_human_gate_credit': False}


class ModuleVersionControls(unittest.TestCase):
    def reject(self, code, function, *args):
        with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$'):
            function(*args)

    def certifi(self, directory, version='2026.07.22', body=CERTIFI_INIT):
        path = Path(directory).resolve() / 'certifi/__init__.py'
        path.parent.mkdir(parents=True)
        path.write_bytes(body)
        module = types.ModuleType('certifi')
        module.__version__, module.__file__, module.__cached__ = version, str(path), None
        bound = {str(path): SUBJECT.sha(body)}
        return module, bound

    def test_exact_certifi_initializer_data_and_metadata_versions_are_distinct(self):
        self.assertEqual(len(CERTIFI_INIT), 94)
        self.assertEqual(SUBJECT.sha(CERTIFI_INIT), SUBJECT.CERTIFI_INIT_SHA256)
        self.assertEqual(SUBJECT.VERSIONS['certifi'], '2026.7.22')
        self.assertEqual(SUBJECT.expected_import_version('certifi'), '2026.07.22')
        tree = ast.parse(CERTIFI_INIT)
        declaration = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
        self.assertEqual(declaration, ['2026.07.22'])
        for name in set(SUBJECT.VERSIONS) - {'certifi'}:
            self.assertEqual(SUBJECT.expected_import_version(name), SUBJECT.VERSIONS[name])

    def test_exact_certifi_module_passes_existing_origin_and_namespace_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            module, bound = self.certifi(directory)
            with owned_modules({'certifi': module}):
                row = SUBJECT.verify_loaded('certifi', module, bound, bound)
            self.assertEqual(row['module_version'], '2026.07.22')
            self.assertEqual(row['loaded_module_count'], 1)
            self.assertTrue(row['source_or_extension_origins_verified'])
            self.assertTrue(row['no_cached_bytecode'])

    def test_metadata_spelling_other_padding_wrong_version_and_missing_are_rejected(self):
        for value in ['2026.7.22', '2026.007.22', '2026.07.23', None, 20260722]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                module, bound = self.certifi(directory, value)
                self.reject('actual_import_version', SUBJECT.verify_loaded, 'certifi', module, bound, bound)

    def test_changed_certifi_wheel_pin_and_rebound_initializer_are_rejected(self):
        changed = {**SUBJECT.WHEEL_PINS['certifi'], 'sha256': '0' * 64}
        with patch.dict(SUBJECT.WHEEL_PINS, {'certifi': changed}):
            self.reject('certifi_import_version_pin', SUBJECT.expected_import_version, 'certifi')
        with tempfile.TemporaryDirectory() as directory:
            module, bound = self.certifi(directory, body=CERTIFI_INIT + b'# altered inert bytes\n')
            with owned_modules({'certifi': module}):
                self.reject('certifi_import_declaration_binding', SUBJECT.verify_loaded, 'certifi', module, bound, bound)

    def test_certifi_origin_alias_and_cached_bytecode_guards_remain(self):
        for kind, code in [('origin', 'actual_import_binding'), ('alias', 'loaded_module_alias_identity'),
                           ('cached', 'loaded_cached_bytecode')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                module, bound = self.certifi(directory)
                if kind == 'origin':
                    bound = {}
                elif kind == 'alias':
                    module.__name__ = 'unknown'
                else:
                    cached = Path(directory).resolve() / 'owned.pyc'
                    cached.write_bytes(b'inert cached marker');module.__cached__ = str(cached)
                with owned_modules({'certifi': module}):
                    self.reject(code, SUBJECT.verify_loaded, 'certifi', module, bound, bound)

    def test_other_module_version_comparison_remains_exact(self):
        module = types.ModuleType('requests')
        module.__version__ = '2.034.2'
        self.reject('actual_import_version', SUBJECT.verify_loaded, 'requests', module, {}, {})

    def test_module_failure_projection_has_only_safe_typed_versions(self):
        for value, kind, safe in [('2026.7.22', 'string', '2026.7.22'),
                                 ('/owned/private?token=SECRET', 'string', None),
                                 ('x' * 1000, 'string', None), (None, 'missing', None), (object(), 'other', None)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                module, bound = self.certifi(directory, value)
                try:
                    SUBJECT.verify_loaded('certifi', module, bound, bound)
                except SUBJECT.VerificationRejected as error:
                    diagnostic = SUBJECT.import_version_failure_diagnostic(error)
                else:
                    self.fail('owned wrong module version accepted')
                self.assertEqual(diagnostic, {'package': 'certifi', 'distribution_version': '2026.7.22',
                    'expected_module_version': '2026.07.22', 'actual_module_version': safe, 'actual_value_kind': kind})
                self.assertNotIn('SECRET', json.dumps(diagnostic))
        error = SUBJECT.VerificationRejected('actual_import_version')
        error.module_version_comparison = {**diagnostic, 'path': '/owned/private'}
        self.assertIsNone(SUBJECT.import_version_failure_diagnostic(error))

    def test_actual_failure_guard_keeps_exit2_and_safe_module_diagnostic(self):
        error = SUBJECT.VerificationRejected('actual_import_version')
        error.module_version_comparison = {'package': 'certifi', 'distribution_version': '2026.7.22',
            'expected_module_version': '2026.07.22', 'actual_module_version': '2026.7.22', 'actual_value_kind': 'string'}
        tree = ast.parse(SOURCE.read_bytes())
        guards = [node for node in tree.body if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name)
                  and node.test.left.id == '__name__']
        self.assertEqual(len(guards), 1)
        scope = dict(SUBJECT.__dict__);scope['__name__'] = '__main__'
        scope['main'] = types.SimpleNamespace()
        with patch.object(SUBJECT, 'main', side_effect=error) as main:
            scope['main'] = main
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), self.assertRaises(SystemExit) as stopped:
                exec(compile(ast.Module(body=guards, type_ignores=[]), '<actual-module-version-main-guard>', 'exec'), scope)
        self.assertEqual(stopped.exception.code, 2)
        result = json.loads(capture.getvalue())
        self.assertEqual(set(result), {'status', 'error_code', 'historical_environment_proof', 'module_version_comparison'})
        self.assertEqual(result['status'], 'UNPROVEN')
        self.assertEqual(result['module_version_comparison'], error.module_version_comparison)


class DependencyLogControls(unittest.TestCase):
    def project(self, proof):
        raw = SUBJECT.canonical(proof) + b'\n'
        return SUBJECT.dependency_log_projection(proof, raw, 'b' * 64), raw

    def reject(self, code, proof, raw=None):
        if raw is None:
            raw = SUBJECT.canonical(proof) + b'\n'
        with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^' + code + '$'):
            SUBJECT.dependency_log_projection(proof, raw, 'b' * 64)

    def test_current_closed_projection_binds_whole_proof_and_exact_package_facts(self):
        proof = owned_dependency_proof()
        summary, raw = self.project(proof)
        self.assertEqual(summary['proof_sha256'], SUBJECT.sha(raw))
        self.assertEqual(summary['proof_bytes'], len(raw))
        self.assertEqual(summary['verifier_sha256'], SUBJECT.sha(SOURCE.read_bytes()))
        self.assertEqual(summary['python'], {'implementation': 'CPython', 'version_info': [3, 11, 17],
            'isolated': True, 'dont_write_bytecode': True})
        self.assertEqual([row['name'] for row in summary['packages']], sorted(SUBJECT.VERSIONS))
        certifi = next(row for row in summary['packages'] if row['name'] == 'certifi')
        self.assertEqual((certifi['distribution_version'], certifi['module_version']), ('2026.7.22', '2026.07.22'))
        self.assertFalse(summary['optional_bootstrap'][0]['pinned_wheel_dependency'])
        self.assertFalse(summary['historical_environment_proof'])
        self.assertFalse(summary['qualification_or_human_gate_credit'])

    def test_private_extra_fields_and_paths_never_enter_log_projection(self):
        proof = owned_dependency_proof()
        marker = 'PRIVATE-CREDENTIAL-MARKER'
        proof['unknown_private'] = {'token': marker, 'provider': marker}
        proof['python']['executable'] = marker
        proof['packages'][0]['installed_record']['path'] = marker
        proof['packages'][0]['wheel']['url'] = marker
        proof['site_population']['optional_bootstrap'][0]['unknown_private'] = marker
        summary, raw = self.project(proof)
        text = json.dumps(summary)
        self.assertNotIn(marker, text)
        self.assertNotIn('/owned/private', text)
        self.assertNotIn('"url"', text)
        self.assertEqual(set(summary), {'schema', 'status', 'verifier_sha256', 'wheel_manifest_sha256',
            'proof_sha256', 'proof_bytes', 'python', 'packages', 'optional_bootstrap', 'site_population',
            'pair_host_installation_binding_required', 'historical_environment_proof',
            'HTTP_subprocess_or_target_execution', 'global_environment_changed', 'qualification_or_human_gate_credit'})

    def test_proof_bytes_identity_runtime_and_historical_flags_reject_tampering(self):
        proof = owned_dependency_proof()
        self.reject('dependency_log_proof_bytes', proof, SUBJECT.canonical(proof))
        self.reject('dependency_log_proof_bytes', proof, SUBJECT.canonical(proof) + b'\nchanged')
        for key, value in [('verifier_sha256', '0' * 64), ('wheel_manifest_sha256', '0' * 64),
                           ('historical_environment_proof', True), ('qualification_or_human_gate_credit', True)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(proof);changed[key] = value
                self.reject('dependency_log_proof_identity', changed)
        for key, value in [('version_info', [3, 12, 14]), ('version_info', [3, 11, True]),
                           ('isolated', False), ('dont_write_bytecode', False)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(proof);changed['python'][key] = value
                self.reject('dependency_log_runtime', changed)

    def test_package_population_exact_versions_hashes_and_origin_cache_flags_reject(self):
        proof = owned_dependency_proof()
        changed = copy.deepcopy(proof);changed['packages'].pop()
        self.reject('dependency_log_package_population', changed)
        changed = copy.deepcopy(proof);changed['packages'][-1] = copy.deepcopy(changed['packages'][0])
        self.reject('dependency_log_package_identity', changed)
        for key, value in [('version', '0'), ('module_version', '2026.7.22'),
                           ('source_or_extension_origins_verified', False), ('no_cached_bytecode', False),
                           ('loaded_module_count', True)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(proof);changed['packages'][0][key] = value
                self.reject('dependency_log_package_facts', changed)
        for container, key, value in [('wheel', 'sha256', '0' * 64), ('wheel', 'bytes', True),
                ('installed_record', 'sha256', '/owned/private'), ('installed_record', 'bytes', 0),
                ('installed_record', 'hashed_files_verified', 2049), ('installed_record', 'all_hashed_files_verified', False)]:
            with self.subTest(container=container, key=key):
                changed = copy.deepcopy(proof);changed['packages'][0][container][key] = value
                self.reject('dependency_log_package_facts', changed)

    def test_site_ownership_bootstrap_population_identity_and_bounds_reject(self):
        proof = owned_dependency_proof()
        for key, value in [('all_site_files_record_owned', False), ('site_file_count', True), ('site_file_count', 20001)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(proof);changed['site_population'][key] = value
                self.reject('dependency_log_site_population', changed)
        for key, value in [('name', 'unknown'), ('version', '/owned/private'), ('record_sha256', 'INVALID'),
                           ('hashed_files_verified', True), ('pinned_wheel_dependency', True)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(proof);changed['site_population']['optional_bootstrap'][0][key] = value
                self.reject('dependency_log_bootstrap', changed)
        changed = copy.deepcopy(proof)
        changed['site_population']['optional_bootstrap'].append(copy.deepcopy(changed['site_population']['optional_bootstrap'][0]))
        self.reject('dependency_log_bootstrap', changed)

    def test_actual_main_writes_private_proof_and_logs_only_bound_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / 'private-proof.json'
            proof = owned_dependency_proof()
            arguments = ['owned', '--wheel-directory', directory, '--wheel-manifest', directory + '/manifest.json',
                '--wheel-manifest-sha256', 'b' * 64, '--venv', directory, '--output', str(output)]
            capture = io.StringIO()
            with patch.object(sys, 'argv', arguments), patch.object(SUBJECT, 'produce', return_value=proof), contextlib.redirect_stdout(capture):
                SUBJECT.main()
            raw = output.read_bytes()
            self.assertEqual(raw, SUBJECT.canonical(proof) + b'\n')
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(json.loads(capture.getvalue())['proof_sha256'], SUBJECT.sha(raw))
            self.assertNotIn('/owned/private', capture.getvalue())

    def test_invalid_log_projection_keeps_gate_failure_and_creates_no_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / 'private-proof.json'
            proof = owned_dependency_proof();proof['packages'][0]['no_cached_bytecode'] = False
            arguments = ['owned', '--wheel-directory', directory, '--wheel-manifest', directory + '/manifest.json',
                '--wheel-manifest-sha256', 'b' * 64, '--venv', directory, '--output', str(output)]
            capture = io.StringIO()
            with patch.object(sys, 'argv', arguments), patch.object(SUBJECT, 'produce', return_value=proof), contextlib.redirect_stdout(capture):
                with self.assertRaisesRegex(SUBJECT.VerificationRejected, '^dependency_log_package_facts$'):
                    SUBJECT.main()
            self.assertFalse(output.exists())
            self.assertEqual(capture.getvalue(), '')


if __name__ == '__main__':
    unittest.main()

