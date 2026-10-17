"""Deterministic caller-budget tests; no network requests or wall-clock sleeps."""
import json
from queue import Empty, Queue
from threading import BoundedSemaphore

import pytest

from nico import readiness_frontend_observation_v1 as readiness

SHA = 'a' * 40
DEPLOYMENT = 'dpl_timing_fixture'


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0
        def advance(self, seconds):
            self.now += seconds
    clock = Clock()
    monkeypatch.setattr(readiness.time, 'monotonic', lambda: clock.now)
    monkeypatch.setattr(readiness, '_CAPTURE_SLOT', BoundedSemaphore(1))
    return clock


@pytest.mark.parametrize('stage,delay,verified,calls', [
    ('headers', 7.9, True, 1), ('headers', 8, False, 1),
    ('headers', 21, False, 1), ('body', 8, False, 1),
    ('body', 8.1, False, 1), ('fallback_headers', 5, True, 2),
    ('fallback_headers', 6, False, 2), ('fallback_headers', 21, False, 2),
    ('fallback_body', 5, True, 2), ('fallback_body', 6, False, 2),
    ('fallback_body', 21, False, 2), ('fallback_denied', 1, False, 2),
])
def test_one_deadline_covers_headers_body_and_fallback(monkeypatch, clock, stage, delay, verified, calls):
    import requests
    seen = []
    class InlineThread:
        def __init__(self, target, **kwargs):
            assert kwargs['daemon'] is True
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(readiness, 'Thread', InlineThread)
    class Response:
        status_code = 200
        def __init__(self, data, body_delay=0):
            self.data, self.body_delay = data, body_delay
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, chunk_size):
            clock.advance(self.body_delay)
            yield json.dumps(self.data).encode()
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert self.trust_env is False
            assert kwargs == dict(timeout=(3, 5), allow_redirects=False, stream=True, headers={'Accept': 'application/json'})
            seen.append(url)
            if len(seen) == 1:
                assert url == readiness.provenance.FRONTEND_URL
                clock.advance(delay if stage == 'headers' else 2 if stage.startswith('fallback') else 0)
                return Response(dict(status='ok', release_sha=SHA if not stage.startswith('fallback') else 'unknown',
                    release_sha_source='VERCEL_GIT_COMMIT_SHA' if not stage.startswith('fallback') else 'unavailable',
                    deployment_id=DEPLOYMENT, deployment_id_source='VERCEL_DEPLOYMENT_ID'), delay if stage == 'body' else 0)
            assert url == f'https://api.vercel.com/v13/deployments/{DEPLOYMENT}?withGitRepoInfo=true'
            clock.advance(delay if stage == 'fallback_headers' else 0)
            response = Response(dict(id=DEPLOYMENT, readyState='READY', gitSource={'sha': SHA}), delay if stage == 'fallback_body' else 0)
            if stage == 'fallback_denied': response.status_code = 403
            return response
    monkeypatch.setattr(requests, 'Session', Session)
    result = readiness.capture_readiness_frontend_release(SHA, DEPLOYMENT)
    assert readiness.provenance.verify_frontend_release(result, SHA, DEPLOYMENT) is verified
    assert len(seen) == calls
    if clock.now >= 8:
        assert result['reason'] == 'frontend_readiness_capture_timed_out'
        assert result['deployment_identity_verified'] is False
    if stage in {'headers', 'fallback_headers'}:
        # Existing report callers retain their socket/body contract. The added
        # total wait is readiness-only, not a global capture-policy change.
        seen.clear()
        clock.now = 0
        ordinary = readiness.provenance.capture_frontend_release(SHA, DEPLOYMENT)
        assert readiness.provenance.verify_frontend_release(ordinary, SHA, DEPLOYMENT)


def test_timeout_busy_late_completion_and_slot_reuse(monkeypatch, clock):
    pending = []
    waits = []
    class DeferredThread:
        def __init__(self, target, **kwargs): self.target = target
        def start(self):
            clock.advance(1)  # Thread startup consumes the same budget.
            pending.append(self.target)
    class DeadlineQueue(Queue):
        def get(self, timeout):
            waits.append(timeout)
            clock.advance(timeout)
            raise Empty
    monkeypatch.setattr(readiness, 'Thread', DeferredThread)
    monkeypatch.setattr(readiness, 'Queue', DeadlineQueue)
    monkeypatch.setattr(readiness.provenance, 'capture_frontend_release', lambda *args: {'status': 'unavailable', 'marker': 'late'})
    result = readiness.capture_readiness_frontend_release(SHA, DEPLOYMENT)
    assert clock.now == 8 and waits == [7]
    assert result['reason'] == 'frontend_readiness_capture_timed_out'
    assert readiness.capture_readiness_frontend_release(SHA, DEPLOYMENT)['reason'] == 'frontend_readiness_capture_busy'
    assert len(pending) == 1
    pending.pop()()  # Only actual worker completion releases the slot.
    assert 'marker' not in result
    assert readiness.capture_readiness_frontend_release(SHA, DEPLOYMENT)['reason'] == 'frontend_readiness_capture_timed_out'
    assert len(pending) == 1 and waits == [7, 7]
    pending.pop()()


@pytest.mark.parametrize('failure', ['capture', 'validation', 'startup'])
def test_exceptions_fail_closed_and_release_slot(monkeypatch, clock, failure):
    class InlineThread:
        def __init__(self, target, **kwargs): self.target = target
        def start(self):
            if failure == 'startup': raise RuntimeError('private detail')
            self.target()
    def fail(*args): raise RuntimeError('private detail')
    monkeypatch.setattr(readiness, 'Thread', InlineThread)
    monkeypatch.setattr(readiness.provenance, 'capture_frontend_release', fail if failure == 'capture' else lambda *args: {})
    if failure == 'validation': monkeypatch.setattr(readiness.provenance, 'verify_frontend_release', fail)
    result = readiness.capture_readiness_frontend_release(SHA, DEPLOYMENT)
    assert result['deployment_identity_verified'] is False
    assert result['reason'] == 'frontend_readiness_capture_failed'
    assert 'private detail' not in str(result)
    assert readiness._CAPTURE_SLOT.acquire(blocking=False)
    readiness._CAPTURE_SLOT.release()
