from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nico.provider_credential_rotation import (
    CredentialRotationError,
    CredentialRotationLedger,
    CredentialRotationPolicy,
    rotation_due,
)


def _ledger(path: Path) -> CredentialRotationLedger:
    ledger = CredentialRotationLedger(lambda: sqlite3.connect(path), dialect="sqlite")
    ledger.ensure_schema()
    return ledger


def test_rotation_requires_dual_control_and_never_accepts_raw_secret_field(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "rotation.db")
    policy = CredentialRotationPolicy(require_dual_control=True)

    with pytest.raises(CredentialRotationError, match="dual_control"):
        ledger.activate(
            provider="gitlab",
            key_id="gitlab-prod",
            version="v1",
            secret_reference="NICO_GITLAB_TOKEN_V1",
            activated_by="same-user",
            approved_by="same-user",
            policy=policy,
            activated_at="2026-07-21T00:00:00Z",
            expires_at="2026-08-20T00:00:00Z",
        )

    with pytest.raises(CredentialRotationError, match="secret_reference_invalid"):
        ledger.activate(
            provider="gitlab",
            key_id="gitlab-prod",
            version="v1",
            secret_reference="raw-secret-value!",
            activated_by="operator",
            approved_by="approver",
            policy=policy,
            activated_at="2026-07-21T00:00:00Z",
            expires_at="2026-08-20T00:00:00Z",
        )


def test_activation_rotation_due_and_retirement_are_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "rotation.db"
    ledger = _ledger(path)
    policy = CredentialRotationPolicy(max_age_days=90, maximum_overlap_hours=24)
    record = ledger.activate(
        provider="azure_devops",
        key_id="azure-prod",
        version="v1",
        secret_reference="NICO_AZURE_TOKEN_V1",
        activated_by="operator",
        approved_by="security-approver",
        policy=policy,
        activated_at="2026-07-21T00:00:00Z",
        expires_at="2026-08-20T00:00:00Z",
    )

    assert record.status == "active"
    assert record.record_sha256.startswith("sha256:")
    assert rotation_due(
        record,
        policy=policy,
        now=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
    ) is True

    restarted = _ledger(path)
    active = restarted.active(
        "azure_devops",
        "azure-prod",
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert active is not None
    assert active.version == "v1"

    retired = restarted.retire(
        provider="azure_devops",
        key_id="azure-prod",
        version="v1",
        retired_by="security-approver",
        retired_at="2026-08-19T13:00:00Z",
    )
    assert retired.status == "retired"
    assert restarted.active(
        "azure_devops",
        "azure-prod",
        now=datetime(2026, 8, 19, 14, tzinfo=timezone.utc),
    ) is None


def test_new_version_records_predecessor_without_secret_material(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "predecessor.db")
    policy = CredentialRotationPolicy(max_age_days=90)
    first = ledger.activate(
        provider="bitbucket",
        key_id="bitbucket-prod",
        version="v1",
        secret_reference="NICO_BITBUCKET_TOKEN_V1",
        activated_by="operator",
        approved_by="approver",
        policy=policy,
        activated_at="2026-07-21T00:00:00Z",
        expires_at="2026-09-01T00:00:00Z",
    )
    second = ledger.activate(
        provider="bitbucket",
        key_id="bitbucket-prod",
        version="v2",
        secret_reference="NICO_BITBUCKET_TOKEN_V2",
        activated_by="operator",
        approved_by="approver",
        policy=policy,
        activated_at="2026-08-31T12:00:00Z",
        expires_at="2026-10-01T00:00:00Z",
    )

    assert first.predecessor_version == ""
    assert second.predecessor_version == "v1"
    rendered = str(ledger.list_versions("bitbucket", "bitbucket-prod"))
    assert "raw-secret" not in rendered
    assert "NICO_BITBUCKET_TOKEN_V2" in rendered


def test_max_age_is_enforced(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "age.db")
    with pytest.raises(CredentialRotationError, match="max_age_exceeded"):
        ledger.activate(
            provider="gitlab",
            key_id="gitlab-prod",
            version="v1",
            secret_reference="NICO_GITLAB_TOKEN_V1",
            activated_by="operator",
            approved_by="approver",
            policy=CredentialRotationPolicy(max_age_days=30),
            activated_at="2026-07-01T00:00:00Z",
            expires_at="2026-09-01T00:00:00Z",
        )
