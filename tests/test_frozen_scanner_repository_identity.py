"""Real disposable local Git clones; no scanners, network evidence, or assessment."""
import subprocess
import traceback
from unittest.mock import Mock

import pytest

from scripts import frozen_scanner_evidence_proof as proof
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import nico_ci_typescript_consumer_v1 as consumer

REPOSITORY = 'BoneManTGRM/NICO'
CANONICAL = 'https://github.com/BoneManTGRM/NICO.git'


def git(source, *args):
    return proof.run_git(*args, cwd=source)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'config', 'user.name', 'Owned fixture')
    for number in range(3):
        (root / 'owned.txt').write_text(str(number))
        git(root, 'add', 'owned.txt')
        git(root, 'commit', '-qm', f'Owned fixture {number}')
    git(root, 'remote', 'add', 'origin', CANONICAL)
    return root


def prepare(source, tmp_path, repository=REPOSITORY, sha=None):
    return proof.prepare_checkout(source, tmp_path / 'disposable', sha or git(source, 'rev-parse', 'HEAD'), repository)


@pytest.mark.parametrize('origin', [
    CANONICAL, 'https://github.com/BoneManTGRM/NICO',
    'https://github.com/BoneManTGRM/NICO.git/',
    'git@github.com:BoneManTGRM/NICO.git',
    'ssh://git@github.com/BoneManTGRM/NICO.git',
    'https://synthetic-user:synthetic-private@github.com/BoneManTGRM/NICO.git',
])
def test_real_clone_retains_validated_identity_exact_commit_and_history(source, tmp_path, origin):
    git(source, 'remote', 'set-url', 'origin', origin)
    original_head = git(source, 'rev-parse', 'HEAD')
    target = git(source, 'rev-parse', 'HEAD~1')
    workspace = prepare(source, tmp_path, sha=target)
    assert git(workspace.repo_dir, 'remote', 'get-url', 'origin') == CANONICAL
    assert git(workspace.repo_dir, 'rev-parse', 'HEAD') == target
    assert git(workspace.repo_dir, 'rev-list', 'HEAD') == git(source, 'rev-list', target)
    assert git(workspace.repo_dir, 'rev-parse', '--is-shallow-repository') == 'false'
    assert pipeline._owned_nico_ci(workspace) is True
    assert pipeline._target_repository(workspace) == REPOSITORY
    assert 'synthetic-private' not in (workspace.repo_dir / '.git/config').read_text()
    assert git(source, 'config', '--get', 'remote.origin.url') == origin
    assert git(source, 'rev-parse', 'HEAD') == original_head


def test_real_local_clone_routes_to_retained_typescript_consumer(source, tmp_path, monkeypatch):
    workspace = prepare(source, tmp_path)
    retained = {'status': 'unavailable', 'reason': 'synthetic authenticated evidence absent'}
    consume = Mock(return_value=retained)
    runner = Mock(side_effect=AssertionError('project execution forbidden'))
    monkeypatch.setattr(consumer, 'run', consume)
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false')
    spec = next(spec for spec in proof.TOOL_SPECS if spec.name == 'typescript')
    assert pipeline._run_typescript(spec, workspace, runner, None) is retained
    consume.assert_called_once_with(spec, workspace)
    runner.assert_not_called()
    # Routing must not turn missing authenticated evidence into a completed scan.
    assert retained['status'] == 'unavailable'


def test_generic_github_repository_is_not_nico(source, tmp_path, monkeypatch):
    git(source, 'remote', 'set-url', 'origin', 'git@github.com:example/ordinary.git')
    workspace = prepare(source, tmp_path, repository='example/ordinary')
    assert git(workspace.repo_dir, 'remote', 'get-url', 'origin') == 'https://github.com/example/ordinary.git'
    assert pipeline._owned_nico_ci(workspace) is False
    consume = Mock(side_effect=AssertionError('NICO evidence must not cover a generic repository'))
    runner = Mock(side_effect=AssertionError('project execution forbidden'))
    monkeypatch.setattr(consumer, 'run', consume)
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false')
    spec = next(spec for spec in proof.TOOL_SPECS if spec.name == 'typescript')
    result = pipeline._run_typescript(spec, workspace, runner, None)
    assert result['status'] == 'unavailable'
    consume.assert_not_called()
    runner.assert_not_called()


