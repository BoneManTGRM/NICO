"""Mechanical repair/receipt controls; these are NOT native parser qualification."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import runpy
import sys

import pytest


def modules():
    return (importlib.import_module('scripts.repair_cppcheck_format_var_template_ast'),
            importlib.import_module('scripts.repair_cppcheck_placement_ast'))


def input_fixture(tmp_path, monkeypatch):
    m, placement = modules()
    # Synthetic input checks the packaging boundary, not C++ grammar.
    original = b'// synthetic packaging control\n' + placement.ANCHOR + m.OLD + b'// end\n'
    monkeypatch.setattr(placement, 'UPSTREAM_BLOB', placement.git_blob(original))
    raw = placement.patched_bytes(original)
    source = tmp_path / 'lib' / 'tokenlist.cpp'
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    return m, placement, source, raw


def test_repair_scripts_are_valid_python():
    for path in ('scripts/repair_cppcheck_format_var_template_ast.py',
                 'scripts/repair_cppcheck_placement_ast.py'):
        compile(Path(path).read_bytes(), path, 'exec')


def test_existing_native_patch_bytes_are_preserved():
    m, _ = modules()
    expected = (
        b'            // A linked ">" is a template closing bracket, not a binary operator.\n'
        b'            if (tok->str() == ">" && tok->link())\n'
        b'                continue;\n'
    )
    assert m.NEW == expected + m.OLD
    assert b'"Syntax Error: AST broken, binary operator \'" + tok->str()' in m.OLD
    assert b"doesn't have two operands." in m.OLD


def test_repair_returns_hash_bound_unqualified_receipt(tmp_path, monkeypatch):
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    receipt = m.apply(tmp_path)
    after = source.read_bytes()
    assert after == raw.replace(m.OLD, m.NEW, 1)
    assert receipt['schema'] == 'nico.cppcheck-tool-repair.v1'
    assert receipt['repair_id'] == 'format-var-template-ast-v1'
    assert receipt['prerequisite_repair_id'] == placement.REPAIR_ID
    assert receipt['upstream_commit'] == placement.UPSTREAM_COMMIT
    assert receipt['source_before_git_blob'] == placement.git_blob(raw)
    assert receipt['source_after_git_blob'] == placement.git_blob(after)
    assert receipt['source_before_sha256'] == hashlib.sha256(raw).hexdigest()
    assert receipt['source_after_sha256'] == hashlib.sha256(after).hexdigest()
    assert receipt['repair_script_sha256'] == hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
    assert receipt['prerequisite_repair_script_sha256'] == hashlib.sha256(Path(placement.__file__).read_bytes()).hexdigest()
    assert receipt['native_qualification_completed'] is False


def test_cli_stdout_is_valid_json_not_a_plaintext_success_message(tmp_path, monkeypatch, capsys):
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'repair_cppcheck_placement_ast', placement)
    monkeypatch.setattr(sys, 'argv', [m.__file__, str(tmp_path)])
    runpy.run_path(m.__file__, run_name='__main__')
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert captured.err == ''
    assert receipt['native_qualification_completed'] is False
    assert receipt['source_before_sha256'] == hashlib.sha256(raw).hexdigest()
    assert receipt['source_after_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_reapplication_is_rejected_without_writing(tmp_path, monkeypatch):
    m, _, source, _ = input_fixture(tmp_path, monkeypatch)
    m.apply(tmp_path)
    already = source.read_bytes()
    with pytest.raises((ValueError, SystemExit), match='already_applied'):
        m.apply(tmp_path)
    assert source.read_bytes() == already


def test_changed_input_is_not_accepted_just_because_anchor_matches(tmp_path, monkeypatch):
    m, _, source, raw = input_fixture(tmp_path, monkeypatch)
    altered = raw + b'// unrelated drift\n'
    source.write_bytes(altered)
    with pytest.raises(ValueError, match='upstream_source_mismatch'):
        m.apply(tmp_path)
    assert source.read_bytes() == altered


def test_missing_prerequisite_repair_is_rejected_without_writing(tmp_path, monkeypatch):
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    unpatched = raw.replace(placement.REPLACEMENT, placement.ANCHOR, 1)
    source.write_bytes(unpatched)
    with pytest.raises(ValueError, match='prerequisite_repair_mismatch'):
        m.apply(tmp_path)
    assert source.read_bytes() == unpatched


@pytest.mark.parametrize('count', [0, 2])
def test_missing_or_ambiguous_operand_anchor_is_rejected(tmp_path, monkeypatch, count):
    m, placement, source, _ = input_fixture(tmp_path, monkeypatch)
    original = b'// synthetic\n' + placement.ANCHOR + m.OLD * count
    monkeypatch.setattr(placement, 'UPSTREAM_BLOB', placement.git_blob(original))
    raw = placement.patched_bytes(original)
    source.write_bytes(raw)
    with pytest.raises((ValueError, SystemExit), match='operand'):
        m.apply(tmp_path)
    assert source.read_bytes() == raw


def test_symlink_source_is_rejected_without_mutating_target(tmp_path, monkeypatch):
    m, _, source, raw = input_fixture(tmp_path, monkeypatch)
    target = source.with_name('original.cpp')
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        m.apply(tmp_path)
    assert target.read_bytes() == raw


def test_workflow_restores_required_controls_and_retains_both_receipts():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    jobs = workflow['jobs']
    assert jobs['owned-project-integration']['needs'] == ['contract-regressions']
    assert jobs['project-baseline-qualification']['needs'] == ['owned-project-integration']
    for job_name in ('owned-project-integration', 'project-baseline-qualification'):
        job = jobs[job_name]
        provision = next(s['run'] for s in job['steps'] if 'docker build ' in s.get('run', ''))
        assert provision.index('scripts.verify_cppcheck_repair_chain') < provision.index('docker build ')
        artifact = next(s for s in job['steps'] if s.get('if') == 'always()' and 'with' in s)
        for name in ('cppcheck-placement-repair.json', 'cppcheck-format-var-template-repair.json',
                     'cppcheck-repair-chain-preflight.json'):
            assert name in artifact['with']['path'].splitlines()
    docker = Path('docker/assessment-full-project-fuzz.Dockerfile').read_text()
    apply_index = docker.index('python3 /opt/repair_cppcheck_format_var_template_ast.py')
    json_index = docker.index('python3 -m json.tool /opt/nico-cppcheck-format-var-template-repair.json')
    assert apply_index < json_index < docker.index('make -C /opt/tool-src')


def test_preflight_exercises_both_repairs_without_changing_source(tmp_path, monkeypatch):
    from scripts.verify_cppcheck_repair_chain import verify
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    original = raw.replace(placement.REPLACEMENT, placement.ANCHOR, 1)
    source.write_bytes(original)
    receipt = verify(source)
    assert source.read_bytes() == original
    assert receipt['source_unchanged'] is True
    assert receipt['native_qualification_completed'] is False
    assert receipt['repairs'][0]['repair_id'] == placement.REPAIR_ID
    assert receipt['repairs'][1]['repair_id'] == m.REPAIR_ID
    assert receipt['repairs'][0]['source_after_sha256'] == receipt['repairs'][1]['source_before_sha256']
    expected = raw.replace(m.OLD, m.NEW, 1)
    assert receipt['repairs'][1]['source_after_sha256'] == hashlib.sha256(expected).hexdigest()


def test_preflight_rejects_unpinned_source(tmp_path):
    from scripts.verify_cppcheck_repair_chain import verify
    source = tmp_path / 'tokenlist.cpp'
    source.write_bytes(b'not pinned source\n')
    with pytest.raises(ValueError, match='upstream_source_mismatch'):
        verify(source)
    assert source.read_bytes() == b'not pinned source\n'


def test_preflight_detects_source_change_during_private_copy_check(tmp_path, monkeypatch):
    from scripts import verify_cppcheck_repair_chain as preflight
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    original = raw.replace(placement.REPLACEMENT, placement.ANCHOR, 1)
    source.write_bytes(original)
    actual_apply = m.apply
    def changed(root):
        receipt = actual_apply(root)
        source.write_bytes(original + b'// changed concurrently\n')
        return receipt
    monkeypatch.setattr(m, 'apply', changed)
    with pytest.raises(ValueError, match='preflight_source_changed'):
        preflight.verify(source)


def test_preflight_detects_a_broken_receipt_chain(tmp_path, monkeypatch):
    from scripts import verify_cppcheck_repair_chain as preflight
    m, placement, source, raw = input_fixture(tmp_path, monkeypatch)
    original = raw.replace(placement.REPLACEMENT, placement.ANCHOR, 1)
    source.write_bytes(original)
    actual_apply = m.apply
    def wrong_receipt(root):
        receipt = actual_apply(root)
        receipt['source_before_sha256'] = '0' * 64
        return receipt
    monkeypatch.setattr(m, 'apply', wrong_receipt)
    with pytest.raises(ValueError, match='repair_chain_mismatch'):
        preflight.verify(source)
    assert source.read_bytes() == original
