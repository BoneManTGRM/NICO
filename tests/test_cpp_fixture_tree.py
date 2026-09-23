"""Real Git-object regression for nested owned source/corpus paths."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from nico.repository_snapshot import _git_environment
from scripts import qualify_cpp_full_project_integration as control


def git_runner(root):
    root.mkdir()
    env = _git_environment(root)
    def git(*args, data=None):
        return subprocess.run(['git', *args], cwd=root, env=env, input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10).stdout.rstrip(b'\n').decode()
    git('init', '--bare', '.')
    return git


@pytest.mark.parametrize('generated,fuzz', [(False, False), (True, False), (False, True), (True, True)])
def test_actual_fixture_tree_retains_all_original_paths_and_bytes(tmp_path, generated, fuzz):
    git = git_runner(tmp_path / 'git')
    files = control.fixture(generated_headers=generated, bounded_fuzz=fuzz)
    before = dict(files)
    tree = control.write_fixture_tree(git, files)
    observed = git('ls-tree', '-r', '--name-only', tree).splitlines()
    assert observed == sorted(files)
    for path, content in files.items():
        oid = git('rev-parse', tree + ':' + path)
        assert oid == hashlib.sha1(b'blob ' + str(len(content.encode())).encode() + b'\0' + content.encode(), usedforsecurity=False).hexdigest()
    assert files == before
    assert tree == control.write_fixture_tree(git, dict(reversed(list(files.items()))))
    if not fuzz:
        # Preserve the earlier flat-fixture identities byte for byte.
        legacy = ''.join(f"100644 blob {git('hash-object', '-w', '--stdin', data=text.encode())}\t{name}\n"
                         for name, text in sorted(files.items()))
        assert tree == git('mktree', data=legacy.encode())


def test_multiple_nested_levels_and_whitespace_are_encoded_as_literal_names(tmp_path):
    git = git_runner(tmp_path / 'git')
    files = {'a/b/c': 'nested', 'a/b/empty': '', 'a space': 'literal', 'z': 'last'}
    tree = control.write_fixture_tree(git, files)
    assert git('ls-tree', '-r', '--name-only', tree).splitlines() == sorted(files)
    assert git('cat-file', 'blob', tree + ':a/b/c') == 'nested'


@pytest.mark.parametrize('files', [
    {'../outside': 'x'}, {'/absolute': 'x'}, {'a//b': 'x'}, {'a/./b': 'x'},
    {'.git/config': 'x'}, {'a\nname': 'x'}, {'a\x00name': 'x'},
    {'a': 'blob', 'a/b': 'nested'}, {'a/b': 'nested', 'a': 'blob'}, {'a': b'not text'},
])
def test_invalid_owned_fixture_is_rejected_before_writing_objects(files):
    called = []
    def git(*args, **kwargs):
        called.append(args)
        raise AssertionError('invalid fixture reached Git')
    with pytest.raises(ValueError, match='owned_fixture_'):
        control.write_fixture_tree(git, files)
    assert called == []
