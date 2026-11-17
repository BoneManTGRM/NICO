import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import nico.no_server_assessment as ns


COMMANDS = [['latest'], ['report', 'latest', '--format', 'json'], ['report', 'latest', '--format', 'markdown'], ['report', 'latest', '--format', 'html']]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path / 'reports')
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text("print('synthetic')\n")
    return root


def cli(args):
    env = dict(os.environ)
    env['NICO_REPORT_DIR'] = str(ns.REPORT_DIR)
    return subprocess.run([sys.executable, '-m', 'nico', 'assess', *args], env=env, text=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('args', COMMANDS)
def test_subprocess_rejects_interrupted_publication(project, monkeypatch, args):
    a = ns.run_local_assessment(str(project), True)
    old_html = (ns.REPORT_DIR / 'no_server_latest.html').read_bytes()
    original = Path.write_bytes
    def fail(path, *a, **kw):
        if path == ns.REPORT_DIR / 'no_server_latest.md':
            raise OSError('synthetic interrupted publication')
        return original(path, *a, **kw)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_bytes', fail)
        with pytest.raises(OSError):
            ns.run_local_assessment(str(project), True)
    b = json.loads((ns.REPORT_DIR / 'no_server_latest.json').read_bytes())
    assert a['assessment_id'] != b['assessment_id']
    assert (ns.REPORT_DIR / 'no_server_latest.html').read_bytes() == old_html
    result = cli(args)
    print(json.dumps({'args': args, 'assessment_a': a['assessment_id'], 'assessment_b': b['assessment_id'], 'returncode': result.returncode, 'stdout': result.stdout}))
    assert result.returncode == 1
    assert json.loads(result.stdout)['status'] == 'error'


@pytest.mark.parametrize('args', COMMANDS)
@pytest.mark.parametrize('damage', ['missing_proof', 'corrupt_proof', 'missing_json', 'missing_markdown', 'missing_html', 'stale_markdown', 'truncated_json', 'truncated_html'])
def test_damaged_bundle_is_not_retrievable(project, capsys, args, damage):
    ns.run_local_assessment(str(project), True)
    old = (ns.REPORT_DIR / 'no_server_latest.md').read_bytes()
    ns.run_local_assessment(str(project), True)
    paths = {'proof': 'manifest.json', 'json': 'json', 'markdown': 'md', 'html': 'html'}
    action, target = damage.split('_', 1)
    path = ns.REPORT_DIR / ('no_server_latest.' + paths[target])
    if action == 'missing':
        path.unlink()
    elif action == 'stale':
        path.write_bytes(old)
    else:
        path.write_bytes(b'{')
    with pytest.raises(SystemExit) as caught:
        ns.main(args)
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out) == {'status': 'error', 'error': 'Assessment failed.', 'error_type': 'ReportIntegrityError'}


@pytest.mark.parametrize('args', COMMANDS)
def test_subprocess_retrieval_is_blocked_by_writer(project, args):
    ns.run_local_assessment(str(project), True)
    with ns._report_publication_lock(exclusive=True):
        result = cli(args)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error_type'] == 'BlockingIOError'


@pytest.mark.parametrize('args', COMMANDS)
def test_subprocess_complete_and_empty_retrieval(project, args):
    empty = cli(args)
    assert empty.returncode == 0
    if args == ['latest']:
        assert json.loads(empty.stdout)['status'] == 'empty'
    else:
        assert empty.stdout == 'No no-server assessment report exists yet.\n'
    report = ns.run_local_assessment(str(project), True)
    complete = cli(args)
    assert complete.returncode == 0
    if args == ['latest']:
        assert json.loads(complete.stdout) == report
    else:
        suffix = {'json': 'json', 'markdown': 'md', 'html': 'html'}[args[-1]]
        assert complete.stdout == (ns.REPORT_DIR / ('no_server_latest.' + suffix)).read_bytes().decode('utf-8') + '\n'


def test_retrieval_checks_integrity_without_scan_verification_or_approval(project, monkeypatch):
    report = ns.run_local_assessment(str(project), True)
    def forbidden():
        raise AssertionError('retrieval must not invoke scan verification')
    monkeypatch.setattr(ns, 'verify_latest', forbidden)
    assert ns.latest_report() == report
    assert ns.latest_report()['status'] == 'completed'
    assert ns.report_text('json') == (ns.REPORT_DIR / 'no_server_latest.json').read_bytes().decode('utf-8')


def test_orphan_artifact_is_not_an_empty_state(project):
    ns.REPORT_DIR.mkdir()
    (ns.REPORT_DIR / 'no_server_latest.html').write_bytes(b'orphan')
    with pytest.raises(ns.ReportIntegrityError):
        ns.latest_report()
    with pytest.raises(ns.ReportIntegrityError):
        ns.report_text('json')


def test_integrity_retrieval_does_not_require_latest_scan_match(project):
    report = ns.run_local_assessment(str(project), True)
    newer = ns.run_scan(str(project))
    assert newer['scan']['id'] != report['scan_id']
    assert ns.latest_report() == report
    assert json.loads(ns.report_text('json')) == report
    assert ns.verify_latest_assessment()['status'] == 'verification_failed'


@pytest.mark.parametrize('fmt,suffix', [('json','json'), ('markdown','md'), ('html','html')])
def test_report_returns_validated_buffer_not_a_later_read(project, monkeypatch, fmt, suffix):
    ns.run_local_assessment(str(project), True)
    target = ns.REPORT_DIR / ('no_server_latest.' + suffix)
    expected = target.read_bytes()
    original = Path.read_bytes
    reads = []
    def mutate_after_read(path):
        data = original(path)
        if path == target:
            reads.append(True)
            path.write_bytes(b'changed after validated read')
        return data
    monkeypatch.setattr(Path, 'read_bytes', mutate_after_read)
    assert ns.report_text(fmt) == expected.decode('utf-8')
    assert reads == [True]
