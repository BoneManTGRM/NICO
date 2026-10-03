from __future__ import annotations

import hashlib
import json
import tracemalloc
from datetime import datetime, timezone

import pytest

from nico import comprehensive_run_record as records


def _reference(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()


def test_retained_record_hash_batches_tiny_updates_without_changing_the_digest(monkeypatch):
    payload = {"stages": [{"id": index, "status": "complete", "verified": True,
                          "evidence": ["retained", "ñ", "native"], "score": 90}
                         for index in range(2000)]}
    expected = _reference(payload)
    actual_hash = hashlib.sha256
    updates = []

    class ObservedHash:
        def __init__(self):
            self.digest = actual_hash()

        def update(self, chunk):
            updates.append(len(chunk))
            self.digest.update(chunk)

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr(records.hashlib, "sha256", ObservedHash)
    assert records._canonical_hash(payload) == expected
    assert len(updates) < 100
    assert all(size > 1024 for size in updates[:-1])


@pytest.mark.parametrize("payload", [
    {}, [], [None, True, False, 0, -1, 1.5, -0.0, 1e-300, 1e300],
    {"b": ["ñ", "東京", "\\", "\n", "\x00", "\"", "\U0001f34e"], "a": {}},
    {"scalars": [float("nan"), float("inf"), float("-inf")]},
    {"default": datetime(2026, 10, 3, tzinfo=timezone.utc)},
    {"tuple": (1, "retained", {"score": 82})},
    {"key" + "x" * 70000: {"large_scalar": "ñ" * 70000}},
    {"nested": [[{"status": "pending", "delivery": False}]]},
    {1: "integer key", 2: "second"},
])
def test_standard_canonical_digest_parity(payload):
    assert records._canonical_hash(payload) == _reference(payload)


def test_shared_containers_are_not_circular_and_changed_evidence_changes_hash():
    shared = {"run": "comprun_fixture", "source": "a" * 40, "approved": False}
    payload = {"first": shared, "second": [shared]}
    original = records._canonical_hash(payload)
    assert original == _reference(payload)
    shared["source"] = "b" * 40
    assert records._canonical_hash(payload) != original
    assert records._canonical_hash(payload) == _reference(payload)


@pytest.mark.parametrize("kind", ["list", "dict"])
def test_circular_records_are_rejected(kind):
    payload = [] if kind == "list" else {}
    if kind == "list":
        payload.append(payload)
    else:
        payload["cycle"] = payload
    with pytest.raises(ValueError, match="Circular reference"):
        records._canonical_hash(payload)


def test_mixed_sort_key_types_preserve_the_existing_failure():
    with pytest.raises(TypeError):
        records._canonical_hash({"string": 1, 2: "integer"})


def test_invalid_unicode_preserves_utf8_rejection():
    with pytest.raises(UnicodeEncodeError):
        records._canonical_hash({"text": "\ud800"})


def test_large_container_does_not_materialize_another_full_json_document():
    leaf = {"status": "complete", "evidence": ["retained" * 80], "approval": False}
    payload = {"retained": [leaf for _ in range(12000)]}
    expected = _reference(payload)
    tracemalloc.start()
    try:
        actual = records._canonical_hash(payload)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert actual == expected
    assert peak < 1024 * 1024


def test_common_scalar_leaves_do_not_initialize_a_native_container_encoder(monkeypatch):
    payload = {"retained": [f"literal-{index}" for index in range(1000)]}
    expected = _reference(payload)
    real_iterencode = records.json.JSONEncoder.iterencode
    native_scalar_calls = []

    def observe(self, value, _one_shot=False):
        if _one_shot and type(value) in (str, int, bool, type(None)):
            native_scalar_calls.append(True)
        return real_iterencode(self, value, _one_shot=_one_shot)

    monkeypatch.setattr(records.json.JSONEncoder, "iterencode", observe)
    assert records._canonical_hash(payload) == expected
    assert not native_scalar_calls
