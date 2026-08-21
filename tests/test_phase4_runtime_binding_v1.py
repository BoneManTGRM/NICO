from __future__ import annotations

from fastapi import FastAPI

import nico.comprehensive_api_routes as routes_module
import nico.comprehensive_run_service as service_module
from nico.comprehensive_approved_delivery_v4 import (
    attach_approved_delivery_package,
    validate_approved_delivery_package,
)
from nico.phase4_client_delivery_runtime_v1 import install_phase4_client_delivery_runtime_v1


def test_phase4_runtime_upgrades_existing_terminal_authorities_without_routes_or_parallel_report() -> None:
    app = FastAPI()
    before_routes = list(app.routes)
    status = install_phase4_client_delivery_runtime_v1(app)
    assert service_module.attach_approved_delivery_package is attach_approved_delivery_package
    assert routes_module.validate_approved_delivery_package is validate_approved_delivery_package
    assert list(app.routes) == before_routes
    assert status["one_public_product"] == "NICO Comprehensive"
    assert status["one_client_report"] is True
    assert status["parallel_assessment_pipeline_created"] is False
    assert status["report_pipeline_replaced"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False


def test_phase4_runtime_install_is_idempotent() -> None:
    app = FastAPI()
    first = install_phase4_client_delivery_runtime_v1(app)
    second = install_phase4_client_delivery_runtime_v1(app)
    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
