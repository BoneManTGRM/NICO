from __future__ import annotations

from pathlib import Path

import pytest

from nico.phase9_client_delivery_v1 import (
    DeliveryAuthorizationError,
    artifact_inventory,
    authorize_exact_package,
    build_pending_delivery_record,
    invalidate_if_package_changed,
)


def _package(tmp_path: Path) -> dict[str, Path]:
    files = {
        "report_en_pdf": tmp_path / "report-en.pdf",
        "report_es_pdf": tmp_path / "report-es.pdf",
        "canonical_json": tmp_path / "canonical.json",
        "findings_csv": tmp_path / "findings.csv",
        "release_manifest": tmp_path / "release.json",
    }
    for label, path in files.items():
        path.write_bytes((label + "\n").encode())
    return files


def test_exact_package_can_be_approved_and_changed_package_is_invalidated(tmp_path: Path) -> None:
    files = _package(tmp_path)
    record = build_pending_delivery_record(
        repository="BoneManTGRM/NICO",
        revision="a" * 40,
        run_id="phase9-proof",
        artifacts=files,
        required_labels=list(files),
        limitations=["Human visual review required", "Static-analysis scope retained"],
    )
    assert record["client_delivery_allowed"] is False

    approved = authorize_exact_package(
        record,
        reviewer="Authorized Reviewer",
        reviewer_role="Technical Approver",
        approved_at="2026-07-28T23:00:00Z",
        observed_package_fingerprint=record["package_fingerprint"],
        observed_revision="a" * 40,
        accepted_limitations=record["limitations"],
    )
    assert approved["client_delivery_allowed"] is True

    files["report_en_pdf"].write_bytes(b"changed\n")
    invalidated = invalidate_if_package_changed(approved, artifact_inventory(files))
    assert invalidated["client_delivery_allowed"] is False
    assert invalidated["approval"]["status"] == "invalidated"


def test_wrong_hash_revision_or_limitations_fail_closed(tmp_path: Path) -> None:
    files = _package(tmp_path)
    record = build_pending_delivery_record(
        repository="BoneManTGRM/NICO",
        revision="b" * 40,
        run_id="phase9-proof",
        artifacts=files,
        required_labels=list(files),
        limitations=["Open limitation"],
    )
    common = dict(
        record=record,
        reviewer="Reviewer",
        reviewer_role="Approver",
        approved_at="2026-07-28T23:00:00Z",
        accepted_limitations=["Open limitation"],
    )
    with pytest.raises(DeliveryAuthorizationError):
        authorize_exact_package(
            **common,
            observed_package_fingerprint="wrong",
            observed_revision="b" * 40,
        )
    with pytest.raises(DeliveryAuthorizationError):
        authorize_exact_package(
            **common,
            observed_package_fingerprint=record["package_fingerprint"],
            observed_revision="c" * 40,
        )
    with pytest.raises(DeliveryAuthorizationError):
        authorize_exact_package(
            **{**common, "accepted_limitations": []},
            observed_package_fingerprint=record["package_fingerprint"],
            observed_revision="b" * 40,
        )
