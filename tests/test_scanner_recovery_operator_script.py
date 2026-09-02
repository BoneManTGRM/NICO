from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconcile_scanner_recovery",
    ROOT / "scripts/reconcile_scanner_recovery.py",
)
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def _inventory(*scan_ids: str) -> dict:
    return {
        "status": "attention_required" if scan_ids else "clear",
        "recovery_required": [
            {
                "scan_id": scan_id,
                "run_id": f"run-{scan_id}",
                "repository": f"private-owner/{scan_id}",
                "status": "recovery_required",
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:10:00Z",
                "recovery": {"reason": "stale_process_local_execution", "attempt": 1},
            }
            for scan_id in scan_ids
        ],
    }


class FakeApi:
    def __init__(self, inventory: dict) -> None:
        self.current = inventory
        self.closed: list[tuple[str, str, str]] = []

    def inventory(self, *, refresh: bool = True) -> dict:
        return json.loads(json.dumps(self.current))

    def close(self, scan_id: str, *, actor: str, reason_code: str) -> dict:
        self.closed.append((scan_id, actor, reason_code))
        self.current["recovery_required"] = [
            item for item in self.current["recovery_required"] if item["scan_id"] != scan_id
        ]
        return {"status": "cancelled", "evidence_retained": True}


def _review(manifest: dict, *, actor: str, reason: str) -> dict:
    reviewed = json.loads(json.dumps(manifest))
    reviewed["review"] = {
        "reviewed": True,
        "reviewed_by": actor,
        "reason_code": reason,
    }
    return reviewed


def test_manifest_is_deterministic_redacted_and_review_locked() -> None:
    first = operator.build_manifest(_inventory("scan-b", "scan-a"))
    second = operator.build_manifest(_inventory("scan-a", "scan-b"))

    assert first["inventory_sha256"] == second["inventory_sha256"]
    assert [item["scan_id"] for item in first["items"]] == ["scan-a", "scan-b"]
    rendered = json.dumps(first)
    assert "private-owner" not in rendered
    assert first["review"]["reviewed"] is False
    assert len(first["items"][0]["repository_sha256"]) == 64


def test_apply_closes_only_exact_reviewed_unchanged_inventory() -> None:
    api = FakeApi(_inventory("scan-a", "scan-b"))
    base = operator.build_manifest(api.inventory())
    manifest = _review(
        base,
        actor="Cody owner review",
        reason="superseded_by_terminal_assessment",
    )

    result = operator.apply_manifest(
        api=api,
        manifest=manifest,
        confirmation_sha256=base["inventory_sha256"],
        actor="Cody owner review",
        reason_code="superseded_by_terminal_assessment",
    )

    assert result == {
        "status": "complete",
        "closed": 2,
        "requested": 2,
        "remaining_recovery_required": 0,
        "reason_code": "superseded_by_terminal_assessment",
        "evidence_retained": True,
    }
    assert [item[0] for item in api.closed] == ["scan-a", "scan-b"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda manifest, api: manifest["review"].update(reviewed=False), "recovery_manifest_not_reviewed"),
        (lambda manifest, api: api.current["recovery_required"].append(_inventory("scan-c")["recovery_required"][0]), "recovery_inventory_changed"),
        (lambda manifest, api: manifest["review"].update(reviewed_by="someone else"), "recovery_manifest_actor_mismatch"),
        (lambda manifest, api: manifest["review"].update(reason_code="no_longer_required"), "recovery_manifest_reason_mismatch"),
    ],
)
def test_apply_fails_closed_when_review_or_live_inventory_changes(mutate, expected: str) -> None:
    api = FakeApi(_inventory("scan-a"))
    base = operator.build_manifest(api.inventory())
    manifest = _review(
        base,
        actor="Cody owner review",
        reason="superseded_by_terminal_assessment",
    )
    mutate(manifest, api)

    with pytest.raises(operator.OperatorError, match=expected):
        operator.apply_manifest(
            api=api,
            manifest=manifest,
            confirmation_sha256=base["inventory_sha256"],
            actor="Cody owner review",
            reason_code="superseded_by_terminal_assessment",
        )

    assert api.closed == []


def test_api_rejects_non_https_credentials_and_never_puts_token_in_url(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(operator.OperatorError, match="must_be_https"):
        operator.RecoveryApi(base_url="http://nico.example", admin_token="secret")
    with pytest.raises(operator.OperatorError, match="must_be_https"):
        operator.RecoveryApi(base_url="https://user:secret@nico.example", admin_token="secret")

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def read() -> bytes:
            return b'{"recovery_required": []}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["token"] = request.headers["X-nico-admin-token"]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(operator.urllib.request, "urlopen", fake_urlopen)
    api = operator.RecoveryApi(base_url="https://nico.example", admin_token="secret", timeout_seconds=20)
    api.inventory()

    assert captured["url"] == "https://nico.example/operations/recovery?refresh=true&limit=500"
    assert "secret" not in captured["url"]
    assert captured["token"] == "secret"
    assert captured["timeout"] == 20


def test_manifest_file_is_private_and_apply_requires_explicit_fields(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    operator._write_manifest(path, operator.build_manifest(_inventory("scan-a")))

    assert path.stat().st_mode & 0o777 == 0o600
    assert operator.main(["--api-url", "https://nico.example"]) == 2
