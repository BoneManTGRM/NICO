"""Owned dependency-input fixtures; native qualification remains a separate gate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts import provision_cpp_fuzz_tools as tool


def project_lock():
    packages = [
        ('libboost1.74-dev', '1.74.0+ds1-21', 'b/boost1.74'),
        ('libsqlite3-0', '3.40.1-2+deb12u2', 's/sqlite3'),
        ('libsqlite3-dev', '3.40.1-2+deb12u2', 's/sqlite3'),
    ]
    return {'schema': 'nico.cpp-project-dependencies.v1', 'packages': [
        {'package': name, 'version': version, 'architecture': 'amd64',
         'url': f'https://deb.debian.org/debian/pool/main/{parent}/{name}_{version}_amd64.deb',
         'bytes': 4, 'sha256': hashlib.sha256(b'test').hexdigest()}
        for name, version, parent in packages]}


def test_verified_project_dependency_population_is_accepted():
    value = project_lock()
    assert tool.validate_lock(value) == value['packages']


@pytest.mark.parametrize('change', [
    {'url': 'http://deb.debian.org/debian/pool/main/b/boost1.74/x_amd64.deb'},
    {'url': 'https://example.invalid/x_amd64.deb'},
    {'url': 'https://deb.debian.org@evil.invalid/debian/pool/main/x_amd64.deb'},
    {'url': 'https://deb.debian.org/debian/pool/main/../x_amd64.deb'},
    {'url': 'https://deb.debian.org/debian/pool/main/%2e%2e/x_amd64.deb'},
    {'url': 'https://deb.debian.org/debian/pool/main/x_amd64.deb?token=x'},
    {'url': 'https://deb.debian.org/debian/pool/main/x_amd64.deb#x'},
    {'bytes': True}, {'bytes': 0}, {'bytes': 16 * 1024 * 1024 + 1},
    {'sha256': 'bad'}, {'architecture': 'arm64'}, {'package': '../../outside'},
])
def test_dependency_lock_rejects_substitution_or_unbounded_input(change):
    value = project_lock(); value['packages'][0].update(change)
    with pytest.raises(ValueError): tool.validate_lock(value)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'extra', 'version_pair'])
def test_dependency_lock_requires_the_entire_version_consistent_population(change):
    value = project_lock()
    if change == 'missing': value['packages'].pop()
    elif change == 'duplicate': value['packages'].append(deepcopy(value['packages'][0]))
    elif change == 'extra': value['packages'][0]['package'] = 'unreviewed-package'
    else: value['packages'][1]['version'] = '3.40.1-2+deb12u1'
    with pytest.raises(ValueError): tool.validate_lock(value)


def test_project_input_download_preserves_partial_evidence_and_uses_no_install_hooks(tmp_path, monkeypatch):
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(project_lock()))
    monkeypatch.setattr(tool, 'LOCK', lock)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert args[:2] == ['curl', '--disable']
        assert '-L' not in args and '--location' not in args
        assert kwargs['env'].keys() == {'PATH'} and kwargs['check']
        assert kwargs['timeout'] <= 31
        Path(args[args.index('--output') + 1]).write_bytes(b'test')
    output = tmp_path / 'inputs'
    result = tool.provision(output, run=run)
    assert result['schema'] == 'nico.cpp-project-dependency-provisioning.v1'
    assert result['status'] == 'VERIFIED_TOOL_INPUTS'
    assert result['installed'] is False and result['target_executed'] is False
    assert len(calls) == 3
    assert len((output / 'SHA256SUMS').read_text().splitlines()) == 3
    def failure(args, **kwargs):
        if 'libsqlite3-0_' in args[-1]:
            raise subprocess.TimeoutExpired('curl', 1)
        run(args, **kwargs)
    failed = tmp_path / 'failed'
    with pytest.raises(subprocess.TimeoutExpired): tool.provision(failed, run=failure)
    receipt = json.loads((failed / 'receipt.json').read_bytes())
    assert receipt['status'] == 'UNPROVEN' and len(receipt['packages']) == 1
    assert not (failed / 'SHA256SUMS').exists()


def test_actual_integration_recipe_and_workflow_require_dependencies():
    root = Path(__file__).resolve().parents[1]
    recipe = (root / 'docker/assessment-full-project-fuzz.Dockerfile').read_text()
    workflow = (root / '.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'COPY project-dependencies /opt/project-dependency-inputs' in recipe
    assert 'cd /opt/project-dependency-inputs && sha256sum -c SHA256SUMS' in recipe
    assert 'dpkg-deb --extract' in recipe and 'apt-get' not in recipe
    assert '--project-dependencies' in workflow
    assert 'toolchain/full-project/project-dependencies/receipt.json' in workflow
    assert 'tests/test_cpp_project_dependencies.py' in workflow
    assert 'tests/test_cpp_nested_cmake.py' in workflow


def test_dependency_control_selects_nested_build_and_real_library_use():
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    from nico.assessment_worker_receipts import validate_contract
    from nico.assessment_cpp_full_project import execution_steps
    files = fixture(generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    assert 'sum.cpp' not in files
    assert 'src/library/sum.cpp' in files and 'src/library/CMakeLists.txt' in files
    assert 'add_subdirectory(src/library)' in files['CMakeLists.txt']
    assert 'find_package(Boost 1.74.0 EXACT CONFIG REQUIRED)' in files['src/library/CMakeLists.txt']
    assert 'SQLite::SQLite3' in files['src/library/CMakeLists.txt']
    assert 'BOOST_VERSION == 107400' in files['src/library/sum.cpp']
    assert 'sqlite3_libversion_number()' in files['src/library/sum.cpp']
    result = plan('sha256:' + 'd' * 64, generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    assert validate_contract(result) == result
    assert result['configuration']['schema'] == 'nico.cpp-cmake-configuration.v6'
    assert result['configuration']['nested_base_schema'] == 'nico.cpp-cmake-configuration.v5'
    assert result['configuration']['translation_units'] == ['main.cpp', 'src/library/sum.cpp']
    assert result['configuration']['native_test_evidence'] == 'bound-binary-replay-v1'
    assert set(result['targets']) == set(files)
    assert result['targets'] == {path: hashlib.sha256(data.encode()).hexdigest() for path, data in files.items()}
    assert len([s for s in execution_steps(result) if 'compiler_configuration' in s]) == 3
    assert len([s for s in execution_steps(result) if 'native_test_configuration' in s]) == 2
    assert any(s['id'] == 'fuzz-native-evidence' for s in execution_steps(result))


def test_dependency_fixture_preserves_original_control_and_failure_scope():
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    from scripts.qualify_cpp_full_project_control import FIXTURE
    assert fixture() == FIXTURE
    unchanged = fixture(generated_headers=True, bounded_fuzz=True)
    assert 'sum.cpp' in unchanged and 'src/library/sum.cpp' not in unchanged
    image = 'sha256:' + 'd' * 64
    positive = plan(image, generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    negative = plan(image, generated_headers=True, bounded_fuzz=True, project_dependencies=True, negative=True)
    assert positive['targets'] == negative['targets']
    assert positive['configuration']['unit_tests'] == ['unit']
    assert negative['configuration']['unit_tests'] == ['negative']
    assert negative['configuration']['bounded_fuzz']['cmake_options']['NICO_FUZZ_FAILURE'] == 'ON'
    assert positive['limits'] == negative['limits'] == {'max_attempts': 1, 'wall_seconds': 180, 'lease_seconds': 30}
    with pytest.raises(ValueError): fixture(project_dependencies=True)


@pytest.mark.parametrize('value', [None, {}, [], 2, True])
def test_malformed_dependency_name_is_rejected_before_any_io(value):
    contract = project_lock(); contract['packages'][0]['package'] = value
    with pytest.raises(ValueError): tool.validate_lock(contract)


def test_owned_control_exact_boost_request_matches_pinned_upstream_version():
    """Native configure rejected 1.74 EXACT against the installed 1.74.0 package."""
    from scripts.qualify_cpp_full_project_integration import fixture
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / 'docker/assessment-project-dependencies.lock.json').read_text())
    package = next(row for row in lock['packages'] if row['package'] == 'libboost1.74-dev')
    upstream = package['version'].split('+', 1)[0]
    assert upstream.count('.') == 2
    cmake = fixture(generated_headers=True, project_dependencies=True)['src/library/CMakeLists.txt']
    assert 'find_package(Boost ' + upstream + ' EXACT CONFIG REQUIRED)' in cmake
    assert 'Boost::headers' in cmake and 'SQLite::SQLite3' in cmake
