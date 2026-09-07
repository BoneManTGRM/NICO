"""Synthetic scanner-byte durability proof for the existing local PostgreSQL CI service."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4


class ProofFailure(RuntimeError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProofFailure(code)


def _new_adapter(database_url: str):
    from nico.storage import PostgresAdapter
    return PostgresAdapter(database_url)


def run_proof(database_url: str) -> dict:
    # This script must never follow a production URL or libpq connection override.
    try:
        parsed = urlsplit(database_url)
        allowed = (parsed.scheme == "postgresql" and parsed.hostname == "127.0.0.1"
                   and parsed.port == 5432 and parsed.path == "/nico"
                   and not parsed.query and not parsed.fragment)
    except ValueError:
        allowed = False
    _require(allowed and not os.getenv("DATABASE_URL"), "test_database_required")
    from nico import scanner_raw_artifact_storage_v1 as artifacts
    from nico.storage import STORE

    suffix = uuid4().hex
    binding = {"run_id": "scanner_proof_run_" + suffix, "scan_id": "scanner_proof_scan_" + suffix,
               "customer_id": "scanner_proof_customer_" + suffix, "project_id": "scanner_proof_project_" + suffix,
               "repository": "synthetic/scanner-artifact-proof", "commit_sha": "a" * 40, "scanner_name": "synthetic"}
    raw = b'{"synthetic":true,"observations":["original scanner bytes"]}'
    compressed = gzip.compress(raw, mtime=0)
    raw_hash, gzip_hash = (hashlib.sha256(value).hexdigest() for value in (raw, compressed))
    previous_adapter = STORE.adapter
    try:
        STORE.adapter = _new_adapter(database_url)
        with TemporaryDirectory(prefix="nico-scanner-byte-proof-") as directory:
            root = Path(directory)
            blob = root / "synthetic.json.gz"
            blob.write_bytes(compressed)
            record = {"tool": binding["scanner_name"], "commit_sha": binding["commit_sha"], "status": "completed",
                      "raw_artifact_sha256": raw_hash,
                      "raw_artifact": {"storage_key": blob.name, "sha256": raw_hash, "gzip_sha256": gzip_hash,
                                       "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True}}
            retained = artifacts.persist_scanner_result(record, binding=binding, raw_root=root)
            _require(retained.get("raw_artifact_retention_complete") is True, "durable_write_failed")
            STORE.put("scanner_runs", binding["scan_id"], {**binding, "scanner_results": [retained]})
            blob.unlink()
            STORE.adapter = _new_adapter(database_url)
            restored = STORE.get("scanner_runs", binding["scan_id"])
            _require(bool(restored), "scanner_record_missing")
            retained = restored["scanner_results"][0]
            read = artifacts.read_scanner_artifact(retained, binding=binding, raw_root=root)
            _require(read.metadata["availability"] == "verified" and read.raw == raw and read.compressed == compressed,
                     "original_bytes_not_preserved")
            _require(read.metadata["sha256"] == raw_hash and read.metadata["gzip_sha256"] == gzip_hash, "hash_mismatch")
            for field in artifacts.BINDING_FIELDS:
                wrong = {**binding, field: "b" * 40 if field == "commit_sha" else "other-synthetic-value"}
                denied = artifacts.read_scanner_artifact(retained, binding=wrong, raw_root=root)
                _require(denied.metadata["availability"] == "source_mismatch" and denied.raw is None and denied.compressed is None,
                         "source_binding_not_enforced")
            for key in ("sha256", "gzip_sha256"):
                wrong = deepcopy(retained)
                wrong["raw_artifact"][key] = "0" * 64
                denied = artifacts.read_scanner_artifact(wrong, binding=binding, raw_root=root)
                _require(denied.metadata["availability"] != "verified" and denied.raw is None and denied.compressed is None,
                         "checksum_binding_not_enforced")
            store = artifacts.ScannerArtifactStore(STORE.adapter._connect)
            artifact_id = retained["raw_artifact"]["artifact_id"]
            _require(store.put(binding, compressed, raw_hash) == artifact_id, "idempotence_failed")
            try:
                store.put(binding, gzip.compress(b"changed synthetic bytes", mtime=0), hashlib.sha256(b"changed synthetic bytes").hexdigest())
            except artifacts.ImmutableArtifactConflict:
                pass
            else:
                raise ProofFailure("conflicting_overwrite_allowed")
            bounded = store.get(artifact_id, limit=1)
            _require(bounded["compressed"] is None and bounded["compressed_bytes"] == len(compressed), "bounded_bytea_read_failed")
            original = artifacts.read_scanner_artifact(retained, binding=binding, raw_root=root)
            _require(original.raw == raw and original.compressed == compressed and not blob.exists(), "original_changed_after_conflict")
        revision = os.getenv("GITHUB_SHA", "")
        return {"schema_version": 1, "evidence_kind": "synthetic_postgres_scanner_artifact_proof", "synthetic": True,
                "live_production_claim": False, "status": "passed", "finished_at": datetime.now(UTC).isoformat(),
                "application_commit": revision if re.fullmatch(r"[a-f0-9]{40}", revision) else None,
                "identity": binding, "hashes": {"raw_sha256": raw_hash, "gzip_sha256": gzip_hash},
                "proof": {"fresh_adapter_reconnected": True, "original_bytes_preserved": True,
                          "filesystem_removed": True, "source_binding_enforced": True, "checksum_binding_enforced": True,
                          "conflicting_overwrite_rejected": True, "bounded_bytea_read": True,
                          "human_approval": False, "client_delivery_allowed": False}}
    finally:
        STORE.adapter = previous_adapter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="audit-results/postgres-scanner-artifact-proof.json")
    args = parser.parse_args(argv)
    try:
        evidence = run_proof(os.getenv("NICO_TEST_DATABASE_URL", ""))
    except Exception:
        # Driver exception messages may contain DSNs or credentials.
        evidence = {"schema_version": 1, "evidence_kind": "synthetic_postgres_scanner_artifact_proof", "synthetic": True,
                    "live_production_claim": False, "status": "failed", "error_code": "scanner_artifact_proof_failed"}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"]}))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
