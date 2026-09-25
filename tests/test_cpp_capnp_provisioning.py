"""The real Bitcoin configure failure requires a pinned tool, not scope removal."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from scripts import provision_cpp_fuzz_tools as tool

ROOT = Path(__file__).resolve().parents[1]
SHA256 = '77dbc13ca82d9c87ddb4581dd49559d45b63096433d3dadea08b7f31b360a5ba'


def source_lock():
    return {'schema': 'nico.cpp-capnp-source-lock.v1', 'packages': [
        {'package': 'capnproto', 'version': '1.5.0', 'architecture': 'source',
         'url': 'https://capnproto.org/capnproto-c++-1.5.0.tar.gz',
         'max_bytes': 4 * 1024 * 1024, 'sha256': hashlib.sha256(b'owned').hexdigest()}]}


def test_fixed_source_lock_is_supported_without_changing_legacy_locks():
    lock = source_lock()
    assert tool.validate_lock(lock) == lock['packages']
    from tests.test_cpp_project_dependencies import project_lock
    from tests.test_cpp_dependency_retention import expanded_lock
    for old in (project_lock(), expanded_lock(), json.loads(tool.LOCK.read_bytes())):
        assert tool.validate_lock(old) == old['packages']


@pytest.mark.parametrize('change', [
    {'package': '../outside'}, {'version': '0.9.2'}, {'architecture': 'amd64'},
    {'url': 'https://capnproto.org/../../x'}, {'url': 'https://evil.invalid/archive'},
    {'url': 'https://capnproto.org/capnproto-c++-1.5.0.tar.gz?token=x'},
    {'max_bytes': True}, {'max_bytes': 0}, {'max_bytes': 4194305}, {'sha256': 'x'},
])
def test_capnp_lock_rejects_substitution_and_unbounded_inputs(change):
    lock = source_lock(); lock['packages'][0].update(change)
    with pytest.raises(ValueError): tool.validate_lock(lock)


def test_capnp_input_is_verified_not_installed_and_shares_safe_transport(tmp_path, monkeypatch):
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(source_lock()))
    monkeypatch.setattr(tool, 'LOCK', lock)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert args[:2] == ['curl', '--disable']
        assert not any(v in args for v in ('-L', '--location', '--insecure'))
        assert kwargs['env'].keys() == {'PATH'} and kwargs['check']
        assert kwargs['timeout'] <= 31
        assert args[args.index('--max-filesize') + 1] == '4194304'
        Path(args[args.index('--output') + 1]).write_bytes(b'owned')
    out = tmp_path / 'inputs'
    receipt = tool.provision(out, run=run)
    assert receipt['schema'] == 'nico.cpp-source-tool-provisioning.v1'
    assert receipt['status'] == 'VERIFIED_TOOL_INPUTS'
    assert not receipt['installed'] and not receipt['target_executed']
    assert receipt['packages'][0]['bytes'] == 5
    assert receipt['packages'][0]['version'] == '1.5.0'
    assert (out / 'capnproto.tar.gz').read_bytes() == b'owned'
    assert (out / 'SHA256SUMS').read_text() == hashlib.sha256(b'owned').hexdigest() + '  capnproto.tar.gz\n'
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['digest', 'size', 'interrupt'])
def test_failed_source_download_never_gets_success_manifest(tmp_path, monkeypatch, failure):
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(source_lock()))
    monkeypatch.setattr(tool, 'LOCK', lock)
    out = tmp_path / 'inputs'
    def run(args, **kwargs):
        path = Path(args[args.index('--output') + 1])
        if failure == 'interrupt': raise KeyboardInterrupt()
        path.write_bytes(b'bad' if failure == 'digest' else b'x' * (4194304 + 1))
    with pytest.raises((ValueError, KeyboardInterrupt)):
        tool.provision(out, run=run)
    receipt = json.loads((out / 'receipt.json').read_bytes())
    assert receipt['status'] == 'UNPROVEN' and receipt['packages'] == []
    assert not (out / 'SHA256SUMS').exists()


def test_source_and_binary_dependency_inputs_share_existing_aggregate_ceiling(tmp_path, monkeypatch):
    from tests.test_cpp_dependency_retention import expanded_lock
    source = tmp_path / 'source.json'; source.write_text(json.dumps(source_lock()))
    binary = expanded_lock(); binary['packages'][0]['bytes'] = 15 * 1024 * 1024
    deps = tmp_path / 'deps.json'; deps.write_text(json.dumps(binary))
    monkeypatch.setattr(tool, 'LOCK', source); monkeypatch.setattr(tool, 'PROJECT_LOCK', deps)
    calls = []
    with pytest.raises(ValueError, match='dependency.*budget'):
        tool.provision(tmp_path / 'inputs', run=lambda *a, **k: calls.append(a))
    assert calls == []


def test_published_source_pin_image_and_bitcoin_scope_are_bound():
    lock_path = ROOT / 'docker/assessment-capnp-source.lock.json'
    assert lock_path.is_file(), 'missing the source dependency pinned by the frozen target'
    lock = json.loads(lock_path.read_bytes()); rows = tool.validate_lock(lock)
    assert len(rows) == 1 and rows[0]['sha256'] == SHA256
    assert rows[0]['version'] == '1.5.0'
    deps = tool.validate_lock(json.loads(tool.PROJECT_LOCK.read_bytes()))
    assert sum(r['bytes'] for r in deps) + rows[0]['max_bytes'] <= 16 * 1024 * 1024
    image = (ROOT / 'docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert 'AS capnp-builder' in image and 'COPY --from=capnp-builder' in image
    assert 'capnproto.tar.gz' in image and 'sha256sum -c SHA256SUMS' in image
    assert '-DWITH_OPENSSL=OFF' in image and '-DWITH_ZLIB=OFF' in image
    assert 'Cap\'n Proto version 1.5.0' in image
    assert 'apt-get' not in image and 'curl' not in image
    workflow = (ROOT / '.github/workflows/cpp-full-project-integration.yml').read_text()
    assert '--capnp-source' in workflow and 'tests/test_cpp_capnp_provisioning.py' in workflow
    assert 'toolchain/full-project/capnp-source/receipt.json' in workflow
    benchmark = json.loads((ROOT / 'tests/fixtures/cpp/bitcoin-configuration-benchmark.json').read_bytes())
    assert benchmark['project_options']['ENABLE_IPC'] == 'ON'
    assert benchmark['project_options']['BUILD_TESTS'] == 'ON'
    assert benchmark['project_options']['ENABLE_WALLET'] == 'ON'
    assert benchmark['commit_sha'] == 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24'


def test_full_project_image_provisions_frozen_bitcoin_pycapnp_offline():
    workflow = (ROOT / '.github/workflows/cpp-full-project-integration.yml').read_text()
    wheel = 'pycapnp-2.2.1-cp311-cp311-manylinux_2_28_x86_64.whl'
    url = ('https://files.pythonhosted.org/packages/f0/a6/'
           'eeb28ab162eed10340921aca24efe062d6bf7d9b98acc7a55c3b6900bf7a/' + wheel)
    digest = 'd682ae9f23a0c6568533ca2ebf6d70ac7e599dd222f671fa87dff278de343eec'
    assert workflow.count(url) == 2
    assert workflow.count(digest + '  toolchain/full-project/pycapnp.whl') == 2
    image = (ROOT / 'docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert 'COPY pycapnp.whl /opt/pycapnp.whl' in image
    assert digest + '  /opt/pycapnp.whl' in image
    assert "capnp.__version__ == '2.2.1'" in image
    assert 'ENV PYTHONPATH=/opt/pycapnp' in image
