"""Reuse completed pending source-PDF computation for exact immutable SQL input.

The transport fingerprint is an invalidation key, never canonical integrity
proof. Only the original full record/history/package/installed PDF validators
can mint an entry. Changed inputs and cache misses always run those validators.
No raw run, mutable report, session or authorization decision is retained.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Response

from nico import comprehensive_run_storage_codec_v1 as codec
from nico.report_delivery_timing_v1 import report_delivery_phase

VERSION = "nico.retained_pdf_exact_input_cache.v1"
MAX_RETAINED_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 4
_CHUNK = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")
_SUPPORTED = {
    ("nico.comprehensive_run_storage.v1", "zlib+base64"),
    ("nico.comprehensive_run_storage.v2", "zlib+json-token-refs-v1+base64"),
    ("nico.comprehensive_run_storage.v3", "zlib+json-chunk-refs-v1+base64"),
}


@dataclass(frozen=True)
class _PendingPdf:
    body: bytes
    disposition: str
    run_id: str
    commit_sha: str
    language: str
    truth_sha256: str
    pdf_sha256: str
    repository: str | None = None

    def response(self) -> Response:
        headers = {
            "Content-Disposition": self.disposition,
            "X-NICO-Run-ID": self.run_id,
            "X-NICO-Commit-SHA": self.commit_sha,
            "X-NICO-Report-Language": self.language,
            "X-NICO-Canonical-Truth-SHA256": self.truth_sha256,
            "X-NICO-PDF-SHA256": self.pdf_sha256,
            "X-NICO-Artifact-SHA256": self.pdf_sha256,
            "X-NICO-Frozen-Source-Artifact": "true",
            "X-NICO-Assessment-Rerun": "false",
            "X-NICO-Approval-Status": "pending_human_approval",
            "X-NICO-Delivery-Status": "blocked_pending_human_approval",
            "X-NICO-Client-Delivery-Allowed": "false",
            "X-NICO-Localized-Artifact-Requires-New-Approval": "false",
        }
        if self.repository is not None:
            headers.update({
                "X-NICO-Repository": self.repository,
                "X-NICO-Artifact-Scope": "client-facing-same-run-projection",
                "X-NICO-Approval-State-Mutated": "false",
                "X-NICO-Delivery-State-Mutated": "false",
            })
        return Response(self.body, media_type="application/pdf", headers=headers)


# Global bounded population; opaque controller namespaces do not retain apps.
_entries: OrderedDict[tuple[Any, ...], tuple[_PendingPdf, int]] = OrderedDict()
_retained_bytes = 0
_lock = threading.Lock()


def _live_policy(builder: Any) -> tuple[Any, ...]:
    """Bind live codec, integrity, edition and installed projection implementations.

    Module code/configuration is fixed for an app lifetime; startup wrappers and
    supported live callable/limit replacement must still invalidate old entries.
    Holding the callable objects also prevents recycled object IDs matching old
    policy. No request/session data or mutable module dictionaries are retained.
    """

    names = (
        'nico.comprehensive_run_store', 'nico.comprehensive_run_record',
        'nico.comprehensive_run_service',
        'nico.comprehensive_run_storage_codec_v1',
        'nico.comprehensive_run_storage_chunks_v1', 'nico.comprehensive_run_storage_dedup_v1',
        'nico.comprehensive_api_controller', 'nico.comprehensive_same_run_locale_report_v1',
        'nico.comprehensive_commercial_ship_projection_v1',
        'nico.comprehensive_commercial_ship_projection_v3',
        'nico.comprehensive_client_delivery_contract_v1',
        'nico.decision_grade_accepted_edition_guard_v1',
        'nico.comprehensive_review_decision_v1', 'nico.report_pdf_text',
    )
    policy: list[Any] = [VERSION, builder, MAX_RETAINED_BYTES, MAX_ENTRIES]
    for name in names:
        module = sys.modules.get(name)
        policy.append(name)
        if module is None:
            policy.append(None)
            continue
        policy.append(getattr(module, 'VERSION', None))
        for attribute, value in sorted(vars(module).items()):
            if inspect.isfunction(value):
                policy.extend((attribute, value))
            elif inspect.isclass(value) and value.__module__ == name:
                for method, descriptor in sorted(vars(value).items()):
                    if inspect.isfunction(descriptor):
                        policy.extend((attribute, method, descriptor))
                    elif isinstance(descriptor, (staticmethod, classmethod)):
                        policy.extend((attribute, method, descriptor.__func__))
            elif attribute.startswith(('MAX_', '_MAX_', '_HASH_')) and type(value) in (int, str, bool):
                policy.extend((attribute, value))
            elif attribute.startswith('_FINAL_REPORT_') and type(value) in (set, frozenset, tuple):
                policy.extend((attribute, tuple(sorted(value))))
    return tuple(policy)


@report_delivery_phase("retained_pdf_input_fingerprint")
def _snapshot_fingerprint(row: Any, run_id: str, language: str) -> str | None:
    if row is None or len(row) != 14 or row[3] != run_id:
        return None
    if type(row[1]) is not int or row[1] < 0 or type(row[2]) is not str or not _SHA.fullmatch(row[2]):
        return None
    # Restrict reuse to pending terminal records. Approval/rejection and legacy
    # backfill retain the complete normal computation on every request.
    if row[9] != "review_required" or row[11] not in (True, 1) or language not in ("en", "es-MX"):
        return None
    try:
        # A legacy uncompressed TEXT record must not be parsed twice simply to
        # discover it is ineligible. Current encoded envelopes have this prefix;
        # other valid wire layouts take the unchanged full restoration path.
        if type(row[0]) is str:
            if len(row[0]) > 4 * ((codec.MAX_COMPRESSED_BYTES + 2) // 3) + _CHUNK:
                return None
            if not row[0].startswith('{"' + codec.ENVELOPE_KEY + '":'):
                return None
        payload = json.loads(row[0]) if type(row[0]) is str else row[0]
        if type(payload) is not dict or set(payload) != {codec.ENVELOPE_KEY}:
            return None
        envelope = payload[codec.ENVELOPE_KEY]
        if type(envelope) is not dict or set(envelope) != {"schema", "encoding", "size_bytes", "sha256", "data"}:
            return None
        if (envelope['schema'], envelope['encoding']) not in _SUPPORTED:
            return None
        if type(envelope['size_bytes']) is not int or not 0 < envelope['size_bytes'] <= codec.MAX_UNCOMPRESSED_BYTES:
            return None
        if type(envelope['sha256']) is not str or not _SHA.fullmatch(envelope['sha256']):
            return None
        data = envelope['data']
        if type(data) is not str or len(data) > 4 * ((codec.MAX_COMPRESSED_BYTES + 2) // 3):
            return None
        if any(type(value) not in (str, int, bool, type(None)) for value in row[1:]):
            return None
        # Bound before JSON encoding, including escaped UTF-8 and integer digits.
        scalar_cost = 1024 + 6 * (len(run_id) + len(language))
        for value in row[1:]:
            if type(value) is str:
                scalar_cost += 2 + 6 * len(value)
            elif type(value) is int:
                scalar_cost += 3 + value.bit_length() // 3
            else:
                scalar_cost += 5
            if scalar_cost > _CHUNK:
                return None
        metadata = [VERSION, run_id, language, list(row[1:]),
                    {key: envelope[key] for key in ('schema', 'encoding', 'size_bytes', 'sha256')}]
        encoded_metadata = json.dumps(metadata, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(encoded_metadata) > _CHUNK:
            return None
        digest = hashlib.sha256(b'NICO retained PDF exact-input proof cache\x00')
        digest.update(len(encoded_metadata).to_bytes(8, 'big'))
        digest.update(encoded_metadata)
        digest.update(len(data).to_bytes(8, 'big'))
        for offset in range(0, len(data), _CHUNK):
            digest.update(data[offset:offset + _CHUNK].encode('ascii'))
        return digest.hexdigest()
    except (ValueError, TypeError, KeyError, UnicodeError):
        # Eligibility cannot turn an invalid input into success; restoration owns
        # the original precise failure and codec limits on the fallback path.
        return None


def _pending_pdf(response: Any, run_id: str, language: str, row: Any) -> _PendingPdf | None:
    if type(response) is not Response or response.status_code != 200 or response.background is not None:
        return None
    if type(response.body) is not bytes or len(response.body) > MAX_RETAINED_BYTES or not response.body.startswith(b'%PDF'):
        return None
    headers = response.headers
    expected = {
        'content-type': 'application/pdf', 'x-nico-run-id': run_id,
        'x-nico-commit-sha': row[7], 'x-nico-report-language': language,
        'x-nico-frozen-source-artifact': 'true', 'x-nico-assessment-rerun': 'false',
        'x-nico-approval-status': 'pending_human_approval',
        'x-nico-delivery-status': 'blocked_pending_human_approval',
        'x-nico-client-delivery-allowed': 'false',
        'x-nico-localized-artifact-requires-new-approval': 'false',
    }
    if any(headers.get(name) != value for name, value in expected.items()):
        return None
    truth = headers.get('x-nico-canonical-truth-sha256', '')
    pdf = hashlib.sha256(response.body).hexdigest()
    if not _SHA.fullmatch(truth) or headers.get('x-nico-pdf-sha256') != pdf or headers.get('x-nico-artifact-sha256') != pdf:
        return None
    disposition = headers.get('content-disposition', '')
    if not disposition or len(disposition) > 4096:
        return None
    repository = None
    if any(headers.get(name) is not None for name in (
        'x-nico-repository', 'x-nico-artifact-scope',
        'x-nico-approval-state-mutated', 'x-nico-delivery-state-mutated',
    )):
        if any(headers.get(name) != value for name, value in {
            'x-nico-repository': row[6],
            'x-nico-artifact-scope': 'client-facing-same-run-projection',
            'x-nico-approval-state-mutated': 'false',
            'x-nico-delivery-state-mutated': 'false',
        }.items()):
            return None
        repository = row[6]
    entry = _PendingPdf(response.body, disposition, run_id, row[7], language, truth, pdf, repository)
    # Preserve exact original semantics; unforeseen extra/custom response headers
    # make this path ineligible instead of being retained as authorization state.
    if dict(entry.response().headers) != dict(headers):
        return None
    return entry


@dataclass(frozen=True)
class _PreparedPdf:
    key: tuple[Any, ...]
    metadata: tuple[Any, ...] | None
    run_id: str
    language: str
    builder: Any
    cached: _PendingPdf | None

    def after_restore(self, row: Any, record: Any) -> _PreparedPdf:
        fingerprint = self.key[2]
        identity = record.get('identity', {})
        matches = self.metadata is not None and all(
            identity.get(field) == self.metadata[index]
            for field, index in (('run_id', 2), ('customer_id', 3), ('project_id', 4),
                                 ('repository', 5), ('commit_sha', 6), ('evidence_ledger_id', 7))
        ) and all(record.get(field) == self.metadata[index]
                  for field, index in (('status', 8), ('revision', 9), ('terminal', 10),
                                       ('integrity_sha256', 11), ('updated_at', 12)))
        if (not matches or _snapshot_fingerprint(row, self.run_id, self.language) != fingerprint
                or _live_policy(self.builder) != self.key[1]):
            return _PreparedPdf(self.key, None, self.run_id, self.language, self.builder, None)
        return self


@report_delivery_phase("retained_pdf_cache_probe")
def prepare_retained_pdf(*, namespace: Any, row: Any, run_id: str,
                         report_language: str, builder: Any) -> _PreparedPdf:
    global _retained_bytes
    policy = _live_policy(builder)
    fingerprint = _snapshot_fingerprint(row, run_id, report_language)
    key = (namespace, policy, fingerprint, report_language)
    metadata = tuple(row[1:]) if fingerprint is not None else None
    if fingerprint is not None:
        with _lock:
            stored = _entries.get(key)
            if stored is not None:
                entry, size = stored
                # Immutable bytes get a fresh small digest and a fresh Response;
                # no shared mutable headers or cached session decisions escape.
                if (entry.run_id == run_id and entry.language == report_language
                        and entry.commit_sha == metadata[6]
                        and (entry.repository is None or entry.repository == metadata[5])
                        and hashlib.sha256(entry.body).hexdigest() == entry.pdf_sha256):
                    _entries.move_to_end(key)
                    return _PreparedPdf(key, metadata, run_id, report_language, builder, entry)
                del _entries[key]
                _retained_bytes -= size
    return _PreparedPdf(key, metadata, run_id, report_language, builder, None)


@report_delivery_phase("retained_pdf_exact_input")
def finish_retained_pdf(prepared: _PreparedPdf, build: Callable[[], Response]) -> Response:
    global _retained_bytes
    if prepared.cached is not None:
        if _live_policy(prepared.builder) == prepared.key[1]:
            return prepared.cached.response()
        # The fallback reloads current input. Even if policy returns to its old
        # value while rebuilding, that result is not proof for this old ticket.
        return build()
    response = build()
    if prepared.metadata is None:
        return response
    # Only small frozen metadata remains after SQL restoration. No compressed
    # row, database cursor, lazy loader or mutable run is retained by this ticket.
    entry = _pending_pdf(response, prepared.run_id, prepared.language, (None, *prepared.metadata))
    key = prepared.key
    policy = key[1]
    if entry is None or _live_policy(prepared.builder) != policy:
        return response
    # Conservative accounting counts each scalar, body, dataclass, tuple and key.
    size = sys.getsizeof(entry) + sys.getsizeof(key) + sys.getsizeof(entry.__dict__)
    size += sum(sys.getsizeof(value) for value in entry.__dict__.values())
    size += sum(sys.getsizeof(value) for value in key)
    size += sum(sys.getsizeof(value) for value in policy)
    size += sys.getsizeof((entry, size)) + 512  # OrderedDict/entry indexing allowance.
    if size > MAX_RETAINED_BYTES:
        return response
    with _lock:
        prior = _entries.pop(key, None)
        if prior is not None:
            _retained_bytes -= prior[1]
        while _entries and (len(_entries) >= MAX_ENTRIES or _retained_bytes + size > MAX_RETAINED_BYTES):
            _, removed = _entries.popitem(last=False)
            _retained_bytes -= removed[1]
        _entries[key] = (entry, size)
        _retained_bytes += size
    return response
