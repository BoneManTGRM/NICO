from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import nico.cli as legacy
from nico.local_store import LocalStore
from nico.local_verification_service import verify_latest, verify_repair_by_id


ROOT = Path(__file__).resolve().parents[1]
CLI_ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"
FIXED_TIME = "2026-07-13T00:00:00+00:00"


def _id_factory(prefix: str) -> str:
    assert prefix == "verify"
    return "verify_exact_1"


def _clock() -> str:
    return FIXED_TIME


def _seed_latest(store: LocalStore, *, raw_secret: bool = False) -> None:
    evidence = "FAKE_TEST_ONLY_SECRET_123456" if raw_secret else "FAKE…3456"
    store.save_scan(
        {
            "id": "scan_exact_1",
            "created_at": FIXED_TIME,
            "target": "authorized/repository",
            "files_scanned": ["app.py"],
            "findings": [
                {
                    "id": "finding_exact_1",
                    "severity": "high",
                    "category": "secret_exposure",
                    "title": "Masked secret evidence",
                    "masked_evidence": evidence,
                }
            ],
        },
        "local",
    )
    store.save_repairs(
        [
            {
                "id": "repair_exact_1",
                "repair_id": "repair_alias_1",
                "finding_id": "finding_exact_1",
                "status": "suggested",
                "exact_issue": "Masked secret evidence",
            }
        ]
    )


def _audit_contract(store: LocalStore) -> list[tuple[str, dict]]:
    return [
        (str(row["action"]), json.loads(str(row["detail"])))
        for row in reversed(store.rows("audit_log"))
    ]


def _repair_status(store: LocalStore, repair_id: str) -> str:
    repair = next(item for item in store.payloads("repairs") if item.get("id") == repair_id)
    return str(repair.get("status") or "")


def test_latest_verification_matches_legacy_result_and_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_store = LocalStore(tmp_path / "legacy.sqlite3")
    extracted_store = LocalStore(tmp_path / "extracted.sqlite3")
    _seed_latest(legacy_store)
    _seed_latest(extracted_store)
    monkeypatch.setattr(legacy, "Store", lambda: legacy_store)
    monkeypatch.setattr(legacy, "new_id", _id_factory)
    monkeypatch.setattr(legacy, "now", _clock)

    legacy_result = legacy.verify_latest()
    extracted_result = verify_latest(
        store=extracted_store,
        id_factory=_id_factory,
        clock=_clock,
    )

    assert extracted_result == legacy_result
    assert extracted_result == {
        "id": "verify_exact_1",
        "created_at": FIXED_TIME,
        "scan_id": "scan_exact_1",
        "repair_id": None,
        "passed": True,
        "status": "verification_observed",
        "checks": [
            "scan_available",
            "findings_masked",
            "governance_enabled",
            "repair_candidates_present",
        ],
        "risk_reduction": "pending_targeted_code_repair",
        "finding_count": 1,
        "repair_count": 1,
        "baseline_update_allowed": False,
    }
    assert extracted_store.payloads("verification") == legacy_store.payloads("verification")
    assert extracted_store.payloads("memory") == legacy_store.payloads("memory")
    assert _audit_contract(extracted_store) == _audit_contract(legacy_store)


def test_exact_repair_alias_resolves_to_canonical_identity_and_remains_pending(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_store = LocalStore(tmp_path / "legacy.sqlite3")
    extracted_store = LocalStore(tmp_path / "extracted.sqlite3")
    _seed_latest(legacy_store)
    _seed_latest(extracted_store)
    monkeypatch.setattr(legacy, "Store", lambda: legacy_store)
    monkeypatch.setattr(legacy, "new_id", _id_factory)
    monkeypatch.setattr(legacy, "now", _clock)

    legacy_result = legacy.verify_repair_by_id("repair_alias_1")
    extracted_result = verify_repair_by_id(
        "repair_alias_1",
        store=extracted_store,
        id_factory=_id_factory,
        clock=_clock,
    )

    assert extracted_result == legacy_result
    assert extracted_result["repair_id"] == "repair_exact_1"
    assert extracted_result["status"] == "verification_pending"
    assert extracted_result["passed"] is True
    assert extracted_result["baseline_update_allowed"] is False
    assert extracted_result["risk_reduction"] == "requires_rescan_after_patch"
    assert _repair_status(extracted_store, "repair_exact_1") == "verification_pending"
    assert _repair_status(legacy_store, "repair_exact_1") == "verification_pending"
    assert extracted_store.payloads("verification") == legacy_store.payloads("verification")
    assert extracted_store.payloads("memory") == legacy_store.payloads("memory")
    assert _audit_contract(extracted_store) == _audit_contract(legacy_store)


def test_missing_repair_fails_closed_without_mutating_existing_repairs(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    _seed_latest(store)
    before = deepcopy(store.payloads("repairs"))

    result = verify_repair_by_id(
        "repair_missing",
        store=store,
        id_factory=_id_factory,
        clock=_clock,
    )

    assert result["repair_id"] is None
    assert result["passed"] is False
    assert result["status"] == "repair_not_found"
    assert result["checks"] == [
        "repair_missing",
        "rescan_required",
        "raw_secret_masking_checked",
    ]
    assert result["baseline_update_allowed"] is False
    assert store.payloads("repairs") == before
    assert _audit_contract(store)[-1][0] == "verification.repair"


def test_raw_secret_evidence_cannot_pass_latest_verification(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    _seed_latest(store, raw_secret=True)

    result = verify_latest(
        store=store,
        id_factory=_id_factory,
        clock=_clock,
    )

    assert result["passed"] is False
    assert "masking_failure" in result["checks"]
    assert result["baseline_update_allowed"] is False
    assert result["risk_reduction"] == "pending_targeted_code_repair"


def test_canonical_cli_no_longer_sources_verification_from_cli_monolith() -> None:
    source = CLI_ENTRYPOINT.read_text(encoding="utf-8")

    assert "from nico.local_verification_service import verify_latest, verify_repair_by_id" in source
    cli_import = source.split("from nico.cli import", 1)[1].splitlines()[0]
    assert "verify_latest" not in cli_import
    assert "verify_repair_by_id" not in cli_import
