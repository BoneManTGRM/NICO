from __future__ import annotations

from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / "docs" / "BACKUP_RESTORE_VERIFICATION.md"


def test_runbook_documents_complete_operator_route_group() -> None:
    source = DOC.read_text(encoding="utf-8")

    assert "GET /operations/backup-restore" in source
    assert "POST /operations/backup-restore/backup-evidence" in source
    assert "POST /operations/backup-restore/restore-drill" in source


def test_runbook_requires_real_backup_and_isolated_restore_evidence() -> None:
    source = DOC.read_text(encoding="utf-8")

    assert "Provider documentation" in source
    assert "not proof that a current backup exists" in source
    assert "isolated non-production target" in source
    assert "must never target the live production database" in source
    assert "successful backup as proof that restoration works" in source


def test_runbook_discloses_default_freshness_and_configuration() -> None:
    source = DOC.read_text(encoding="utf-8")

    assert "36 hours" in source
    assert "30 days" in source
    assert "7 days" in source
    assert "24 hours" in source
    assert "NICO_BACKUP_MAX_AGE_HOURS" in source
    assert "NICO_RESTORE_DRILL_MAX_AGE_DAYS" in source
    assert "NICO_BACKUP_MIN_RETENTION_DAYS" in source
    assert "NICO_BACKUP_MIN_PITR_HOURS" in source


def test_runbook_prohibits_secrets_and_destructive_actions() -> None:
    source = DOC.read_text(encoding="utf-8")

    for required in [
        "DATABASE_URL",
        "credentials",
        "tokens",
        "provider URLs",
        "archive contents",
        "Do not restore into production as a drill",
        "client delivery",
        "score changes",
        "deployment",
        "rollback",
        "failover",
    ]:
        assert required in source


def test_deployment_truth_does_not_claim_provider_backup_or_restore() -> None:
    source = DOC.read_text(encoding="utf-8")

    assert "Deploying this module does not establish backup protection" in source
    assert "must remain degraded or blocked" in source
    assert "No provider backup or restore operation is claimed" in source