@pytest.mark.parametrize('origin', [
    None, '/tmp/local-source', 'file:///tmp/local-source',
    'https://gitlab.com/BoneManTGRM/NICO.git',
    'https://github.com.evil.invalid/BoneManTGRM/NICO.git',
    'https://github.com@evil.invalid/BoneManTGRM/NICO.git',
    'http://github.com/BoneManTGRM/NICO.git',
    'ssh://other@github.com/BoneManTGRM/NICO.git',
    'https://github.com:444/BoneManTGRM/NICO.git',
    'https://github.com/BoneManTGRM/NICO.git?token=synthetic-private',
    'https://github.com/BoneManTGRM/NICO.git#synthetic-private',
    'https://github.com/other/repo.git',
    'https://github.com/BoneManTGRM/NICO/extra',
    'git@github.com:other/repo.git',
    'https://[invalid/synthetic-private',
])
def test_invalid_source_origin_rejected_before_clone_or_destination_changes(source, tmp_path, origin, capsys):
    if origin is None:
        git(source, 'remote', 'remove', 'origin')
    else:
        git(source, 'remote', 'set-url', 'origin', origin)
    destination = tmp_path / 'disposable'
    destination.mkdir()
    marker = destination / 'keep.txt'
    marker.write_text('unchanged')
    with pytest.raises(ValueError, match='frozen_proof_origin_') as caught:
        prepare(source, tmp_path)
    assert marker.read_text() == 'unchanged'
    assert not (destination / 'repo').exists()
    output = capsys.readouterr()
    assert 'synthetic-private' not in ''.join(traceback.format_exception(caught.value)) + output.out + output.err


def test_multiple_origins_fail_closed(source, tmp_path):
    git(source, 'config', '--add', 'remote.origin.url', 'https://github.com/other/repo.git')
    with pytest.raises(ValueError, match='origin_ambiguous'):
        prepare(source, tmp_path)
    assert not (tmp_path / 'disposable').exists()


@pytest.mark.parametrize('repository', ['other/repo', '../NICO', 'BoneManTGRM/NICO/extra', ''])
def test_repository_label_does_not_override_source_identity(source, tmp_path, repository, monkeypatch):
    scanners = Mock(side_effect=AssertionError('must reject identity before scanners'))
    monkeypatch.setattr(proof, 'run_canonical_scanner_tools', scanners)
    with pytest.raises(ValueError, match='frozen_proof_'):
        proof.run_once(source=source, target_sha=git(source, 'rev-parse', 'HEAD'), repository=repository,
                       output_root=tmp_path, run_number=1)
    scanners.assert_not_called()
    assert not (tmp_path / 'workspace-1').exists()


def test_spoofed_nico_label_cannot_relabel_generic_checkout(source, tmp_path):
    git(source, 'remote', 'set-url', 'origin', 'https://github.com/other/repo.git')
    with pytest.raises(ValueError, match='origin_repository_mismatch'):
        prepare(source, tmp_path, repository=REPOSITORY)


@pytest.mark.parametrize('sha', ['HEAD', '--help', 'a' * 39, 'f' * 40])
def test_wrong_or_non_exact_sha_never_reaches_scanners(source, tmp_path, sha, monkeypatch):
    scanners = Mock(side_effect=AssertionError('wrong SHA must not reach scanners'))
    monkeypatch.setattr(proof, 'run_canonical_scanner_tools', scanners)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        proof.run_once(source=source, target_sha=sha, repository=REPOSITORY, output_root=tmp_path, run_number=1)
    scanners.assert_not_called()
    assert not (tmp_path / 'scanner-run-1.json').exists()


