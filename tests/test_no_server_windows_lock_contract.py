"""Mocked Windows branch contracts; these are NOT Windows runtime qualification."""
import hashlib
import json
import os
import sys
from types import SimpleNamespace

import pytest

import nico.no_server_assessment as ns


@pytest.mark.parametrize('exclusive', [False, True])
@pytest.mark.parametrize('body_fails', [False, True])
def test_mock_windows_uses_same_nonblocking_byte_and_unlocks(tmp_path, monkeypatch, exclusive, body_fails):
    calls = []
    def locking(fd, mode, size):
        calls.append((fd, mode, size, os.lseek(fd, 0, os.SEEK_CUR)))
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path)
    monkeypatch.setattr(ns, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(locking=locking, LK_NBLCK=2, LK_UNLCK=0))
    def exercise():
        with ns._report_publication_lock(exclusive=exclusive):
            os.lseek(calls[0][0], 17, os.SEEK_SET)
            if body_fails:
                raise RuntimeError('synthetic body failure')
    if body_fails:
        with pytest.raises(RuntimeError):
            exercise()
    else:
        exercise()
    assert [(mode, size, offset) for _, mode, size, offset in calls] == [(2, 1, 0), (0, 1, 0)]
    with pytest.raises(OSError):
        os.fstat(calls[0][0])
    assert (tmp_path / '.no_server_publication.lock').exists()


def test_mock_windows_contention_does_not_yield_unlock_or_delete(tmp_path, monkeypatch):
    calls = []
    def locking(fd, mode, size):
        calls.append((fd, mode, size))
        raise PermissionError('synthetic lock conflict')
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path)
    monkeypatch.setattr(ns, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(locking=locking, LK_NBLCK=2, LK_UNLCK=0))
    with pytest.raises(PermissionError):
        with ns._report_publication_lock(exclusive=False):
            pytest.fail('must not yield without a lock')
    assert len(calls) == 1
    with pytest.raises(OSError):
        os.fstat(calls[0][0])
    assert (tmp_path / '.no_server_publication.lock').exists()


def test_unknown_platform_has_no_unlocked_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path)
    monkeypatch.setattr(ns, 'os', SimpleNamespace(name='unsupported'))
    with pytest.raises(OSError):
        with ns._report_publication_lock(exclusive=True):
            pytest.fail('must not yield without a lock')


def test_publication_uses_exact_utf8_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path / 'reports')
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'README.md').write_bytes('# Synthetic café\n'.encode('utf-8'))
    report = ns.run_local_assessment(str(project), True)
    expected = {
        'json': json.dumps(ns.sanitize_output(report), indent=2, sort_keys=True),
        'markdown': ns.markdown_report(ns.sanitize_output(report)),
    }
    expected['html'] = ns.html_report(expected['markdown'])
    proof = json.loads((ns.REPORT_DIR / 'no_server_latest.manifest.json').read_bytes())
    for fmt, suffix in [('json', 'json'), ('markdown', 'md'), ('html', 'html')]:
        data = (ns.REPORT_DIR / ('no_server_latest.' + suffix)).read_bytes()
        assert data == expected[fmt].encode('utf-8')
        assert hashlib.sha256(data).hexdigest() == proof['sha256'][fmt]
