from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg

from nico.comprehensive_run_store import (
    ComprehensiveRunStore,
    _public_intake_payload_sha256,
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_proof(database_url: str) -> dict[str, object]:
    token = uuid4().hex
    run_id = f"comprun_{token}"
    payload = {
        "run_id": run_id,
        "repository": "synthetic/public-provider-reservation-proof",
        "provider": "gitlab",
        "human_evidence": {"synthetic": "terminal payload must be scrubbed"},
    }
    digest = _public_intake_payload_sha256(payload)

    def store() -> ComprehensiveRunStore:
        return ComprehensiveRunStore(
            lambda: psycopg.connect(database_url),
            dialect="postgres",
        )

    initial = store()
    initial.ensure_schema()
    seeded = initial.reserve_public_intake(
        run_id=run_id,
        request_sha256=digest,
        payload=payload,
        now_epoch=1,
        lease_seconds=1,
        updated_at=_now(),
    )
    if seeded.get("lease_owner") is not True:
        raise RuntimeError("postgres_reservation_seed_not_owned")

    def reclaim(_index: int) -> dict[str, object]:
        return store().reserve_public_intake(
            run_id=run_id,
            request_sha256=digest,
            payload=payload,
            now_epoch=10,
            lease_seconds=30,
            updated_at=_now(),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(reclaim, range(8)))
    owners = [item for item in attempts if item.get("lease_owner") is True]
    if len(owners) != 1:
        raise RuntimeError("postgres_reservation_single_owner_violation")
    owner = owners[0]
    if not store().heartbeat_public_intake(
        run_id=run_id,
        lease_id=str(owner["lease_id"]),
        lease_until_epoch=100,
        updated_at=_now(),
    ):
        raise RuntimeError("postgres_reservation_heartbeat_failed")
    active = store().reserve_public_intake(
        run_id=run_id,
        request_sha256=digest,
        payload=payload,
        now_epoch=50,
        lease_seconds=30,
        updated_at=_now(),
    )
    if active.get("lease_owner") is True:
        raise RuntimeError("postgres_reservation_active_lease_reclaimed")
    if not store().complete_public_intake(
        run_id=run_id,
        lease_id=str(owner["lease_id"]),
        commit_sha="a" * 40,
        updated_at=_now(),
    ):
        raise RuntimeError("postgres_reservation_completion_failed")
    terminal = store().load_public_intake(run_id)
    if terminal is None or terminal.get("status") != "accepted":
        raise RuntimeError("postgres_reservation_terminal_truth_missing")
    if "human_evidence" in dict(terminal.get("payload") or {}):
        raise RuntimeError("postgres_reservation_terminal_payload_not_scrubbed")

    return {
        "artifact_schema": "nico.postgres_public_intake_reservation_proof.v1",
        "status": "passed",
        "synthetic": True,
        "live_production_claim": False,
        "proof": {
            "concurrent_attempts": len(attempts),
            "exactly_one_lease_owner": True,
            "active_heartbeat_prevented_reclaim": True,
            "terminal_payload_scrubbed": True,
            "request_hash_bound": True,
            "human_review_required": True,
            "human_approval": False,
            "client_delivery_allowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_proof(args.database_url)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
