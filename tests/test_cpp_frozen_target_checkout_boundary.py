"""New source-only owned tiny-Git boundary controls, for root execution.

No provider/native/target code runs. Git commands operate ONLY in newly owned
temporary repositories with inert fixture bytes. Original helper079 is loaded
unchanged; original-negative/new-positive @ evidence uses its actual checker.
The old17 caller tests remain byte-identical in their separate test file.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, path, digest=None):
    raw = path.read_bytes()
    if digest is not None:
        assert hashlib.sha256(raw).hexdigest() == digest, 'actual_immutable_control_source'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CALLER = load('owned_target_boundary_caller', ROOT / 'scripts/cpp_same_image_full_static_diagnostic.py')
HELPER = load('owned_original_image_helper', ROOT / 'scripts/cpp_diagnostic_image_rebuild.py',
              '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344')
SCOPE = load('owned_selected_target_scope', ROOT / 'scripts/cpp_static_runner_scope.py',
             '4929fc0909a336006633dca732b729fb9bda0669eff2f3e09c13fe2093d161c9')


class TargetCheckoutBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nico-owned-target-boundary-')
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repository'
        self.repo.mkdir(mode=0o700)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Owned inert control')
        self.git('config', 'user.email', 'owned-control@example.invalid')
        self.inventory = []
        fixtures = (
            ('src/qt/locale/owned_az@latin.ts', b'<TS>owned inert locale data</TS>\n', '100644'),
            ('owned+source.cpp', b'// Owned inert source; never compiled.\n', '100644'),
            ('owned-script.txt', b'# Owned inert data; never executed.\n', '100755'),
        )
        for name, raw, mode in fixtures:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o700 if mode == '100755' else 0o600)
            self.inventory.append({'path': name, 'bytes': len(raw), 'sha256': CALLER.sha(raw),
                                   'git_blob': SCOPE.git_blob(raw), 'git_mode': mode})
        self.git('add', '--all')
        self.git('commit', '-qm', 'Owned inert target boundary fixtures')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.tree = self.git('rev-parse', 'HEAD^{tree}').decode().strip()
        self.assertEqual(SCOPE.git_tree(self.inventory), self.tree)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments):
        return subprocess.run(['git', '-C', str(self.repo), *arguments], check=True,
                              capture_output=True, timeout=30).stdout

    def check(self, *, helper=HELPER, inventory=None, commit=None, tree=None, population=3):
        return CALLER.checked_target_checkout(self.repo, helper, SCOPE,
            self.inventory if inventory is None else inventory,
            expected_commit=self.commit if commit is None else commit,
            expected_tree=self.tree if tree is None else tree, expected_population=population)

    def test_original_negative_literal_at_path(self):
        with self.assertRaisesRegex(ValueError, '^unsafe_source_path$'):
            HELPER.checked_git_source(self.repo, self.commit, self.tree, 3)

    def test_new_positive_exact_owned_tree_and_modes(self):
        result = self.check()
        self.assertEqual(result['commit'], self.commit)
        self.assertEqual(result['tree'], self.tree)
        self.assertEqual(result['tracked_files'], 3)
        self.assertEqual(result['checkout_eol_differences'], [])
        self.assertEqual(len(result['tracked_byte_blob_mode_inventory_sha256']), 64)

    def test_wrong_head_and_tree_rejected(self):
        for arguments in ({'commit': '0' * 40}, {'tree': '0' * 40}):
            with self.subTest(arguments=arguments), self.assertRaises(CALLER.CallerRejected):
                self.check(**arguments)

    def test_wrong_population_or_duplicate_inventory_rejected(self):
        with self.assertRaises(CALLER.CallerRejected):
            self.check(population=4)
        inventory = [self.inventory[0], self.inventory[0], self.inventory[2]]
        with self.assertRaises(CALLER.CallerRejected):
            self.check(inventory=inventory)

    def test_wrong_pinned_blob_mode_or_sha_rejected(self):
        for key, value in (('git_blob', '0' * 40), ('git_mode', '120000'), ('sha256', '0' * 64)):
            inventory = [dict(row) for row in self.inventory]
            inventory[0][key] = value
            with self.subTest(key=key), self.assertRaises(CALLER.CallerRejected):
                self.check(inventory=inventory)

    def test_changed_bytes_dirty_index_and_mode_rejected(self):
        path = self.repo / self.inventory[0]['path']
        path.write_bytes(b'Owned altered data\n')
        with self.assertRaises(subprocess.CalledProcessError):
            self.check()
        self.git('add', '--all')
        with self.assertRaises(subprocess.CalledProcessError):
            self.check()

    def test_changed_executable_mode_rejected(self):
        path = self.repo / self.inventory[0]['path']
        path.chmod(0o700)
        with self.assertRaises((subprocess.CalledProcessError, CALLER.CallerRejected)):
            self.check()

    def test_symlink_worktree_rejected(self):
        path = self.repo / self.inventory[0]['path']
        path.unlink()
        path.symlink_to(self.repo / 'owned+source.cpp')
        with self.assertRaises((subprocess.CalledProcessError, CALLER.CallerRejected)):
            self.check()

    def listing_helper(self, transform):
        listing = self.git('ls-tree', '-rz', '--full-tree', 'HEAD')
        return types.SimpleNamespace(git_value=HELPER.git_value,
            command=lambda *_arguments, **_kwargs: transform(listing))

    def test_duplicate_missing_or_extra_git_members_rejected(self):
        extra = b'100644 blob ' + self.inventory[0]['git_blob'].encode() + b'\tunknown@locale.ts\0'
        transforms = (
            lambda raw: raw + raw.split(b'\0')[0] + b'\0',
            lambda raw: b'\0'.join(raw.split(b'\0')[1:]),
            lambda raw: raw + extra,
        )
        for transform in transforms:
            with self.subTest(transform=transform), self.assertRaises(CALLER.CallerRejected):
                self.check(helper=self.listing_helper(transform))

    def test_nonblob_git_entry_rejected(self):
        helper = self.listing_helper(lambda raw: raw.replace(b' blob ', b' tree ', 1))
        with self.assertRaises(CALLER.CallerRejected):
            self.check(helper=helper)

    def test_listing_path_escape_or_git_directory_rejected(self):
        for name in (b'../outside', b'/outside', b'.git/config', b'bad\\name'):
            def transform(raw):
                first, rest = raw.split(b'\0', 1)
                header, _ = first.split(b'\t', 1)
                return header + b'\t' + name + b'\0' + rest
            with self.subTest(name=name), self.assertRaises((CALLER.CallerRejected, SCOPE.Rejected)):
                self.check(helper=self.listing_helper(transform))


if __name__ == '__main__':
    unittest.main()
