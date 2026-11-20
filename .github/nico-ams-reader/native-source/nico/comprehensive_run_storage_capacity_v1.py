"""Bounded, content-free measurements for a rejected canonical run save."""
from __future__ import annotations

import json
import sys
import time
from typing import Any

MEASUREMENT_LIMIT_BYTES = 1024 * 1024 * 1024
MEASUREMENT_LIMIT_SECONDS = 45.0


def measure_rejected_run(record: dict[str, Any], *, storage_limit_bytes: int) -> dict[str, Any]:
    """Count canonical bytes without retaining a second serialized run or its text.

    A completed count is exact. At the byte/time boundary only a lower bound is
    reported. This observer never changes the original rejection or storage caps.
    """
    started = time.monotonic()
    count = 0
    complete = False
    stop_reason = "measurement_failed"
    try:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for text in encoder.iterencode(record):
            count += len(text.encode("utf-8"))
            if count > MEASUREMENT_LIMIT_BYTES:
                stop_reason = "byte_limit"
                break
            if time.monotonic() - started >= MEASUREMENT_LIMIT_SECONDS:
                stop_reason = "time_limit"
                break
        else:
            complete = True
            stop_reason = "complete"
    except Exception:
        # Do not retain an exception message: it may contain record content.
        stop_reason = "measurement_failed"
    peak_rss_bytes = None
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform.startswith("linux"):
            peak_rss_bytes = int(peak * 1024)
    except (ImportError, ValueError, OSError):
        peak_rss_bytes = None
    return {
        "schema": "nico.run_storage_capacity.v1",
        "storage_limit_bytes": storage_limit_bytes,
        "canonical_size_bytes": count if complete else None,
        "canonical_size_lower_bound_bytes": count,
        "measurement_complete": complete,
        "measurement_stop_reason": stop_reason,
        "measurement_limit_bytes": MEASUREMENT_LIMIT_BYTES,
        "measurement_limit_seconds": MEASUREMENT_LIMIT_SECONDS,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "process_peak_rss_bytes": peak_rss_bytes,
        "peak_rss_scope": "current_process_lifetime",
        "record_content_retained": False,
        "storage_limits_changed": False,
    }
