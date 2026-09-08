from pathlib import Path
from types import SimpleNamespace

import pytest

from nico import github_app_auth, snapshot_scanner_worker as worker
from nico.scanner_determinism_v1 import clone_repository_at_snapshot


SHA = 'a' * 40
PRIVATE = {'NICO_PROVIDER_ACCESS_MODE': 'authenticated_read_only',
           'NICO_PROVIDER_CREDENTIAL_USED': 'true'}


def test_private_snapshot_fetch_uses_existing_auth_without_leaking_to_scanners(monkeypatch, tmp_path):
    calls = []
    # Synthetic header, never a real credential.
    header = 'AUTHORIZATION: basic synthetic-checkout-fixture'
    auth_env = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
                'GIT_CONFIG_VALUE_0': header}
    monkeypatch.setattr(github_app_auth, 'build_github_clone_auth_env', lambda: SimpleNamespace(
        extra_env=auth_env, mode='server_token', evidence=[], unavailable=[]))

    def git(command, *, cwd, env, timeout=90):
        calls.append((command, dict(env)))
        if 'fetch' in command and env.get('GIT_CONFIG_VALUE_0') != header:
            return SimpleNamespace(returncode=128, stdout='', stderr='Authentication required')
        return SimpleNamespace(returncode=0, stdout=SHA if command[-2:] == ['rev-parse', 'HEAD'] else '', stderr='')

    monkeypatch.setattr(worker, '_git', git)
    original = dict(PRIVATE)
    repo, actual, notes = clone_repository_at_snapshot('owner/private-repo', SHA, tmp_path, original)
    assert (repo, actual, notes) == (tmp_path / 'repo', SHA, [])
    assert original == PRIVATE, 'scanner environment must not receive checkout credentials'
    for command, env in calls:
        assert header not in ' '.join(command)
        if 'fetch' in command:
            assert env['GIT_CONFIG_VALUE_0'] == header
            assert env['GIT_TERMINAL_PROMPT'] == '0'
            assert 'http.followRedirects=false' in command
            assert 'credential.helper=' in command
            assert command[-1] == SHA
            assert '--depth' not in command and '--filter' not in command
        else:
            assert header not in env.values()
    assert not any(header in p.read_text(errors='replace') for p in tmp_path.rglob('*') if p.is_file())


@pytest.mark.parametrize('access', [{}, {'NICO_PROVIDER_ACCESS_MODE': 'anonymous_public', 'NICO_PROVIDER_CREDENTIAL_USED': 'false'}])
def test_public_checkout_never_resolves_server_credentials(monkeypatch, tmp_path, access):
    def forbidden():
        pytest.fail('anonymous checkout must not acquire credentials')
    monkeypatch.setattr(github_app_auth, 'build_github_clone_auth_env', forbidden)
    monkeypatch.setattr(worker, '_git', lambda command, **kwargs: SimpleNamespace(
        returncode=0, stdout=SHA if command[-2:] == ['rev-parse', 'HEAD'] else '', stderr=''))
    assert clone_repository_at_snapshot('owner/public-repo', SHA, tmp_path, access)[1] == SHA


@pytest.mark.parametrize('access', [
    {'NICO_PROVIDER_ACCESS_MODE': 'authenticated_read_only', 'NICO_PROVIDER_CREDENTIAL_USED': 'false'},
    {'NICO_PROVIDER_ACCESS_MODE': 'anonymous_public', 'NICO_PROVIDER_CREDENTIAL_USED': 'true'},
    {'NICO_PROVIDER_ACCESS_MODE': 'authenticated_read_only'},
    {'NICO_PROVIDER_ACCESS_MODE': 'auto', 'NICO_PROVIDER_CREDENTIAL_USED': 'true'},
])
def test_inconsistent_frozen_access_cannot_fetch(monkeypatch, tmp_path, access):
    monkeypatch.setattr(worker, '_git', lambda *args, **kwargs: pytest.fail('invalid access must stop before Git'))
    repo, _, notes = clone_repository_at_snapshot('owner/private-repo', SHA, tmp_path, access)
    assert repo is None
    assert notes == ['github_snapshot_access_binding_invalid']


def test_missing_private_credential_cannot_fall_back_to_anonymous(monkeypatch, tmp_path):
    monkeypatch.setattr(github_app_auth, 'build_github_clone_auth_env', lambda: SimpleNamespace(
        extra_env={}, mode='anonymous', evidence=[], unavailable=[]))
    monkeypatch.setattr(worker, '_git', lambda *args, **kwargs: pytest.fail('missing credential must stop before Git'))
    repo, _, notes = clone_repository_at_snapshot('owner/private-repo', SHA, tmp_path, dict(PRIVATE))
    assert repo is None
    assert notes == ['github_snapshot_checkout_credential_unavailable']


def test_private_fetch_failure_does_not_disclose_process_output(monkeypatch, tmp_path):
    header = 'AUTHORIZATION: basic synthetic-private-header'
    monkeypatch.setattr(github_app_auth, 'build_github_clone_auth_env', lambda: SimpleNamespace(
        extra_env={'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
                   'GIT_CONFIG_VALUE_0': header}, mode='server_token', evidence=[], unavailable=[]))
    monkeypatch.setattr(worker, '_git', lambda command, **kwargs: SimpleNamespace(
        returncode=128 if 'fetch' in command else 0, stdout='', stderr=header))
    repo, _, notes = clone_repository_at_snapshot('owner/private-repo', SHA, tmp_path, dict(PRIVATE))
    assert repo is None
    assert notes == ['github_authenticated_snapshot_fetch_failed']


def test_github_scan_persists_frozen_access_for_later_recovery(monkeypatch):
    from tests.test_scanner_recovery import _MemoryStore
    store = _MemoryStore([])
    monkeypatch.setattr(worker, 'STORE', store)
    monkeypatch.setattr(worker, 'threading', SimpleNamespace(Thread=lambda **kw: SimpleNamespace(start=lambda: None)))
    result = worker.start_snapshot_scan(dict(repository='owner/private-repo', snapshot_id='snapshot_private', snapshot_commit_sha=SHA, run_id='comprun_private', authorized=True, authorized_by='owner', authorization_scope='defensive assessment', provider_access_mode='authenticated_read_only', provider_credential_used=True, tools=['gitleaks']))
    saved = store.records[result['scan_id']]
    assert saved['provider_access_mode'] == 'authenticated_read_only'
    assert saved['provider_credential_used'] is True
