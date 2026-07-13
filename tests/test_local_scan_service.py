from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import nico.cli as legacy
import nico.local_scan_engine as engine
import nico.local_scan_service as service


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"


def _finding_contract(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "source",
        "category",
        "severity",
        "confidence",
        "title",
        "affected_file",
        "affected_line",
        "masked_evidence",
        "raw_evidence_fingerprint",
        "business_impact",
        "technical_impact",
        "recommended_fix",
        "verification_method",
        "standards_mapping",
        "status",
    )
    return sorted(
        ({key: item.get(key) for key in keys} for item in items),
        key=lambda item: (
            str(item["affected_file"]),
            int(item["affected_line"] or 0),
            str(item["source"]),
            str(item["category"]),
        ),
    )


def test_extracted_scan_text_preserves_legacy_detection_contract() -> None:
    samples = {
        "app.py": (
            "FAKE_API_KEY='FAKE_TEST_ONLY_API_KEY_1234567890'\n"
            "result = eval(user_input)\n"
            "app.run(debug=True)\n"
            "# TODO: add rate limiting\n"
        ),
        "requirements.txt": "flask==0.12\nrequests==2.31.0\n",
        "package.json": '{"dependencies":{"lodash":"4.17.15"}}\n',
        "auth.jsonl": "\n".join(
            [json.dumps({"event": "failed_login"}) for _ in range(6)]
            + [json.dumps({"event": "admin_role_change"})]
        ),
    }

    for path, text in samples.items():
        assert _finding_contract(engine.scan_text(path, text)) == _finding_contract(
            legacy.scan_text(path, text)
        )


def test_extracted_engine_masks_raw_secret_material() -> None:
    raw = "sk-1234567890ABCDEFGHIJKLMNOP"
    findings = engine.scan_text("settings.py", f"token='{raw}'\n")

    assert findings
    rendered = json.dumps(findings)
    assert raw not in rendered
    assert findings[0]["raw_evidence_fingerprint"] == engine.fingerprint(raw)
    assert findings[0]["masked_evidence"] != f"token='{raw}'"


def test_scan_repo_is_confined_to_allowed_root_and_skips_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = tmp_path / "allowed"
    target = allowed / "repo"
    target.mkdir(parents=True)
    (target / "safe.py").write_text("debug=True\n", encoding="utf-8")
    (target / "node_modules").mkdir()
    (target / "node_modules" / "ignored.js").write_text("eval(x)\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("eval(x)\n", encoding="utf-8")
    try:
        (target / "outside-link.py").symlink_to(outside)
    except OSError:
        pass

    monkeypatch.setenv("NICO_ALLOWED_SCAN_ROOT", str(allowed))
    result = engine.scan_repo("repo")

    assert result["target"] == str(target.resolve())
    assert result["files_scanned"] == ["safe.py"]
    assert {item["category"] for item in result["findings"]} == {"debug_mode"}

    with pytest.raises(NotADirectoryError):
        engine.scan_repo(str(tmp_path))
    with pytest.raises(NotADirectoryError):
        engine.scan_repo("../outside")


def test_local_scan_service_preserves_pipeline_order_and_persistence_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeStore:
        def policy(self) -> dict[str, Any]:
            calls.append("policy")
            return {"allowed_actions": ["scan"]}

        def payloads(self, table: str) -> list[dict[str, Any]]:
            calls.append(f"payloads:{table}")
            return []

        def baseline(self) -> dict[str, Any] | None:
            calls.append("baseline")
            return None

        def save_scan(self, _scan: dict[str, Any], kind: str) -> None:
            calls.append(f"save_scan:{kind}")

        def save_drift(self, _scan_id: str, _drift: list[dict[str, Any]]) -> None:
            calls.append("save_drift")

        def save_repairs(self, _repairs: list[dict[str, Any]]) -> None:
            calls.append("save_repairs")

        def save_baseline(self, _baseline: dict[str, Any]) -> None:
            calls.append("save_baseline")

        def save_memory(self, payload: dict[str, Any]) -> None:
            assert payload["type"] == "scan_cycle"
            calls.append("save_memory")

        def audit(self, action: str, detail: dict[str, Any]) -> None:
            assert action == "scan.run"
            assert detail["kind"] == "local"
            calls.append("audit")

    raw_scan = {
        "id": "scan_exact_1",
        "files_scanned": ["app.py"],
        "findings": [{"id": "finding_1", "category": "debug_mode", "severity": "high"}],
    }
    enriched = [{"id": "finding_1", "category": "debug_mode", "severity": "high", "rye": {"score": 72}}]
    baseline = {
        "scan_id": "scan_exact_1",
        "files_scanned_count": 1,
        "finding_count": 1,
        "risk_score": 35,
        "categories": ["debug_mode"],
    }
    repairs = [{"id": "repair_1", "finding_id": "finding_1", "rye_score": 72}]

    monkeypatch.setattr(service, "Store", FakeStore)
    monkeypatch.setattr(service, "decide_action", lambda action, policy: {"allowed": action == "scan", "reason": "allowed"})
    monkeypatch.setattr(service, "scan_repo", lambda target: calls.append(f"scan_repo:{target}") or dict(raw_scan))
    monkeypatch.setattr(service, "apply_rye", lambda findings, memory: calls.append("apply_rye") or list(enriched))
    monkeypatch.setattr(service, "make_baseline", lambda scan: calls.append("make_baseline") or dict(baseline))
    monkeypatch.setattr(service, "detect_drift", lambda base, scan: calls.append("detect_drift") or [])
    monkeypatch.setattr(service, "repairs_for", lambda findings, memory: calls.append("repairs_for") or list(repairs))
    monkeypatch.setattr(service, "generate_reports", lambda: calls.append("generate_reports") or [])
    monkeypatch.setattr(service, "new_id", lambda prefix: f"{prefix}_exact_1")
    monkeypatch.setattr(service, "now", lambda: "2026-07-13T00:00:00+00:00")

    result = service.run_scan("authorized/repository")

    assert result == {
        "scan": {**raw_scan, "findings": enriched},
        "baseline": baseline,
        "drift": [],
        "repairs": repairs,
    }
    assert calls == [
        "policy",
        "scan_repo:authorized/repository",
        "payloads:memory",
        "apply_rye",
        "baseline",
        "make_baseline",
        "detect_drift",
        "repairs_for",
        "save_scan:local",
        "save_drift",
        "save_repairs",
        "save_baseline",
        "save_memory",
        "audit",
        "generate_reports",
    ]


def test_local_scan_service_fails_closed_when_governance_blocks_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStore:
        def policy(self) -> dict[str, Any]:
            return {"kill_switch": True}

    monkeypatch.setattr(service, "Store", FakeStore)
    monkeypatch.setattr(
        service,
        "decide_action",
        lambda _action, _policy: {
            "allowed": False,
            "reason": "kill switch enabled",
            "requires_approval": True,
        },
    )
    monkeypatch.setattr(
        service,
        "scan_repo",
        lambda _target: pytest.fail("blocked scans must not reach repository traversal"),
    )

    with pytest.raises(RuntimeError, match="scan blocked by governance: kill switch enabled"):
        service.run_scan("authorized/repository")


def test_canonical_cli_scan_commands_import_the_extracted_service() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")

    assert "from nico.local_scan_service import (" in source
    assert "run_scan," in source
    assert "scan_drift_demo," in source
    assert "scan_test_lab," in source
    assert "scanner_availability," in source
    assert "from nico.cli import" not in source
