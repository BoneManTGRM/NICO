from __future__ import annotations

import sys
from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v2_legacy as _legacy


# Re-export the proven acceptance implementation, including its private runtime
# helpers used by the v3 compatibility layer. Only final reconnect behavior is
# replaced below.
for _name, _value in vars(_legacy).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

VERSION = "nico.two_service_live_acceptance_reconnect.v4"
RECONNECT_MAX_ATTEMPTS = 4
RECONNECT_RETRY_MS = 2_000


def status_reconnect(
    page: Any,
    service: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Prove a fresh exact-run read after bounded transient transport failures.

    A completed assessment is not accepted from cached browser state or from the
    previously captured terminal payload alone. At least one fresh same-origin
    status read must succeed. Run identity, revision monotonicity, and integrity
    equality remain fail-closed and are never retried as transient failures.
    """

    rid = acceptance.run_id(payload)
    if not rid:
        raise AssertionError(f"{service} reconnect is missing the exact run ID")

    transient_errors: list[dict[str, Any]] = []
    response: Any | None = None
    path = ""
    successful_attempt = 0
    for attempt in range(1, RECONNECT_MAX_ATTEMPTS + 1):
        try:
            response, path = _status_request(page, service, payload)
            successful_attempt = attempt
            break
        except Exception as exc:
            transient_errors.append(
                {
                    "attempt": attempt,
                    "code": type(exc).__name__,
                    "message": acceptance.text(exc, 320),
                }
            )
            if attempt >= RECONNECT_MAX_ATTEMPTS:
                raise AssertionError(
                    f"{service} exact-run reconnect for {rid} failed after "
                    f"{RECONNECT_MAX_ATTEMPTS} transport attempts: "
                    f"{acceptance.text(exc, 320)}"
                ) from exc
            page.wait_for_timeout(RECONNECT_RETRY_MS)

    if response is None:
        raise AssertionError(f"{service} exact-run reconnect for {rid} returned no response")
    if not 200 <= response.status < 300:
        raise AssertionError(f"{service} reconnect returned HTTP {response.status}")

    current = acceptance.response_json(response)
    if acceptance.run_id(current) != rid:
        raise AssertionError(f"{service} reconnect changed run identity")

    before_revision, before_integrity = acceptance.integrity(payload)
    after_revision, after_integrity = acceptance.integrity(current)
    if before_revision is not None and after_revision is not None:
        if after_revision < before_revision:
            raise AssertionError(
                f"{service} reconnect moved revision backward from "
                f"{before_revision} to {after_revision}"
            )
    if before_integrity and after_integrity and after_integrity != before_integrity:
        raise AssertionError(f"{service} reconnect changed exact-run integrity")

    return {
        "artifact_schema": VERSION,
        "http_status": response.status,
        "run_id": rid,
        "request_url": _same_origin_url(page, path),
        "revision_before": before_revision,
        "revision_after": after_revision,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "identity_preserved": True,
        "attempts": successful_attempt,
        "transient_error_count": len(transient_errors),
        "transient_errors": transient_errors,
    }


def main(argv: list[str] | None = None) -> int:
    _legacy.status_reconnect = status_reconnect
    acceptance.status_reconnect = status_reconnect
    return _legacy.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
