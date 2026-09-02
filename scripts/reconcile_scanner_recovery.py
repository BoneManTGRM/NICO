#!/usr/bin/env python3
"""Review and close interrupted scanner runs through NICO's audited API.

The command is intentionally two-phase.  The first invocation exports a
redacted, hash-bound manifest.  A later invocation can close only the exact
records in that reviewed manifest, and only when the live inventory still
matches it.  It never resumes work, deletes evidence, or guesses whether a run
is still authorized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping


MANIFEST_SCHEMA = "nico.scanner_recovery_close_manifest.v1"
ALLOWED_REASONS = {
    "superseded_by_terminal_assessment",
    "authorization_expired",
    "duplicate_or_test_run",
    "no_longer_required",
}


class OperatorError(RuntimeError):
    pass


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _redacted_item(item: Mapping[str, Any]) -> dict[str, Any]:
    recovery = item.get("recovery") if isinstance(item.get("recovery"), Mapping) else {}
    repository = _text(item.get("repository"), 500)
    return {
        "scan_id": _text(item.get("scan_id"), 120),
        "run_id": _text(item.get("run_id"), 120) or None,
        "repository_sha256": hashlib.sha256(repository.encode("utf-8")).hexdigest() if repository else None,
        "created_at": _text(item.get("created_at"), 40) or None,
        "updated_at": _text(item.get("updated_at"), 40) or None,
        "recovery_reason": _text(recovery.get("reason"), 120) or "interrupted_execution",
        "recovery_attempt": int(recovery.get("attempt") or 0),
    }


def build_manifest(inventory: Mapping[str, Any]) -> dict[str, Any]:
    raw_items = inventory.get("recovery_required")
    if not isinstance(raw_items, list):
        raise OperatorError("recovery_inventory_invalid")
    items = sorted(
        (_redacted_item(item) for item in raw_items if isinstance(item, Mapping)),
        key=lambda item: item["scan_id"],
    )
    if any(not item["scan_id"] for item in items):
        raise OperatorError("recovery_inventory_scan_id_missing")
    if len({item["scan_id"] for item in items}) != len(items):
        raise OperatorError("recovery_inventory_duplicate_scan_id")
    return {
        "artifact_schema": MANIFEST_SCHEMA,
        "recovery_required_count": len(items),
        "inventory_sha256": _canonical_sha256(items),
        "items": items,
        "review": {
            "reviewed": False,
            "reviewed_by": "",
            "reason_code": "",
        },
        "guardrail": "Set reviewed=true only after confirming every exact scan ID is obsolete. Evidence is retained.",
    }


def validate_reviewed_manifest(
    manifest: Mapping[str, Any],
    current_inventory: Mapping[str, Any],
    *,
    confirmation_sha256: str,
    actor: str,
    reason_code: str,
) -> list[str]:
    if manifest.get("artifact_schema") != MANIFEST_SCHEMA:
        raise OperatorError("recovery_manifest_schema_invalid")
    current = build_manifest(current_inventory)
    expected = _text(manifest.get("inventory_sha256"), 64).lower()
    supplied = _text(confirmation_sha256, 64).lower()
    if not expected or expected != supplied:
        raise OperatorError("recovery_manifest_confirmation_mismatch")
    if current["inventory_sha256"] != expected:
        raise OperatorError("recovery_inventory_changed_refresh_manifest")
    review = manifest.get("review") if isinstance(manifest.get("review"), Mapping) else {}
    if review.get("reviewed") is not True:
        raise OperatorError("recovery_manifest_not_reviewed")
    if _text(review.get("reviewed_by"), 120) != _text(actor, 120):
        raise OperatorError("recovery_manifest_actor_mismatch")
    if _text(review.get("reason_code"), 120) != reason_code:
        raise OperatorError("recovery_manifest_reason_mismatch")
    if reason_code not in ALLOWED_REASONS:
        raise OperatorError("recovery_close_reason_invalid")
    scan_ids = [str(item["scan_id"]) for item in current["items"]]
    if not scan_ids:
        raise OperatorError("recovery_manifest_empty")
    return scan_ids


class RecoveryApi:
    def __init__(self, *, base_url: str, admin_token: str, timeout_seconds: int = 30) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise OperatorError("nico_api_url_must_be_https")
        if not admin_token.strip():
            raise OperatorError("nico_admin_token_required")
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.timeout_seconds = max(5, min(int(timeout_seconds), 120))

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "X-NICO-Admin-Token": self.admin_token,
        }
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OperatorError(f"nico_api_http_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OperatorError(f"nico_api_request_failed:{exc.__class__.__name__}") from exc
        if not isinstance(result, dict):
            raise OperatorError("nico_api_response_invalid")
        return result

    def inventory(self, *, refresh: bool = True) -> dict[str, Any]:
        suffix = "?refresh=true&limit=500" if refresh else "?refresh=false&limit=500"
        return self._request("GET", f"/operations/recovery{suffix}")

    def close(self, scan_id: str, *, actor: str, reason_code: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(scan_id, safe="")
        return self._request(
            "POST",
            f"/operations/recovery/scanner/{encoded}/close",
            {"actor": actor, "reason_code": reason_code},
        )


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def apply_manifest(
    *,
    api: RecoveryApi,
    manifest: Mapping[str, Any],
    confirmation_sha256: str,
    actor: str,
    reason_code: str,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    current = api.inventory(refresh=True)
    scan_ids = validate_reviewed_manifest(
        manifest,
        current,
        confirmation_sha256=confirmation_sha256,
        actor=actor,
        reason_code=reason_code,
    )
    closed: list[str] = []
    for scan_id in scan_ids:
        response = api.close(scan_id, actor=actor, reason_code=reason_code)
        if response.get("status") != "cancelled":
            raise OperatorError(f"recovery_close_unexpected_status:{scan_id}")
        closed.append(scan_id)
        if progress is not None:
            progress({"closed": len(closed), "total": len(scan_ids), "scan_id_sha256": hashlib.sha256(scan_id.encode()).hexdigest()})
    remaining_manifest = build_manifest(api.inventory(refresh=True))
    remaining_ids = {item["scan_id"] for item in remaining_manifest["items"]}
    if remaining_ids.intersection(closed):
        raise OperatorError("recovery_close_verification_failed")
    return {
        "status": "complete",
        "closed": len(closed),
        "requested": len(scan_ids),
        "remaining_recovery_required": remaining_manifest["recovery_required_count"],
        "reason_code": reason_code,
        "evidence_retained": True,
    }


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("NICO_API_URL", ""))
    parser.add_argument("--write-manifest", type=Path)
    parser.add_argument("--apply-manifest", type=Path)
    parser.add_argument("--confirm-inventory-sha256", default="")
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason-code", choices=sorted(ALLOWED_REASONS), default=None)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        if bool(args.write_manifest) == bool(args.apply_manifest):
            raise OperatorError("choose_exactly_one_manifest_mode")
        api = RecoveryApi(
            base_url=args.api_url,
            admin_token=os.getenv("NICO_ADMIN_TOKEN", ""),
            timeout_seconds=args.timeout_seconds,
        )
        if args.write_manifest:
            manifest = build_manifest(api.inventory(refresh=True))
            _write_manifest(args.write_manifest, manifest)
            print(json.dumps({
                "status": "review_required",
                "manifest": str(args.write_manifest.resolve()),
                "recovery_required_count": manifest["recovery_required_count"],
                "inventory_sha256": manifest["inventory_sha256"],
            }, sort_keys=True))
            return 0
        if not args.actor or not args.reason_code or not args.confirm_inventory_sha256:
            raise OperatorError("apply_requires_actor_reason_and_confirmation")
        manifest = json.loads(args.apply_manifest.read_text(encoding="utf-8"))
        result = apply_manifest(
            api=api,
            manifest=manifest,
            confirmation_sha256=args.confirm_inventory_sha256,
            actor=args.actor,
            reason_code=args.reason_code,
            progress=lambda item: print(json.dumps(item, sort_keys=True)),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OperatorError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)[:240]}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
