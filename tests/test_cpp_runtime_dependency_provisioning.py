"""Exercise real archive verification; only the HTTPS download is substituted."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts.provision_cpp_runtime_dependencies import provision


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as bundle:
        for path, raw, kind in entries:
            member = tarfile.TarInfo(path)
            member.mode = 0o755
            if kind == 'symlink':
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
                bundle.addfile(member)
            else:
                member.size = len(raw)
                bundle.addfile(member, io.BytesIO(raw))
    return output.getvalue()


def inputs(tmp_path, entries=None):
    binary = b'\x7fELF' + b'owned-no-execution-fixture'*4
    raw = archive(entries or [('release/bin/program', binary, 'file'),
                             ('release/README', b'not selected', 'file')])
    license_path = tmp_path/'LICENSE.fixture'
    license_path.write_bytes(b'Owned test fixture, not a third-party distribution.\n')
    value = {'schema': 'nico.cpp-runtime-dependencies.v1', 'packages': [{
        'id': 'owned-previous-release', 'url': 'https://bitcoincore.org/bin/owned/fixture.tar.gz',
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'members': {'release/bin/program': 'previous-releases/v1/bin/program'},
        'license_file': 'LICENSE.fixture',
        'license_sha256': hashlib.sha256(license_path.read_bytes()).hexdigest(),
    }]}
    lock = tmp_path/'lock.json'; lock.write_text(json.dumps(value))
    calls = []
    def download(argv, **kwargs):
        calls.append((argv, kwargs))
        Path(argv[argv.index('--output')+1]).write_bytes(raw)
    return lock, value, binary, calls, download


def test_required_fixture_is_hash_verified_staged_and_never_executed(tmp_path):
    lock, value, binary, calls, download = inputs(tmp_path)
    destination = tmp_path/'staged'
    result = provision(destination, lock_path=lock, run=download)
    assert result['status'] == 'VERIFIED_RUNTIME_DEPENDENCIES'
    assert result['target_executed'] is False
    staged = destination/'payload/previous-releases/v1/bin/program'
    assert staged.read_bytes() == binary
    assert staged.stat().st_mode & 0o777 == 0o555
    assert len(calls) == 1 and calls[0][0][0] == 'curl'
    assert calls[0][1]['timeout'] <= 41
    assert '--proto' in calls[0][0] and '=https' in calls[0][0]
    assert '--location' not in calls[0][0]
    assert 'GITHUB_TOKEN' not in calls[0][1]['env']
    row = result['packages'][0]
    assert row['archive_sha256'] == value['packages'][0]['sha256']
    assert row['members'][0]['sha256'] == hashlib.sha256(binary).hexdigest()
    assert not (destination/'payload/README').exists()
    assert json.loads((destination/'receipt.json').read_text()) == result
    assert (destination/'payload/licenses/owned-previous-release.txt').is_file()
    assert 'previous-releases/v1/bin/program' in (destination/'SHA256SUMS').read_text()


@pytest.mark.parametrize('fault', ['hash', 'size', 'missing', 'symlink', 'duplicate', 'traversal'])
def test_invalid_runtime_fixture_cannot_become_verified(tmp_path, fault):
    entries = None
    if fault == 'missing':
        entries = [('release/other', b'not the binary', 'file')]
    elif fault == 'symlink':
        entries = [('release/bin/program', b'', 'symlink')]
    elif fault == 'duplicate':
        entries = [('release/bin/program', b'\x7fELFone', 'file'),
                   ('release/bin/program', b'\x7fELFtwo', 'file')]
    elif fault == 'traversal':
        entries = [('release/bin/program', b'\x7fELFone', 'file'),
                   ('../escape', b'bad', 'file')]
    lock, value, binary, calls, download = inputs(tmp_path, entries)
    if fault == 'hash':
        value['packages'][0]['sha256'] = '0'*64
    if fault == 'size':
        value['packages'][0]['bytes'] += 1
    lock.write_text(json.dumps(value))
    destination = tmp_path/'staged'
    with pytest.raises(ValueError, match='cpp_runtime_dependency_'):
        provision(destination, lock_path=lock, run=download)
    receipt = json.loads((destination/'receipt.json').read_text())
    assert receipt['status'] == 'UNPROVEN' and receipt['error']
    assert receipt['target_executed'] is False
    assert not (tmp_path/'escape').exists()
    assert not (destination/'SHA256SUMS').exists()


@pytest.mark.parametrize('url', ['http://bitcoincore.org/bin/owned/fixture.tar.gz',
    'https://bitcoincore.org.evil.invalid/bin/owned/fixture.tar.gz',
    'https://bitcoincore.org/bin/../private/fixture.tar.gz',
    'https://user:secret@bitcoincore.org/bin/owned/fixture.tar.gz',
    'https://bitcoincore.org/bin/owned/fixture.tar.gz?override=1'])
def test_runtime_dependency_lock_cannot_redirect_or_downgrade_download(tmp_path, url):
    lock, value, binary, calls, download = inputs(tmp_path)
    value['packages'][0]['url'] = url; lock.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='cpp_runtime_dependency_'):
        provision(tmp_path/'staged', lock_path=lock, run=download)
    assert calls == [] and not (tmp_path/'staged').exists()


@pytest.mark.parametrize('destination', ['../escape', '/tmp/escape', 'previous-releases/../../escape'])
def test_runtime_member_destination_is_validated_before_network(tmp_path, destination):
    lock, value, binary, calls, download = inputs(tmp_path)
    value['packages'][0]['members'] = {'release/bin/program': destination}
    lock.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='cpp_runtime_dependency_member_invalid'):
        provision(tmp_path/'staged', lock_path=lock, run=download)
    assert calls == []


def test_runtime_dependency_license_must_match_before_download(tmp_path):
    lock, value, binary, calls, download = inputs(tmp_path)
    (tmp_path/'LICENSE.fixture').write_text('changed')
    with pytest.raises(ValueError, match='cpp_runtime_dependency_license_invalid'):
        provision(tmp_path/'staged', lock_path=lock, run=download)
    assert calls == []


def test_existing_runtime_dependency_output_is_not_overwritten(tmp_path):
    lock, value, binary, calls, download = inputs(tmp_path)
    destination = tmp_path/'staged'; destination.mkdir()
    sentinel = destination/'receipt.json'; sentinel.write_text('preserved')
    with pytest.raises(FileExistsError):
        provision(destination, lock_path=lock, run=download)
    assert sentinel.read_text() == 'preserved' and calls == []


def test_release_owned_lock_and_both_image_build_paths_stage_required_prerequisites():
    from scripts.provision_cpp_runtime_dependencies import LOCK, validate_lock
    rows = validate_lock(json.loads(LOCK.read_text()))
    assert rows[0]['sha256'] == '706e0472dbc933ed2757650d54cbcd780fd3829ebf8f609b32780c7eedebdbc9'
    assert rows[0]['bytes'] == 24644309
    assert set(rows[0]['members']) == {'bitcoin-0.14.3/bin/bitcoind', 'bitcoin-0.14.3/bin/bitcoin-cli'}
    root = Path(__file__).resolve().parents[1]
    workflow = (root/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert workflow.count('python -m scripts.provision_cpp_runtime_dependencies --destination toolchain/full-project/runtime-dependencies') == 2
    assert 'tests/test_cpp_runtime_dependency_provisioning.py' in workflow
    image = (root/'docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert 'COPY runtime-dependencies/payload /opt/nico-runtime' in image
    assert 'ENV PREVIOUS_RELEASES_DIR=/opt/nico-runtime/previous-releases' in image
    assert 'sha256sum -c /opt/nico-runtime-inputs/SHA256SUMS' in image
    assert 'bitcoind --version' not in image  # No target executable runs during provisioning.
