"""A verified input must not cause dispatch after the shared deadline."""
from types import SimpleNamespace

import pytest

from nico import assessment_cpp_clang_fallback as fallback
from tests.test_cpp_clang_fallback import primary_with_one_failure, execution


@pytest.mark.parametrize('elapsed', [1.0, 1.001])
def test_input_verification_expiry_retains_unstarted_context(tmp_path, monkeypatch, elapsed):
    request, primary = primary_with_one_failure(tmp_path)
    request = fallback.clang_fallback_request(request, primary)
    clock = [10.0]
    calls = []
    directory = tmp_path / 'private-worker'
    directory.mkdir(mode=0o700)

    class PrivateParent:
        def lstat(self):
            return SimpleNamespace(st_uid=1001, st_mode=0o40700)

        def resolve(self, *, strict):
            assert strict
            return self

        def __truediv__(self, name):
            return directory / name

    parent = PrivateParent()
    real_path = fallback.Path
    monkeypatch.setattr(fallback, 'Path', lambda value: parent if value == '/work/analysis' else real_path(value))
    monkeypatch.setattr(fallback.os, 'getuid', lambda: 1001)
    monkeypatch.setattr(fallback.os, 'getgid', lambda: 1001)
    import resource
    monkeypatch.setattr(resource, 'setrlimit', lambda *args: None)
    monkeypatch.setattr(fallback.time, 'monotonic', lambda: clock[0])

    def verify(*args):
        clock[0] = 10.0 + elapsed

    def run(argv, stem, deadline, environment):
        calls.append(argv)
        assert argv == [fallback.CLANG, '-dumpversion'], 'expired analyzer dispatched'
        return execution(output=(fallback.VERSION + '\n').encode())

    monkeypatch.setattr(fallback, '_verify_input', verify)
    monkeypatch.setattr(fallback, '_run', run)
    result = fallback.collect_clang_fallback(request, wall_budget_ms=1000)
    assert calls == [[fallback.CLANG, '-dumpversion']]
    assert len(result['records']) == 1
    row = result['records'][0]
    assert row['context_id'] == request['contexts'][0]['context_id']
    assert row['execution'] is None
    assert row['error'] == 'worker_clang_fallback_deadline'
    assert row['plist'] == '' and row['plist_sha256'] is None
