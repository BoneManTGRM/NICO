"""Synthetic near-cap storage qualification; never connects to production by default."""
from __future__ import annotations

import argparse
import base64
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import sqlite3
# A fresh interpreter is required to qualify reconnect behavior.
import subprocess  # nosec B404
import sys
import tempfile
import time
from uuid import uuid4

from nico import comprehensive_run_storage_codec_v1 as codec
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, apply_comprehensive_stage_result, create_comprehensive_run_record
from nico.comprehensive_run_store import ComprehensiveRunStore


def store() -> ComprehensiveRunStore:
    local = os.getenv("NICO_STORAGE_QUALIFICATION_SQLITE")
    if local:
        return ComprehensiveRunStore(lambda: sqlite3.connect(local))
    import psycopg
    database = os.environ["NICO_TEST_DATABASE_URL"]
    return ComprehensiveRunStore(lambda: psycopg.connect(database), dialect="postgres")


def canonical_hash(value: object) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    for token in encoder.iterencode(value):
        digest.update(token.encode("utf-8"))
    return digest.hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def fresh_reader(run_id: str, expected: dict) -> dict:
    restored = store().load(run_id)
    require(restored["identity"] == expected["identity"], "capacity_identity_mismatch")
    require(restored["revision"] == expected["revision"], "capacity_revision_mismatch")
    require(restored["integrity_sha256"] == expected["integrity_sha256"], "capacity_integrity_mismatch")
    require(restored["human_review_required"] is True, "capacity_review_gate_weakened")
    require(restored["client_delivery_allowed"] is False, "capacity_delivery_gate_weakened")
    aliases = restored["synthetic_capacity_evidence"]
    require(len(aliases) == expected["alias_count"], "capacity_alias_count_mismatch")
    require(all(canonical_hash(alias) == expected["alias_sha256"] for alias in aliases), "capacity_alias_content_mismatch")
    return {"fresh_process_reconnected": True, "all_aliases_exact": True,
            "integrity_and_review_gates_preserved": True,
            "reader_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}


def qualify(transport: str) -> dict:
    target_bytes = 960 * 1024 * 1024
    # Deterministic synthetic evidence, never security material.
    rng = random.Random(2011)  # nosec B311
    if transport == "v2":
        value = base64.b64encode(rng.randbytes(12 * 1024 * 1024)).decode("ascii")
    else:
        # Pieces stay below the token-reference threshold: this must qualify v3.
        value = [base64.b64encode(rng.randbytes(3000)).decode("ascii") for _ in range(4096)]
    value_bytes = len(json.dumps(value, separators=(",", ":")).encode())
    copies = target_bytes // value_bytes + 1
    run_id = "comprun_" + uuid4().hex
    adapter = store()
    adapter.ensure_schema()
    original = adapter.create(create_comprehensive_run_record(
        run_id=run_id, repository="synthetic/storage-capacity", commit_sha="a" * 40,
        evidence_ledger_id="ledger_" + run_id, customer_id="synthetic_capacity",
        project_id="synthetic_capacity", authorized=True,
    ))
    record = apply_comprehensive_stage_result(original, stage_id=COMPREHENSIVE_STAGES[0], result={"status": "complete"})
    record["synthetic_capacity_evidence"] = [value] * copies
    record["integrity_sha256"] = _record_hash(record)
    expected = {"identity": record["identity"], "revision": record["revision"],
                "integrity_sha256": record["integrity_sha256"], "alias_count": copies,
                "alias_sha256": canonical_hash(value)}
    started = time.monotonic()
    adapter.save(record, expected_revision=original["revision"])
    save_seconds = round(time.monotonic() - started, 3)
    with adapter._connection() as connection:
        cursor = connection.cursor()
        query = "SELECT payload FROM nico_comprehensive_runs WHERE run_id = %s" if adapter.placeholder == "%s" else "SELECT payload FROM nico_comprehensive_runs WHERE run_id = ?"
        cursor.execute(query, (run_id,))
        payload = cursor.fetchone()[0]
    envelope = (json.loads(payload) if isinstance(payload, str) else payload)[codec.ENVELOPE_KEY]
    require(target_bytes < envelope["size_bytes"] < codec.MAX_UNCOMPRESSED_BYTES, "capacity_fixture_size_invalid")
    require(envelope["schema"] == "nico.comprehensive_run_storage." + transport, "capacity_transport_not_qualified")
    require(len(base64.b64decode(envelope["data"])) <= codec.MAX_COMPRESSED_BYTES, "capacity_compressed_cap_exceeded")
    packed_bytes = len(base64.b64decode(envelope["data"]))
    canonical_size_bytes = envelope["size_bytes"]
    del record, value, payload, envelope, adapter
    gc.collect()
    # Execute this trusted script with the fixed interpreter and a generated UUID.
    reader = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--read-run-id", run_id],  # nosec B603
                            input=json.dumps(expected), text=True, capture_output=True, check=True,
                            timeout=180)
    checks = json.loads(reader.stdout)
    writer_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    require(writer_peak < 6 * 1024**3, "capacity_writer_memory_limit")
    require(checks["reader_peak_rss_bytes"] < 6 * 1024**3, "capacity_reader_memory_limit")
    return {"status": "passed", "synthetic": True, "live_production_claim": False,
            "transport": transport, "canonical_size_bytes": canonical_size_bytes,
            "expanded_cap_bytes": codec.MAX_UNCOMPRESSED_BYTES,
            "compressed_bytes": packed_bytes, "compressed_cap_bytes": codec.MAX_COMPRESSED_BYTES,
            "save_seconds": save_seconds, "writer_peak_rss_bytes": writer_peak,
            "checks": checks, "human_approval": False, "client_delivery_allowed": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("v2", "v3"), default="v3")
    parser.add_argument("--sqlite", action="store_true")
    parser.add_argument("--read-run-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.read_run_id:
        print(json.dumps(fresh_reader(args.read_run_id, json.load(sys.stdin)), sort_keys=True))
        return
    with tempfile.TemporaryDirectory(prefix="nico-capacity-proof-") as directory:
        if args.sqlite:
            os.environ["NICO_STORAGE_QUALIFICATION_SQLITE"] = str(Path(directory) / "runs.sqlite")
        result = qualify(args.transport)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
