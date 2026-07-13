from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

import nico.cli as legacy
import nico.local_scan_service as scan_service
from nico.local_governance_service import decide_action
from nico.local_store import DEFAULT_POLICY, LocalStore


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCAN_SERVICE = ROOT / "nico" / "local_scan_service.py"
GOVERNANCE_SERVICE = ROOT / "nico" / "local_governance_service.py"


@pytest.mark.parametrize(
    ("action", "policy"),
    [
        ("scan", {**DEFAULT_POLICY, "kill_switch": True}),
        ("exploit", deepcopy(DEFAULT_POLICY)),
        ("production_deploy", deepcopy(DEFAULT_POLICY)),
        ("scan", deepcopy(DEFAULT_POLICY)),
        ("unregistered_action", deepcopy(DEFAULT_POLICY)),
    ],
)
def test_governance_decisions_match_legacy_contract_exactly(
    action: str,
    policy: dict[str, Any],
) -> None:
    original = deepcopy(policy)

    assert decide_action(action, policy) == legacy.decide_action(action, policy)
    assert policy == original


def test_default_policy_and_store_output_remain_compatible(tmp_path: Path) -> None:
    extracted = LocalStore(tmp_path / "extracted.sqlite3")
    compatible = legacy.Store(tmp_path / "legacy.sqlite3")

    assert DEFAULT_POLICY == legacy.DEFAULT_POLICY
    assert extracted.policy() == compatible.policy() == DEFAULT_POLICY
    assert decide_action("scan", extracted.policy()) == {
        "allowed": True,
        "reason": "allowed",
        "requires_approval": False,
    }
    assert decide_action("production_deploy", extracted.policy()) == {
        "allowed": False,
        "reason": "human approval required",
        "requires_approval": True,
    }


def test_blocked_scan_uses_exact_database_path_and_stops_before_scan_or_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed_paths: list[Path] = []

    class BlockedStore:
        def __init__(self, path: Path) -> None:
            constructed_paths.append(path)

        def policy(self) -> dict[str, Any]:
            return {**DEFAULT_POLICY, "kill_switch": True}

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("blocked governance must stop before scan and report execution")

    monkeypatch.setattr(scan_service, "LocalStore", BlockedStore)
    monkeypatch.setattr(scan_service, "scan_repo", must_not_run)
    monkeypatch.setattr(scan_service, "generate_reports", must_not_run)

    with pytest.raises(RuntimeError, match="scan blocked by governance: kill switch enabled"):
        scan_service.run_scan("unused-target")

    assert constructed_paths == [scan_service.DB_PATH]


def test_allowed_scan_preserves_store_writes_and_return_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    scan = {
        "id": "scan_exact_1",
        "created_at": "2026-07-13T23:55:00+00:00",
        "findings": [
            {
                "id": "finding_exact_1",
                "category": "debug_mode",
                "severity": "high",
            }
        ],
    }
    scored_findings = [{**scan["findings"][0], "rye": {"score": 72.0}}]
    baseline = {"id": "baseline_exact_1"}
    drift = [{"id": "drift_exact_1", "type": "finding_added"}]
    repairs = [{"id": "repair_exact_1", "finding_id": "finding_exact_1", "rye_score": 72.0}]

    class AllowedStore:
        def __init__(self, path: Path) -> None:
            calls.append(("construct", path))

        def policy(self) -> dict[str, Any]:
            return deepcopy(DEFAULT_POLICY)

        def payloads(self, table: str) -> list[dict[str, Any]]:
            calls.append(("payloads", table))
            return []

        def baseline(self) -> None:
            calls.append(("baseline", None))
            return None

        def save_scan(self, value: dict[str, Any], kind: str) -> None:
            calls.append(("save_scan", (value, kind)))

        def save_drift(self, scan_id: str, value: list[dict[str, Any]]) -> None:
            calls.append(("save_drift", (scan_id, value)))

        def save_repairs(self, value: list[dict[str, Any]]) -> None:
            calls.append(("save_repairs", value))

        def save_baseline(self, value: dict[str, Any]) -> None:
            calls.append(("save_baseline", value))

        def save_memory(self, value: dict[str, Any]) -> None:
            calls.append(("save_memory", value))

        def audit(self, action: str, detail: dict[str, Any]) -> None:
            calls.append(("audit", (action, detail)))

    monkeypatch.setattr(scan_service, "LocalStore", AllowedStore)
    monkeypatch.setattr(scan_service, "scan_repo", lambda target: deepcopy(scan))
    monkeypatch.setattr(scan_service, "apply_rye", lambda findings, memory: deepcopy(scored_findings))
    monkeypatch.setattr(scan_service, "make_baseline", lambda value: deepcopy(baseline))
    monkeypatch.setattr(scan_service, "detect_drift", lambda current, value: deepcopy(drift))
    monkeypatch.setattr(scan_service, "repairs_for", lambda findings, memory: deepcopy(repairs))
    monkeypatch.setattr(scan_service, "new_id", lambda prefix: "mem_exact_1")
    monkeypatch.setattr(scan_service, "now", lambda: "2026-07-13T23:55:01+00:00")
    monkeypatch.setattr(scan_service, "generate_reports", lambda: calls.append(("generate_reports", None)))

    result = scan_service.run_scan("authorized-target", "local")

    assert result == {
        "scan": {**scan, "findings": scored_findings},
        "baseline": baseline,
        "drift": drift,
        "repairs": repairs,
    }
    assert calls[0] == ("construct", scan_service.DB_PATH)
    assert ("save_drift", ("scan_exact_1", drift)) in calls
    assert ("save_repairs", repairs) in calls
    assert ("save_baseline", baseline) in calls
    assert calls[-1] == ("generate_reports", None)


def test_canonical_scan_service_has_no_legacy_cli_dependency() -> None:
    scan_source = LOCAL_SCAN_SERVICE.read_text(encoding="utf-8")
    governance_source = GOVERNANCE_SERVICE.read_text(encoding="utf-8")

    assert "from nico.cli" not in scan_source
    assert "import nico.cli" not in scan_source
    assert "from nico.local_governance_service import decide_action" in scan_source
    assert "from nico.local_store import LocalStore" in scan_source
    assert "from nico.local_runtime_config import DB_PATH" in scan_source
    assert scan_source.count("LocalStore(DB_PATH)") == 2
    assert "from nico.cli" not in governance_source
    assert "unknown action denied by default" in governance_source
