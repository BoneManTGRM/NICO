from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FakeStore:
    payload: dict[str, Any]

    def status(self) -> dict[str, Any]:
        return dict(self.payload)


def test_assessment_memory_is_writable_but_not_a_verified_record() -> None:
    from nico.assessment_persistence_truth_patch import _truthful_persistence_metadata

    value = _truthful_persistence_metadata(
        FakeStore(
            {
                "adapter": "memory",
                "persistence_available": False,
                "persistence_note": "In-memory fallback.",
            }
        )
    )

    assert value["writable"] is True
    assert value["recorded"] is False
    assert value["durable"] is False
    assert value["durability_verified"] is False
    assert value["survives_container_replacement_verified"] is False


def test_assessment_unverified_sqlite_does_not_present_as_recorded() -> None:
    from nico.assessment_persistence_truth_patch import _truthful_persistence_metadata

    value = _truthful_persistence_metadata(
        FakeStore(
            {
                "adapter": "sqlite",
                "persistence_available": True,
                "durability_verified": False,
            }
        )
    )

    assert value["writable"] is True
    assert value["recorded"] is False
    assert value["durable"] is False
    assert value["warning"]


def test_assessment_postgres_is_a_verified_durable_record() -> None:
    from nico.assessment_persistence_truth_patch import _truthful_persistence_metadata

    value = _truthful_persistence_metadata(
        FakeStore(
            {
                "adapter": "postgres",
                "persistence_available": True,
            }
        )
    )

    assert value["writable"] is True
    assert value["recorded"] is True
    assert value["durable"] is True
    assert value["durability_verified"] is True
    assert value["survives_container_replacement_verified"] is True


def test_express_memory_is_not_reported_as_a_durable_record(monkeypatch) -> None:
    from nico import express_async_api, storage

    monkeypatch.setattr(
        storage,
        "STORE",
        FakeStore(
            {
                "adapter": "memory",
                "persistence_available": False,
                "persistence_note": "In-memory fallback.",
            }
        ),
    )

    value = express_async_api._persistence()

    assert value["writable"] is True
    assert value["recorded"] is False
    assert value["durable"] is False
    assert value["durability_verified"] is False


def test_express_postgres_is_reported_as_verified_durable(monkeypatch) -> None:
    from nico import express_async_api, storage

    monkeypatch.setattr(
        storage,
        "STORE",
        FakeStore(
            {
                "adapter": "postgres",
                "persistence_available": True,
            }
        ),
    )

    value = express_async_api._persistence()

    assert value["writable"] is True
    assert value["recorded"] is True
    assert value["durable"] is True
    assert value["durability_verified"] is True
    assert value["survives_container_replacement_verified"] is True
