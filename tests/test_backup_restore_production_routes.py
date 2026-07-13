from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from nico.api.production import (
    OPERATIONS_BACKUP_RESTORE,
    REQUIRED_BACKUP_RESTORE_ROUTES,
    REQUIRED_PRODUCTION_ROUTES,
    register_production_routes,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def _route_count(app: FastAPI, method: str, path: str) -> int:
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and method in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def test_production_contract_requires_complete_backup_restore_route_group() -> None:
    assert REQUIRED_BACKUP_RESTORE_ROUTES == {
        ("GET", "/operations/backup-restore"),
        ("POST", "/operations/backup-restore/backup-evidence"),
        ("POST", "/operations/backup-restore/restore-drill"),
    }
    assert REQUIRED_BACKUP_RESTORE_ROUTES <= REQUIRED_PRODUCTION_ROUTES
    assert OPERATIONS_BACKUP_RESTORE["installed"] is True


def test_production_registration_is_idempotent_for_backup_restore_routes() -> None:
    app = FastAPI()
    register_production_routes(app)
    before = len(app.routes)
    register_production_routes(app)

    assert len(app.routes) == before
    for method, path in REQUIRED_BACKUP_RESTORE_ROUTES:
        assert _route_count(app, method, path) == 1


def test_production_source_exports_and_installs_backup_restore_controls() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "install_backup_restore_readiness" in source
    assert "REQUIRED_BACKUP_RESTORE_ROUTES" in source
    assert "OPERATIONS_BACKUP_RESTORE" in source
    assert '_validate_group(existing, REQUIRED_BACKUP_RESTORE_ROUTES, "backup/restore readiness")' in source
    assert "| REQUIRED_BACKUP_RESTORE_ROUTES" in source
    assert '"REQUIRED_BACKUP_RESTORE_ROUTES"' in source
    assert '"OPERATIONS_BACKUP_RESTORE"' in source
