"""Static source-pinned selected definitions; checked by verifier before import."""
import json
import hashlib
from typing import Any
from collections.abc import Mapping
from nico.report_delivery_timing_v1 import report_delivery_phase
from nico.review_pdf_admission_observability_v1 import timed
def _review_history(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = record.get('review_history')
    if value is None:
        return []
    if not isinstance(value, list) or any((not isinstance(item, Mapping) for item in value)):
        raise ValueError('review_history_commitment_payload_invalid')
    return [dict(item) for item in value]

def _review_history_sha256(history: list[dict[str, Any]]) -> str:
    payload = json.dumps(history, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()

@timed('history_validation')
def _assert_review_history_commitment(record: Mapping[str, Any], *, committed_count: Any, committed_sha256: Any, allow_append: bool) -> list[dict[str, Any]]:
    if isinstance(committed_count, bool) or not isinstance(committed_count, int):
        raise ValueError('review_history_commitment_count_invalid')
    committed_digest = str(committed_sha256 or '').strip().casefold()
    history = _review_history(record)
    if committed_count < 0 or len(history) < committed_count:
        raise ValueError('review_history_commitment_cannot_be_truncated')
    if _review_history_sha256(history[:committed_count]) != committed_digest:
        raise ValueError('review_history_commitment_prefix_mismatch')
    if not allow_append and len(history) != committed_count:
        raise ValueError('review_history_commitment_uncommitted_events')
    return history
