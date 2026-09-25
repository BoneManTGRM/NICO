"""Capture failures retain bounded metadata without relaxing the byte boundary."""
import io
import json
import os
from pathlib import Path
import sys

import pytest

from nico import assessment_cpp_project_snapshot as snapshot
from tests.test_cpp_project_snapshot import layout, contexts


@pytest.mark.parametrize('fault',['oversized','hardlink','aggregate'])
def test_rejected_input_identifies_the_exact_bound_without_retaining_content(tmp_path,monkeypatch,fault):
    build,destination=layout(tmp_path)
    leaf=build/'generated/message.capnp.c++'
    if fault=='oversized':
        with leaf.open('wb') as f: f.truncate(snapshot.PROJECT_GENERATED_MAX_FILE_BYTES+1)
    elif fault=='hardlink': os.link(leaf,build/'duplicate.c++')
    else: monkeypatch.setattr(snapshot,'PROJECT_GENERATED_MAX_BYTES',1)
    with pytest.raises(ValueError) as caught:
        snapshot.capture_project_snapshot(build,destination,snapshot.project_snapshot_request(contexts()))
    detail=getattr(caught.value,'failed_input',None)
    assert detail is not None, 'capture error loses the offending member and bound'
    assert set(detail)=={'path','phase','effective_max_bytes','captured_bytes_before','observed'}
    assert detail['path'].startswith('generated/') and detail['phase']=='initial_read'
    assert detail['observed']['type']=='regular'
    if fault=='oversized':
        assert detail['observed']['bytes']==snapshot.PROJECT_GENERATED_MAX_FILE_BYTES+1
        assert detail['effective_max_bytes']==min(snapshot.PROJECT_GENERATED_MAX_FILE_BYTES,
            snapshot.PROJECT_GENERATED_MAX_BYTES-detail['captured_bytes_before'])
        assert detail['observed']['bytes'] > detail['effective_max_bytes']
    if fault=='hardlink': assert detail['observed']['links']==2
    if fault=='aggregate': assert detail['effective_max_bytes']==1
    assert not destination.exists() and not list(destination.parent.glob('.project-generated-*'))
    assert 'base64' not in json.dumps(detail)


def test_failed_project_entrypoint_retains_metadata_and_sanitizes_other_errors(monkeypatch,capsys):
    assert hasattr(snapshot,'run_project_snapshot'), 'missing metadata-retaining project entrypoint'
    error_type=getattr(snapshot,'ProjectSnapshotFailure')
    detail={'path':'generated/large.cpp','phase':'initial_read','effective_max_bytes':8,
            'captured_bytes_before':0,'observed':{'type':'regular','bytes':9,'links':1}}
    def reject(_): raise error_type('worker_generated_type_or_size_invalid',detail)
    monkeypatch.setattr(snapshot,'collect_project_snapshot',reject)
    monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(b'{"configuration":"baseline"}')))
    with pytest.raises(SystemExit) as raised: snapshot.run_project_snapshot()
    assert raised.value.code==1
    result=json.loads(capsys.readouterr().out)
    assert result['error']=='worker_generated_type_or_size_invalid' and result['failed_input']==detail
    assert result['phase']=='project_snapshot'
    def unknown(_): raise OSError('sensitive filesystem detail must not escape')
    monkeypatch.setattr(snapshot,'collect_project_snapshot',unknown)
    monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(b'{"configuration":"baseline"}')))
    with pytest.raises(SystemExit): snapshot.run_project_snapshot()
    text=capsys.readouterr().out
    assert 'sensitive' not in text and json.loads(text)['error']=='worker_generated_capture_unavailable'


def test_diagnostics_are_registered_in_the_existing_workflow():
    text=(Path(__file__).resolve().parents[1]/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_project_snapshot_diagnostics.py' in text
