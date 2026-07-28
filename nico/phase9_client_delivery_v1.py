from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "nico.phase9_client_delivery.v1"


class DeliveryAuthorizationError(ValueError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_inventory(paths: Mapping[str, str | Path]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for label, raw_path in sorted(paths.items()):
        path = Path(raw_path)
        if not path.is_file():
            raise DeliveryAuthorizationError(f"missing required artifact: {label} -> {path}")
        payload = path.read_bytes()
        if not payload:
            raise DeliveryAuthorizationError(f"empty required artifact: {label} -> {path}")
        inventory[label] = {
            "path": str(path),
            "sha256": _sha256_bytes(payload),
            "size_bytes": len(payload),
        }
    return inventory


def package_fingerprint(*, repository: str, revision: str, inventory: Mapping[str, Any]) -> str:
    payload = {
        "repository": repository,
        "revision": revision,
        "inventory": inventory,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_pending_delivery_record(
    *,
    repository: str,
    revision: str,
    run_id: str,
    artifacts: Mapping[str, str | Path],
    required_labels: Sequence[str],
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    inventory = artifact_inventory(artifacts)
    missing = sorted(set(required_labels) - set(inventory))
    if missing:
        raise DeliveryAuthorizationError(f"missing required package labels: {missing}")
    fingerprint = package_fingerprint(repository=repository, revision=revision, inventory=inventory)
    return {
        "version": VERSION,
        "repository": repository,
        "immutable_revision": revision,
        "run_id": run_id,
        "package_fingerprint": fingerprint,
        "artifact_inventory": inventory,
        "limitations": list(limitations),
        "approval": {
            "status": "pending",
            "reviewer": None,
            "reviewer_role": None,
            "approved_package_fingerprint": None,
            "approved_revision": None,
            "approved_at": None,
        },
        "client_delivery_allowed": False,
    }


def authorize_exact_package(
    record: Mapping[str, Any],
    *,
    reviewer: str,
    reviewer_role: str,
    approved_at: str,
    observed_package_fingerprint: str,
    observed_revision: str,
    accepted_limitations: Sequence[str],
) -> dict[str, Any]:
    expected_fingerprint = str(record.get("package_fingerprint") or "")
    expected_revision = str(record.get("immutable_revision") or "")
    if not reviewer.strip() or not reviewer_role.strip():
        raise DeliveryAuthorizationError("identified reviewer and reviewer role are required")
    if observed_package_fingerprint != expected_fingerprint:
        raise DeliveryAuthorizationError("approval fingerprint does not match the exact package")
    if observed_revision != expected_revision:
        raise DeliveryAuthorizationError("approval revision does not match the assessed revision")
    expected_limitations = sorted(str(item) for item in record.get("limitations") or [])
    if sorted(str(item) for item in accepted_limitations) != expected_limitations:
        raise DeliveryAuthorizationError("all retained limitations must be explicitly accepted")

    result = deepcopy(dict(record))
    result["approval"] = {
        "status": "approved",
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "approved_package_fingerprint": expected_fingerprint,
        "approved_revision": expected_revision,
        "approved_at": approved_at,
        "accepted_limitations": list(accepted_limitations),
    }
    result["client_delivery_allowed"] = True
    return result


def invalidate_if_package_changed(record: Mapping[str, Any], current_inventory: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(record))
    current = package_fingerprint(
        repository=str(record.get("repository") or ""),
        revision=str(record.get("immutable_revision") or ""),
        inventory=current_inventory,
    )
    if current != record.get("package_fingerprint"):
        result["approval"] = {
            "status": "invalidated",
            "reason": "package_changed_after_approval",
            "previous_package_fingerprint": record.get("package_fingerprint"),
            "current_package_fingerprint": current,
        }
        result["client_delivery_allowed"] = False
    return result
