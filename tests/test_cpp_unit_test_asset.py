import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from scripts import stage_cpp_unit_test_asset as proposal


def test_pinned_identity_and_workflow_acceptance_remain_fixed():
    root = Path(__file__).resolve().parents[1]
    assert proposal.URL == ('https://github.com/bitcoin-core/qa-assets/raw/'
        'b33d85102d169b54d966ea315ad81a636680aefa/unit_test_data/script_assets_test.json')
    assert proposal.EXPECTED_BYTES == 9243520
    assert proposal.EXPECTED_SHA256 == 'cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095'
    workflow = (root / '.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_unit_test_asset.py' in workflow
    assert 'python -m scripts.stage_cpp_unit_test_asset --destination qualification-unit-test-data/script_assets_test.json' in workflow
    assert 'timeout --kill-after=1s 90s python -m scripts.stage_cpp_unit_test_asset' in workflow
    assert proposal.EXPECTED_SHA256 + "  qualification-unit-test-data/script_assets_test.json' | sha256sum -c -" in workflow
    assert 'test "$(wc -c < qualification-unit-test-data/script_assets_test.json)" -eq 9243520' in workflow

@pytest.mark.parametrize('responses,expected,attempts', [
    (['504', '504', '200'], None, 3),
    (['504'] * 4, 'failed', 4),
    (['404'], 'failed', 1),
    (['tls'], 'failed', 1),
    (['corrupt'], 'hash_invalid', 1),
    (['oversized'], 'size_invalid', 1),
    (['timeout', '200'], None, 2),
    (['deadline'], 'deadline', 1),
])
def test_owned_transport_outcomes(tmp_path, monkeypatch, responses, expected, attempts):
    payload = b'owned'
    monkeypatch.setattr(proposal, 'EXPECTED_BYTES', len(payload))
    monkeypatch.setattr(proposal, 'EXPECTED_SHA256', hashlib.sha256(payload).hexdigest())
    now, calls, delays = [0], [], []
    def pause(delay):
        delays.append(delay); now[0] += delay
    def run(argv, **kwargs):
        action = responses[len(calls)]; calls.append((argv, kwargs)); now[0] += 1
        assert argv[1] == '--disable'
        assert argv[-1] == proposal.URL
        assert kwargs['timeout'] <= 21 and '--fail' in argv and '--max-filesize' in argv
        if action in ('timeout', 'deadline'):
            if action == 'deadline': now[0] = 91
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        output = Path(argv[argv.index('--output') + 1])
        assert not output.exists(), 'every attempt must start without partial bytes'
        output.write_bytes(b'bad!!' if action == 'corrupt' else payload + b'!' if action == 'oversized' else payload)
        code = 60 if action == 'tls' else 22 if action in ('504', '404') else 0
        return SimpleNamespace(returncode=code, stdout=action if code else '200')
    destination = tmp_path / 'asset.json'
    if expected:
        with pytest.raises(ValueError, match='asset_download_' + expected):
            proposal.stage(destination, run=run, clock=lambda: now[0], pause=pause)
        assert not destination.exists()
    else:
        proposal.stage(destination, run=run, clock=lambda: now[0], pause=pause)
        assert destination.read_bytes() == payload
    assert len(calls) == attempts
    assert delays == [2, 4, 8][:attempts - 1]
    assert not list(tmp_path.glob('.unit-asset-*'))


@pytest.mark.parametrize('status', ['408', '429', '500', '502', '503', '504'])
def test_only_allowlisted_http_failures_can_retry(tmp_path, status):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=22, stdout=status)
    with pytest.raises(ValueError, match='asset_download_failed'):
        proposal.stage(tmp_path / 'asset', run=run, clock=lambda: 0, pause=lambda seconds: None)
    assert len(calls) == 4


@pytest.mark.parametrize('code,status', [(22, '401'), (22, '403'), (22, '404'),
    (22, '501'), (6, '000'), (60, '000'), (63, '200'), (0, '206'), (0, '200\nPRIVATE')])