def test_shallow_local_source_is_rejected(source, tmp_path):
    shallow = tmp_path / 'shallow'
    proof.run_git('clone', '--depth=1', source.as_uri(), str(shallow))
    git(shallow, 'remote', 'set-url', 'origin', CANONICAL)
    assert git(shallow, 'rev-parse', '--is-shallow-repository') == 'true'
    with pytest.raises(RuntimeError, match='checkout is shallow'):
        prepare(shallow, tmp_path)


@pytest.mark.parametrize('layout', [
    'equal', 'ancestor', 'descendant', 'missing_descendant',
    'destination_alias_equal', 'destination_alias_ancestor',
    'destination_alias_descendant', 'source_alias',
])
def test_checkout_overlap_fails_before_deletion_or_clone(source, tmp_path, monkeypatch, layout):
    target = git(source, 'rev-parse', 'HEAD')
    marker = source / 'preserve.txt'
    marker.write_text('source must survive')
    config = (source / '.git/config').read_bytes()
    source_arg = source
    destinations = {'equal': source, 'ancestor': tmp_path, 'descendant': source / 'child',
                    'missing_descendant': source / 'not-created' / 'child'}
    if layout.startswith('destination_alias_'):
        kind = layout.removeprefix('destination_alias_')
        destination = tmp_path / 'alias'
        referred = destinations[kind]
        referred.mkdir(exist_ok=True)
        destination.symlink_to(referred, target_is_directory=True)
    elif layout == 'source_alias':
        source_arg = tmp_path / 'source-alias'
        source_arg.symlink_to(source, target_is_directory=True)
        destination = source
    else:
        destination = destinations[layout]
        if layout != 'missing_descendant':
            destination.mkdir(exist_ok=True)
    remove = Mock(side_effect=AssertionError('must not delete overlapping paths'))
    execute = Mock(side_effect=AssertionError('must reject overlap before Git operations'))
    monkeypatch.setattr(proof.shutil, 'rmtree', remove)
    monkeypatch.setattr(proof.subprocess, 'run', execute)
    with pytest.raises(ValueError, match='frozen_proof_checkout_paths_overlap'):
        proof.prepare_checkout(source_arg, destination, target, REPOSITORY)
    remove.assert_not_called()
    execute.assert_not_called()
    assert marker.read_text() == 'source must survive'
    assert (source / '.git/config').read_bytes() == config
    assert not (source / 'not-created').exists()


@pytest.mark.parametrize('kind', ['directory', 'empty_directory', 'file', 'symlink', 'broken_symlink'])
def test_existing_destination_is_not_assumed_owned(source, tmp_path, monkeypatch, kind):
    destination = tmp_path / 'existing'
    marker = tmp_path / 'unrelated.txt'
    marker.write_text('unrelated data')
    if kind == 'directory':
        destination.mkdir()
        (destination / 'keep.txt').write_text('pre-existing output')
    elif kind == 'empty_directory':
        destination.mkdir()
    elif kind == 'file':
        destination.write_text('pre-existing file')
    elif kind == 'symlink':
        destination.symlink_to(marker)
    else:
        destination.symlink_to(tmp_path / 'absent')
    target = git(source, 'rev-parse', 'HEAD')
    config = (source / '.git/config').read_bytes()
    remove = Mock(side_effect=AssertionError('unowned destination must not be deleted'))
    monkeypatch.setattr(proof.shutil, 'rmtree', remove)
    with pytest.raises(ValueError, match='frozen_proof_destination_exists'):
        proof.prepare_checkout(source, destination, target, REPOSITORY)
    remove.assert_not_called()
    assert marker.read_text() == 'unrelated data'
    assert (source / '.git/config').read_bytes() == config
    assert destination.exists() or destination.is_symlink()
    assert not (tmp_path / 'absent').exists()
    if kind == 'directory':
        assert (destination / 'keep.txt').read_text() == 'pre-existing output'
    if kind == 'file':
        assert destination.read_text() == 'pre-existing file'
