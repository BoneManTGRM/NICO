"""Integrity controls for the native dependency repair, not parsing substitutes."""
from pathlib import Path
import pytest
from scripts import repair_cppcheck_header_grammar as repair


def owned_sources(tmp_path, monkeypatch):
    patches = {}; originals = {}
    for relative, (blob, anchor, replacement) in repair.PATCHES.items():
        raw = b'// owned boundary fixture\n'+anchor
        raw += b'\n'.join(old for old,_ in repair.EXTRA_REPLACEMENTS.get(relative,()))
        raw += b'\n// end\n'
        path = tmp_path/relative; path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        originals[relative] = raw
        patches[relative] = (repair.git_blob(raw),anchor,replacement)
    monkeypatch.setattr(repair,'PATCHES',patches)
    return originals


def test_changed_tool_source_rejected_before_any_mutation(tmp_path, monkeypatch):
    originals = owned_sources(tmp_path,monkeypatch)
    (tmp_path/'lib/tokenlist.cpp').write_bytes(b'untrusted')
    with pytest.raises(ValueError,match='upstream_source_mismatch'): repair.apply_repair(tmp_path)
    for name in ('lib/token.cpp','lib/tokenize.cpp'):
        assert (tmp_path/name).read_bytes() == originals[name]


def test_symlink_source_rejected_without_mutation(tmp_path, monkeypatch):
    originals=owned_sources(tmp_path,monkeypatch)
    target=tmp_path/'lib/tokenlist.cpp';target.unlink();target.symlink_to(tmp_path/'lib/token.cpp')
    with pytest.raises((OSError,ValueError)): repair.apply_repair(tmp_path)
    assert (tmp_path/'lib/tokenize.cpp').read_bytes() == originals['lib/tokenize.cpp']


def test_receipt_binds_each_changed_source_and_rejects_reapplication(tmp_path, monkeypatch):
    originals=owned_sources(tmp_path,monkeypatch);receipt=repair.apply_repair(tmp_path)
    assert receipt['native_qualification_completed'] is False
    assert receipt['upstream_commit'] == 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
    for member in receipt['members']:
        name=member['source_path']
        assert member['source_before_git_blob'] == repair.git_blob(originals[name])
        assert member['source_after_git_blob'] == repair.git_blob((tmp_path/name).read_bytes())
    changed={n:(tmp_path/n).read_bytes() for n in originals}
    with pytest.raises(ValueError,match='upstream_source_mismatch'): repair.apply_repair(tmp_path)
    assert changed == {n:(tmp_path/n).read_bytes() for n in originals}


@pytest.mark.parametrize('relative',list(repair.PATCHES))
def test_exact_upstream_and_placement_output_identity_required(relative):
    with pytest.raises(ValueError,match='upstream_source_mismatch'):
        repair.patched_bytes(relative,b'arbitrary tool source')


def test_grammar_changes_do_not_modify_observer_or_target_sources():
    assert set(repair.PATCHES) == {'lib/token.cpp','lib/tokenize.cpp','lib/tokenlist.cpp'}
    docker=Path('docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert docker.index('python3 /opt/repair_cppcheck_placement_ast.py') < docker.index('python3 /opt/repair_cppcheck_header_grammar.py') < docker.index('python3 /opt/patch_cppcheck_header_evidence.py')


def test_owned_container_can_write_evidence_with_host_runner_uid(monkeypatch):
    from scripts import qualify_cpp_header_grammar as control
    # This verifies dispatch arguments, not a container execution.
    monkeypatch.setattr(control.os,'getuid',lambda:1001)
    monkeypatch.setattr(control.os,'getgid',lambda:123)
    argv=control.image_argv('sha256:'+'a'*64,Path('/input'),Path('/output'),'/work/output/pass.xml',['--std=c++20'])
    assert '--user=1001:123' in argv
    assert '--network=none' in argv and '--read-only' in argv
    assert '--memory=12g' in argv and '--cpus=2' in argv
    assert '--mount=type=bind,src=/input,dst=/work/owned,readonly' in argv
    assert '--mount=type=bind,src=/output,dst=/work/output' in argv
