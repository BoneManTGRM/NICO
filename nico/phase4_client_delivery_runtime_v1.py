from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

import nico.comprehensive_api_routes as routes_module
import nico.comprehensive_run_service as service_module
from nico.comprehensive_approved_delivery_v4 import (
    attach_approved_delivery_package,
    validate_approved_delivery_package,
)
from nico.comprehensive_client_delivery_contract_v1 import PRODUCT_NAME

VERSION = "nico.phase4_client_delivery_runtime.v1"
_STATE_KEY = "nico_phase4_client_delivery_runtime"


def install_phase4_client_delivery_runtime_v1(app: FastAPI) -> dict[str, Any]:
    """Upgrade the existing terminal approval/delivery authorities in place.

    No route, controller, report, assessment tier, or parallel product is created.
    The Phase 2 guarded review method resolves the service-module delivery callable
    at action time, and the protected download route resolves its validator at
    request time, so rebinding those two terminal authorities is sufficient.
    """

    existing = getattr(app.state, _STATE_KEY, None)
    if isinstance(existing, Mapping) and existing.get("status") == "installed":
        return {**dict(existing), "status": "already_installed"}

    service_module.attach_approved_delivery_package = attach_approved_delivery_package
    routes_module.validate_approved_delivery_package = validate_approved_delivery_package
    if service_module.attach_approved_delivery_package is not attach_approved_delivery_package:
        raise RuntimeError("phase4_delivery_builder_not_bound")
    if routes_module.validate_approved_delivery_package is not validate_approved_delivery_package:
        raise RuntimeError("phase4_delivery_validator_not_bound")

    status = {
        "artifact_schema": VERSION,
        "status": "installed",
        "one_public_product": PRODUCT_NAME,
        "one_client_report": True,
        "parallel_assessment_pipeline_created": False,
        "report_pipeline_replaced": False,
        "terminal_approved_delivery_builder_upgraded": True,
        "protected_download_validator_upgraded": True,
        "client_project_identity_bound_to_approval": True,
        "reviewer_identity_role_authorization_basis_bound": True,
        "automation_final_approval_rejected": True,
        "exact_artifact_digests_bound": True,
        "candidate_register_and_disposition_digests_bound": True,
        "generator_version_truth_bound_without_overclaiming_deployment": True,
        "immutable_phase4_receipt_in_delivery_archive": True,
        "material_regeneration_invalidates_approval": True,
        "cross_client_project_run_delivery_fails_closed": True,
        "internal_test_package_delivery_fails_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    setattr(app.state, _STATE_KEY, dict(status))
    return status


__all__ = ["VERSION", "install_phase4_client_delivery_runtime_v1"]
