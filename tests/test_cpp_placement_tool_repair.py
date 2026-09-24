"""The toolchain repair must be source-pinned and exercised by owned controls."""
import hashlib
import importlib
from pathlib import Path
import pytest


def repair():
    module = 'scripts.repair_cppcheck_placement_ast'
    assert Path('scripts/repair_cppcheck_placement_ast.py').is_file(), 'missing pinned analyzer repair'
    return importlib.import_module(module)


def test_fixture_reproduces_placement_new_through_both_existing_contexts(tmp_path):
    from scripts.qualify_cpp_project_generated_context import fixture
    root = tmp_path / 'owned'
    fixture(root, compiler_environment=True)
    source = (root / 'repeated.cpp').read_text()
    assert '#include <new>' in source
    assert '::new (&resource) OwnedResource{}' in source
    assert 'resource.~OwnedResource()' in source
    assert 'VARIANT == 1' in source
    assert 'owned_reconstruct(resource)' in source


def test_both_toolchain_builds_apply_the_same_pinned_source_repair():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    builds = [s['run'] for j in workflow['jobs'].values() for s in j['steps']
              if 'docker/assessment-full-project-fuzz.Dockerfile' in s.get('run', '')]
    assert len(builds) == 2
    assert all('cp scripts/repair_cppcheck_placement_ast.py toolchain/full-project/' in b for b in builds)
    docker = Path('docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert 'COPY repair_cppcheck_placement_ast.py /opt/repair_cppcheck_placement_ast.py' in docker
    assert docker.index('python3 /opt/repair_cppcheck_placement_ast.py') < docker.index('make -C /opt/tool-src')
    assert 'org.nico.cppcheck.repair="placement-new-initializer-ast-v1"' in docker
    assert 'COPYING' in docker


def pinned_fixture(module, monkeypatch):
    # Synthetic bytes exercise the file-integrity boundary, not native parsing.
    raw = b'// owned source-boundary fixture\n' + module.ANCHOR + b'// end\n'
    monkeypatch.setattr(module, 'UPSTREAM_BLOB', module.git_blob(raw))
    return raw


def test_repair_pins_the_exact_upstream_source_not_a_repository_name():
    m = repair()
    assert m.UPSTREAM_BLOB == 'b9c3ab07f0436ada75da5f45c7f8c3f3e06a8608'
    assert m.UPSTREAM_COMMIT == 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
    assert 'bitcoin' not in Path(m.__file__).read_text().lower()
    with pytest.raises(ValueError, match='upstream_source_mismatch'):
        m.patched_bytes(b'arbitrary source')


def test_owned_file_repair_records_exact_before_after_and_script_hashes(tmp_path, monkeypatch):
    m = repair(); raw = pinned_fixture(m, monkeypatch)
    source = tmp_path / 'tokenlist.cpp'; source.write_bytes(raw)
    receipt = m.apply_repair(source)
    patched = source.read_bytes()
    assert patched == raw.replace(m.ANCHOR, m.REPLACEMENT)
    assert receipt['source_before_sha256'] == hashlib.sha256(raw).hexdigest()
    assert receipt['source_after_sha256'] == hashlib.sha256(patched).hexdigest()
    assert receipt['source_after_git_blob'] == m.git_blob(patched)
    assert receipt['repair_script_sha256'] == hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
    assert receipt['repair_id'] == 'placement-new-initializer-ast-v1'
    with pytest.raises(ValueError, match='upstream_source_mismatch'):
        m.apply_repair(source)
    assert source.read_bytes() == patched


@pytest.mark.parametrize('count', [0, 2])
def test_changed_or_ambiguous_native_anchor_is_never_patched(monkeypatch, count):
    m = repair(); raw = b'// owned\n' + m.ANCHOR * count
    monkeypatch.setattr(m, 'UPSTREAM_BLOB', m.git_blob(raw))
    with pytest.raises(ValueError, match='upstream_anchor_mismatch'):
        m.patched_bytes(raw)


def test_symlink_tool_source_cannot_be_followed(tmp_path, monkeypatch):
    m = repair(); raw = pinned_fixture(m, monkeypatch)
    source = tmp_path / 'original'; source.write_bytes(raw)
    link = tmp_path / 'tokenlist.cpp'; link.symlink_to(source)
    with pytest.raises((ValueError, OSError)):
        m.apply_repair(link)
    assert source.read_bytes() == raw


def test_repair_only_changes_placement_initializer_dispatch(monkeypatch):
    m = repair(); raw = pinned_fixture(m, monkeypatch)
    patched = m.patched_bytes(raw)
    assert b'Token::simpleMatch(tok, ")")' in patched
    assert b'tok->link()' in patched
    assert b'Token::simpleMatch(tok->link()->previous(), "new (")' in patched
    assert patched.count(m.ANCHOR) == 1
    assert b'return false;' in patched
    assert b'catch' not in m.REPLACEMENT
    assert b'astOperand' not in m.REPLACEMENT
