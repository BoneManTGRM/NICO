import json
from pathlib import Path

import pytest

import nico.no_server_assessment as ns


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path / 'reports')
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text("print('synthetic A')\n")
    return root


@pytest.mark.parametrize('failure', ['stale_markdown', 'stale_html', 'missing_markdown', 'truncated_markdown'])
def test_interrupted_publication_cannot_verify(project, monkeypatch, failure):
    a = ns.run_local_assessment(str(project), True)
    old_html = (ns.REPORT_DIR / 'no_server_latest.html').read_bytes()
    original = Path.write_bytes
    failed_name = 'no_server_latest.html' if failure == 'stale_html' else 'no_server_latest.md'
    def interrupt(path, data, *args, **kwargs):
        if path == ns.REPORT_DIR / failed_name:
            if failure == 'missing_markdown':
                path.unlink()
            elif failure == 'truncated_markdown':
                original(path, b'truncated')
            raise OSError('synthetic publication interruption')
        return original(path, data, *args, **kwargs)
    (project / 'app.py').write_text("print('synthetic B')\n")
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_bytes', interrupt)
        with pytest.raises(OSError):
            ns.run_local_assessment(str(project), True)
    b = json.loads((ns.REPORT_DIR / "no_server_latest.json").read_bytes())
    verification = ns.verify_latest_assessment()
    assert b['assessment_id'] != a['assessment_id']
    assert verification['nico_verification']['scan_id'] == b['scan_id']
    assert verification['nico_verification']['passed'] is True
    assert (ns.REPORT_DIR / 'no_server_latest.html').read_bytes() == old_html
    print(json.dumps({'failure': failure, 'assessment_a': a['assessment_id'], 'assessment_b': b['assessment_id'], 'scan_b': b['scan_id'], 'verification': verification}, sort_keys=True))
    assert verification['status'] == 'verification_failed'


@pytest.mark.parametrize('suffix', ['json', 'md', 'html'])
@pytest.mark.parametrize('damage', ['stale', 'missing', 'truncated'])
def test_actual_persisted_artifact_bytes_are_checked(project, monkeypatch, capsys, suffix, damage):
    ns.run_local_assessment(str(project), True)
    path = ns.REPORT_DIR / f'no_server_latest.{suffix}'
    old = path.read_bytes()
    ns.run_local_assessment(str(project), True)
    if damage == 'stale':
        path.write_bytes(old)
    elif damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(path.read_bytes()[:9])
    with pytest.raises(SystemExit) as caught:
        ns.main(['verify', 'latest'])
    assert caught.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output['status'] != 'verified'


