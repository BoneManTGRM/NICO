from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import nico.cli as legacy
from nico.local_memory_service import memory_summary
from nico.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
CLI_ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"


def _seed(store: LocalStore) -> None:
    store.save_scan(
        {
            "id": "scan_exact_1",
            "created_at": "2026-07-13T00:00:00+00:00",
            "target": "authorized/repository",
            "files_scanned": ["app.py", "worker.py"],
            "findings": [
                {
                    "id": "finding_exact_1",
                    "severity": "high",
                    "category": "unsafe_eval",
                    "affected_file": "app.py",
                },
                {
                    "id": "finding_exact_2",
                    "severity": "medium",
                    "category": "unsafe_eval",
                    "affected_file": "worker.py",
                },
            ],
        },
        "local",
    )
    store.save_memory(
        {
            "id": "memory_exact_1",
            "type": "scan_cycle",
            "created_at": "2026-07-13T00:01:00+00:00",
            "scan_id": "scan_exact_1",
        }
    )
    store.save_memory(
        {
            "id": "memory_exact_2",
            "type": "verification",
            "created_at": "2026-07-13T00:02:00+00:00",
            "result": {
                "status": "verification_pending",
                "repair_id": "repair_exact_1",
                "baseline_update_allowed": False,
            },
        }
    )


def test_memory_summary_matches_legacy_order_and_analysis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_store = LocalStore(tmp_path / "legacy.sqlite3")
    extracted_store = LocalStore(tmp_path / "extracted.sqlite3")
    _seed(legacy_store)
    _seed(extracted_store)
    monkeypatch.setattr(legacy, "Store", lambda: legacy_store)

    legacy_result = legacy.memory_summary()
    extracted_result = memory_summary(store=extracted_store)

    assert extracted_result == legacy_result
    assert [item["id"] for item in extracted_result["items"]] == [
        "memory_exact_2",
        "memory_exact_1",
    ]
    assert extracted_result["analysis"]["recurring_categories"] == ["unsafe_eval"]
    assert extracted_result["analysis"]["fragile_modules"] == ["app.py", "worker.py"]
    assert extracted_result["analysis"]["risk_reduction_history"] == [
        extracted_result["items"][0]
    ]


def test_memory_summary_is_read_only(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    _seed(store)
    memory_before = deepcopy(store.payloads("memory"))
    findings_before = deepcopy(store.payloads("findings"))

    first = memory_summary(store=store)
    second = memory_summary(store=store)

    assert first == second
    assert store.payloads("memory") == memory_before
    assert store.payloads("findings") == findings_before
    assert store.rows("audit_log") == []


def test_empty_memory_remains_explicit_without_fabricated_history(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")

    result = memory_summary(store=store)

    assert result["items"] == []
    assert result["analysis"] == {
        "recurring_categories": [],
        "fragile_modules": [],
        "false_positive_tracking": "available via repair status false_positive",
        "risk_reduction_history": [],
        "memory_notes": ["No recurring drift pattern has enough evidence yet."],
    }


def test_canonical_cli_memory_has_no_direct_legacy_cli_dependency() -> None:
    source = CLI_ENTRYPOINT.read_text(encoding="utf-8")

    assert "from nico.local_memory_service import memory_summary" in source
    assert "from nico.cli import" not in source
