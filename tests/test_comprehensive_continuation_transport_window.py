from pathlib import Path


PROXY = Path("apps/web/app/api/nico/[...path]/route.ts")
CLIENT = Path("apps/web/app/assessment/assessmentRunRequests.ts")


def test_continuation_transport_window_fits_function_budget_and_preserves_no_replay() -> None:
    proxy = PROXY.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    assert "export const maxDuration = 300" in proxy
    assert "const CONTINUATION_WRITE_TIMEOUT_MS = 240_000" in proxy
    assert "const SINGLE_ATTEMPT_DELAYS_MS = [0]" in proxy
    assert 'readClass: "single-attempt-continuation"' in proxy
    assert "retryDelaysMs: SINGLE_ATTEMPT_DELAYS_MS" in proxy
    assert '"assessment_run_continue_timeout"' in proxy

    assert "const RUN_CONTINUE_CLIENT_TIMEOUT_MS = 260_000" in client
    assert "runContinueRequest\n        ? RUN_CONTINUE_CLIENT_TIMEOUT_MS" in client
    assert ': boundedRequest\n      ? [0]\n      : CLIENT_RETRY_DELAYS_MS' in client

    # Ordering is intentional: backend proxy timeout < browser timeout < platform max.
    assert 240_000 < 260_000 < 300_000