@pytest.mark.parametrize('stage', ['json', 'store', 'manifest'])
def test_publication_commit_failures_leave_no_valid_proof(project, monkeypatch, stage):
    ns.run_local_assessment(str(project), True)
    with monkeypatch.context() as patch:
        if stage == 'json':
            original = Path.write_bytes
            def fail(path, *args, **kwargs):
                if path == ns.REPORT_DIR / 'no_server_latest.json':
                    raise OSError('synthetic JSON write failure')
                return original(path, *args, **kwargs)
            patch.setattr(Path, 'write_bytes', fail)
        elif stage == 'store':
            patch.setattr(ns.Store, 'save_report', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic registry failure')))
        else:
            patch.setattr(ns.os, 'replace', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic manifest commit failure')))
        with pytest.raises(OSError):
            ns.write_latest_reports(ns.latest_report())
    assert not (ns.REPORT_DIR / 'no_server_latest.manifest.json').exists()
    assert ns.verify_latest_assessment()['status'] == 'verification_failed'
    assert not list(ns.REPORT_DIR.glob('.no_server_manifest_*'))


@pytest.mark.parametrize('damage', ['missing', 'truncated', 'identity', 'hash', 'shape'])
def test_invalid_or_legacy_proof_fails_closed(project, damage):
    ns.run_local_assessment(str(project), True)
    path = ns.REPORT_DIR / 'no_server_latest.manifest.json'
    proof = json.loads(path.read_bytes())
    if damage == 'missing':
        path.unlink()
    elif damage == 'truncated':
        path.write_bytes(b'{')
    else:
        if damage == 'identity':
            proof['assessment_id'] = 'different_assessment'
        elif damage == 'hash':
            proof['sha256']['html'] = '0' * 64
        else:
            proof['sha256'] = []
        path.write_text(json.dumps(proof))
    assert ns.verify_latest_assessment()['status'] == 'verification_failed'


def test_competing_writer_and_verifier_cannot_interleave(project, monkeypatch, capsys):
    a = ns.run_local_assessment(str(project), True)
    original = Path.write_bytes
    observed = []
    def interleave(path, data, *args, **kwargs):
        result = original(path, data, *args, **kwargs)
        if path == ns.REPORT_DIR / 'no_server_latest.json':
            assert not (ns.REPORT_DIR / 'no_server_latest.manifest.json').exists()
            with pytest.raises(BlockingIOError):
                ns.write_latest_reports(a)
            with pytest.raises(SystemExit) as caught:
                ns.main(['verify', 'latest'])
            assert caught.value.code == 1
            blocked = json.loads(capsys.readouterr().out)
            assert blocked == {'status': 'error', 'error': 'Assessment failed.', 'error_type': 'BlockingIOError'}
            observed.append(True)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_bytes', interleave)
        b = ns.run_local_assessment(str(project), True)
    assert observed == [True]
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verified'
    assert result['assessment_id'] == b['assessment_id']
    assert 'assessment_artifacts_verified' in result['checks']


def test_writer_process_death_releases_lock_but_cannot_commit(project):
    import multiprocessing
    import os

    ns.run_local_assessment(str(project), True)
    def interrupted_writer():
        with ns._report_publication_lock(exclusive=True):
            (ns.REPORT_DIR / 'no_server_latest.manifest.json').unlink()
            (ns.REPORT_DIR / 'no_server_latest.md').write_text('partial')
            os._exit(7)
    child = multiprocessing.get_context('fork').Process(target=interrupted_writer)
    child.start()
    child.join(5)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail('writer did not finish')
    assert child.exitcode == 7
    assert ns.verify_latest_assessment()['status'] == 'verification_failed'
    ns.run_local_assessment(str(project), True)
    assert ns.verify_latest_assessment()['status'] == 'verified'


@pytest.mark.parametrize('kind', ['local', 'zip', 'tar'])
def test_complete_publication_and_verification(project, kind):
    import io
    import tarfile
    import zipfile

    if kind == 'local':
        report = ns.run_local_assessment(str(project), True)
    else:
        archive = project.parent / ('fixture.' + kind)
        if kind == 'zip':
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('project/app.py', "print('synthetic')\n")
        else:
            with tarfile.open(archive, 'w') as output:
                data = b"print('synthetic')\n"
                item = tarfile.TarInfo('project/app.py')
                item.size = len(data)
                output.addfile(item, io.BytesIO(data))
        report = ns.run_archive_assessment(str(archive), True)
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verified'
    assert result['scan_id'] == report['scan_id']
    assert 'assessment_artifacts_verified' in result['checks']


def test_verifier_holds_lock_across_artifact_check(project, monkeypatch):
    report = ns.run_local_assessment(str(project), True)
    original = ns._publication_check
    observed = []
    def check(loaded):
        with pytest.raises(BlockingIOError):
            ns.write_latest_reports(report)
        observed.append(True)
        return original(loaded)
    monkeypatch.setattr(ns, '_publication_check', check)
    assert ns.verify_latest_assessment()['status'] == 'verified'
    assert observed == [True]


def test_cross_process_publication_blocks_competing_operations(project):
    import multiprocessing

    a = ns.run_local_assessment(str(project), True)
    b = {**a, 'assessment_id': 'synthetic_concurrent_assessment_b'}
    context = multiprocessing.get_context('fork')
    parent, child_pipe = context.Pipe()
    def publish():
        original = Path.write_bytes
        def pause_after_json(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == ns.REPORT_DIR / 'no_server_latest.json':
                child_pipe.send('json_written')
                if not child_pipe.poll(5):
                    raise RuntimeError('test coordination timeout')
                assert child_pipe.recv() == 'continue'
            return result
        Path.write_bytes = pause_after_json
        ns.write_latest_reports(b)
    child = context.Process(target=publish)
    child.start()
    try:
        assert parent.poll(5), 'writer did not reach JSON checkpoint'
        assert parent.recv() == 'json_written'
        with pytest.raises(BlockingIOError):
            ns.write_latest_reports(a)
        with pytest.raises(BlockingIOError):
            ns.verify_latest_assessment()
        parent.send('continue')
        child.join(5)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
        parent.close()
        child_pipe.close()
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verified'
    assert result['assessment_id'] == b['assessment_id']


def test_linux_cross_process_simultaneous_first_lock_creation(tmp_path, monkeypatch):
    import multiprocessing
    import os
    import sys

    if not sys.platform.startswith('linux'):
        pytest.skip('real Linux first-creation qualification')
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path / 'new_reports')
    lock_path = ns.REPORT_DIR / '.no_server_publication.lock'
    context = multiprocessing.get_context('fork')
    start = context.Event()
    release = context.Event()
    pipes = [context.Pipe() for _ in range(2)]
    def contender(pipe):
        pipe.send('ready')
        if not start.wait(5):
            raise RuntimeError('start timeout')
        try:
            with ns._report_publication_lock(exclusive=True):
                stat = lock_path.stat()
                pipe.send(('acquired', stat.st_dev, stat.st_ino, stat.st_size))
                if not release.wait(5):
                    raise RuntimeError('release timeout')
        except BlockingIOError:
            stat = lock_path.stat()
            pipe.send(('blocked', stat.st_dev, stat.st_ino, stat.st_size))
    children = [context.Process(target=contender, args=(pair[1],)) for pair in pipes]
    for child in children:
        child.start()
    try:
        for parent, _ in pipes:
            assert parent.poll(5) and parent.recv() == 'ready'
        assert not lock_path.exists()
        start.set()
        results = []
        for parent, _ in pipes:
            assert parent.poll(5), 'lock attempt did not finish'
            results.append(parent.recv())
        assert sorted(item[0] for item in results) == ['acquired', 'blocked']
        assert results[0][1:] == results[1][1:]
        assert results[0][-1] == 0
        release.set()
        for child in children:
            child.join(5)
            assert child.exitcode == 0
    finally:
        start.set()
        release.set()
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
        for pair in pipes:
            for pipe in pair:
                pipe.close()
    with ns._report_publication_lock(exclusive=True):
        assert lock_path.stat().st_ino == results[0][2]
