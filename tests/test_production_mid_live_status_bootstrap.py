from __future__ import annotations

from nico.api import production_bootstrap
from nico.mid_live_status_api import MID_LIVE_STATUS_PATH


def test_production_bootstrap_registers_exactly_one_mid_live_status_route() -> None:
    routes = [
        route
        for route in production_bootstrap.app.routes
        if getattr(route, "path", "") == MID_LIVE_STATUS_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert len(routes) == 1
    assert production_bootstrap.MID_LIVE_STATUS["route_count"] == 1
    assert production_bootstrap.SNAPSHOT_SCANNER_HEARTBEAT["durable_heartbeat"] is True
    assert production_bootstrap.POSTGRES_TIMEOUTS["connect_timeout_seconds"] <= 30
