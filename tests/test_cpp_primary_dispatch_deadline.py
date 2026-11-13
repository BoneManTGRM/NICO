"""Synthetic physical-worker preparation costs cannot grant dispatch credit."""
import base64
import json
import os
from pathlib import Path
import resource
from types import SimpleNamespace

import pytest

from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_completed_static_collection import fixture
from tests.test_cpp_project_static import execution


@pytest.mark.parametrize('phase', ['verification', 'database', 'trace'])
@pytest.mark.parametrize('elapsed', [540.0, 540.001])
def test_physical_preparation_expiry_retains_unstarted_contexts(tmp_path, monkeypatch, phase, elapsed):
    request, _, primary, _ = fixture(tmp_path, physical=True)
    receipt = base64.b64decode(json.loads(primary)['header_tool_receipt'])
    clock = [10.0]
    parent = tmp_path / 'analyst'
    parent.mkdir(mode=0o700)

    class AnalystPath(type(tmp_path)):
        def lstat(self, *args, **kwargs):
            info = super().lstat(*args, **kwargs)
            return SimpleNamespace(st_uid=1001, st_mode=info.st_mode) if self == parent else info

        def chmod(self, mode, **kwargs):
            super().chmod(mode, **kwargs)
            if phase == 'database' and self.suffix == '.json':
                clock[0] = 10.0 + elapsed

    def trace_open(path, *args):
        descriptor = os.open(path, *args)
        if phase == 'trace' and str(path).endswith('.trace.xml'):
            clock[0] = 10.0 + elapsed
        return descriptor

    monkeypatch.setattr(static, 'Path', lambda p: AnalystPath(parent if p == '/work/analysis' else p))
    monkeypatch.setattr(static, 'os', SimpleNamespace(getuid=lambda: 1001, getgid=lambda: 1001,
        open=trace_open, close=os.close, O_CREAT=os.O_CREAT, O_EXCL=os.O_EXCL,
        O_WRONLY=os.O_WRONLY, O_NOFOLLOW=os.O_NOFOLLOW))
    monkeypatch.setattr(resource, 'setrlimit', lambda *args: None)
    monkeypatch.setattr(static, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(static, 'verify_environment_inputs', lambda model: None)
    regular_bytes = static._regular_bytes
    monkeypatch.setattr(static, '_regular_bytes', lambda path, limit:
        receipt if path == '/opt/nico-cppcheck-header-observer.json' else regular_bytes(path, limit))

    def verify(*args):
        if phase == 'verification':
            clock[0] = 10.0 + elapsed
    monkeypatch.setattr(static, '_verify_input', verify)
    calls = []
    def run(argv, stem, deadline, environment):
        calls.append(argv)
        assert argv == ['/usr/local/bin/cppcheck', '--version'], 'expired analyzer dispatched'
        return execution(('Cppcheck ' + static.TOOL_VERSION + '\n').encode())
    monkeypatch.setattr(static, '_run', run)

    class SequentialPool:
        def __init__(self, max_workers):
            assert max_workers == 2  # Preserve physical-input policy.
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def map(self, fn, rows):
            return map(fn, rows)
    monkeypatch.setattr(static, 'ThreadPoolExecutor', SequentialPool)

    result = static.collect_project_static(request)
    assert calls == [['/usr/local/bin/cppcheck', '--version']]
    assert len(result['records']) == len(request['contexts'])
    assert all(row['execution'] is None and row['error'] == 'worker_project_static_deadline'
               and not row['xml'] and not row['header_trace'] for row in result['records'])
    proof = static.validate_project_static(_canonical(result), request)
    assert proof['attempted_contexts'] == [] and proof['analyzed_contexts'] == []
    assert proof['complete'] is False and proof['analyzer_header_coverage_verified'] is False
