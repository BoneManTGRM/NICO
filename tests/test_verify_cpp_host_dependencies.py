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


if __name__ == '__main__':
    unittest.main()