def test_nonallowlisted_errors_never_retry_or_publish(tmp_path, code, status):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=code, stdout=status)
    with pytest.raises(ValueError, match='asset_download_failed'):
        proposal.stage(tmp_path / 'asset', run=run, pause=lambda seconds: pytest.fail('unexpected retry'))
    assert len(calls) == 1 and not (tmp_path / 'asset').exists()


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'directory', 'missing'])
def test_untrusted_transfer_file_cannot_be_published(tmp_path, kind):
    secret = tmp_path / 'private'
    secret.write_bytes(b'PRIVATE')
    def run(argv, **kwargs):
        import os
        path = Path(argv[argv.index('--output') + 1])
        if kind == 'symlink': path.symlink_to(secret)
        elif kind == 'fifo': os.mkfifo(path)
        elif kind == 'directory': path.mkdir()
        return SimpleNamespace(returncode=0, stdout='200')
    with pytest.raises((OSError, ValueError)):
        proposal.stage(tmp_path / 'asset', run=run)
    assert secret.read_bytes() == b'PRIVATE'
    assert not (tmp_path / 'asset').exists() and not list(tmp_path.glob('.unit-asset-*'))


@pytest.mark.parametrize('symlink', [False, True])
def test_existing_destination_is_never_replaced(tmp_path, monkeypatch, symlink):
    payload = b'owned'
    monkeypatch.setattr(proposal, 'EXPECTED_BYTES', len(payload))
    monkeypatch.setattr(proposal, 'EXPECTED_SHA256', hashlib.sha256(payload).hexdigest())
    destination = tmp_path / 'asset'
    if symlink: destination.symlink_to(tmp_path / 'absent')
    else: destination.write_bytes(b'original')
    def run(argv, **kwargs):
        Path(argv[argv.index('--output') + 1]).write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout='200')
    with pytest.raises(FileExistsError): proposal.stage(destination, run=run)
    assert destination.is_symlink() if symlink else destination.read_bytes() == b'original'
    assert not list(tmp_path.glob('.unit-asset-*'))


def test_total_deadline_includes_transfer_grace_and_backoff(tmp_path):
    now, timeouts, delays = [0], [], []
    def run(argv, **kwargs):
        timeouts.append(kwargs['timeout'])
        now[0] += kwargs['timeout']
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    def pause(delay):
        delays.append(delay); now[0] += delay
    with pytest.raises(ValueError, match='asset_download_deadline'):
        proposal.stage(tmp_path / 'asset', run=run, clock=lambda: now[0], pause=pause)
    assert timeouts == [21, 21, 21, 13] and delays == [2, 4, 8]
    assert now[0] == 90 and not (tmp_path / 'asset').exists()


def test_changed_transfer_file_cannot_replace_verified_bytes(tmp_path, monkeypatch):
    payload, paths = b'owned', []
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(proposal, 'EXPECTED_BYTES', len(payload))
    monkeypatch.setattr(proposal, 'EXPECTED_SHA256', digest)
    original_sha256 = hashlib.sha256
    def run(argv, **kwargs):
        path = Path(argv[argv.index('--output') + 1])
        paths.append(path); path.write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout='200')
    def hashing(raw):
        # Model a late write to the transfer file after the verified read.
        paths[0].write_bytes(b'other')
        return original_sha256(raw)
    monkeypatch.setattr(proposal.hashlib, 'sha256', hashing)
    destination = tmp_path / 'asset'
    proposal.stage(destination, run=run)
    assert destination.read_bytes() == payload


def test_cli_failure_is_nonzero_and_never_echoes_transport_details(tmp_path, monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, 'argv', ['stage', '--destination', str(tmp_path / 'asset')])
    def fail(destination): raise OSError('PRIVATE transport detail')
    monkeypatch.setattr(proposal, 'stage', fail)
    assert proposal.main() == 1
    assert capsys.readouterr().out == '{"status": "UNPROVEN", "error": "asset_download_failed"}\n'


def test_outer_timeout_stops_stalled_publication_without_a_final_asset(tmp_path):
    import sys
    harness = '''
import hashlib, sys, time
from pathlib import Path
from types import SimpleNamespace
from scripts import stage_cpp_unit_test_asset as m
root = Path(sys.argv[1])
m.EXPECTED_BYTES = 5
m.EXPECTED_SHA256 = hashlib.sha256(b'owned').hexdigest()
def run(argv, **kwargs):
    Path(argv[argv.index('--output') + 1]).write_bytes(b'owned')
    return SimpleNamespace(returncode=0, stdout='200')
def blocked_fsync(fd):
    (root/'entered-fsync').touch()
    time.sleep(20)
m.os.fsync = blocked_fsync
m.stage(root/'asset', run=run)
'''
    # Scale only time values; exercise real process termination at the I/O seam.
    result = subprocess.run(['timeout', '--kill-after=0.2s', '2s', sys.executable,
        '-c', harness, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, timeout=5, check=False)
    assert result.returncode == 124, result.stderr
    assert (tmp_path / 'entered-fsync').exists()
    assert not (tmp_path / 'asset').exists()
