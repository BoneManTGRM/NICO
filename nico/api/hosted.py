from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware import Middleware

from nico.api.main import app
from nico.approved_delivery_operational_readiness import (
    approved_delivery_operational_readiness,
    reconcile_orphaned_delivery_consumptions,
)
from nico.approved_delivery_package import build_approved_delivery_package
from nico.approved_delivery_storage_policy import delivery_storage_readiness
from nico.full_assessment_api import register_full_assessment_routes
from nico.public_delivery_boundary import PublicDeliveryBoundaryMiddleware, public_delivery_boundary_status

REQUIRED_FULL_ASSESSMENT_ROUTES = {
    ("POST", "/assessment/full-run"),
    ("POST", "/assessment/full-run/{run_id}/status"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/verify"),
    ("POST", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/receipts"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/acknowledgments"),
    ("POST", "/assessment/full-run/approved-delivery/access/{access_id}/revoke"),
    ("POST", "/delivery/approved/inspect"),
    ("POST", "/delivery/approved/redeem"),
    ("POST", "/delivery/approved/acknowledge"),
    ("GET", "/reports/{run_id}/approved-delivery"),
    ("GET", "/reports/{run_id}/approved-delivery/verify"),
    ("GET", "/reports/{run_id}/approved-delivery/receipts"),
    ("GET", "/reports/{run_id}/approved-delivery/acknowledgments"),
}
HOSTED_POLICY_ROUTES = {
    ("GET", "/delivery/storage-readiness"),
    ("GET", "/delivery/boundary-status"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/package"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/readiness"),
    ("POST", "/assessment/full-run/{run_id}/approved-delivery/reconcile"),
}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _protected_delivery_write(request: Request) -> bool:
    if request.method.upper() != "POST":
        return False
    path = request.url.path.rstrip("/") or "/"
    if path in {"/delivery/approved/redeem", "/delivery/approved/acknowledge"}:
        return True
    return path.startswith("/assessment/full-run/") and path.endswith("/approved-delivery/access")


async def _enforce_durable_delivery_storage(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if _protected_delivery_write(request):
        readiness = delivery_storage_readiness()
        if not readiness.get("ready"):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "blocked",
                    "code": "durable_delivery_storage_unavailable",
                    "message": "Hosted client delivery is temporarily unavailable because durable delivery storage is required but not ready.",
                    "storage_readiness": readiness,
                },
                headers={"Cache-Control": "no-store, private, max-age=0"},
            )
    return await call_next(request)


def _delivery_storage_readiness_response() -> dict[str, object]:
    return delivery_storage_readiness()


def _public_delivery_boundary_status_response() -> dict[str, object]:
    return public_delivery_boundary_status()


def _approved_delivery_package_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> Response:
    result = build_approved_delivery_package(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
    )
    if result.get("status") != "complete":
        if result.get("admin_write"):
            status_code = 403
        elif result.get("storage_readiness"):
            status_code = 503
        else:
            status_code = 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "status": "blocked",
                "message": str(result.get("error") or "Approved-delivery package export was blocked."),
            },
        )

    filename = str(result.get("filename") or "nico-approved-delivery-package.zip").replace('"', "")
    exposed = ", ".join(
        [
            "Content-Disposition",
            "X-NICO-Package-SHA256",
            "X-NICO-Manifest-SHA256",
            "X-NICO-Package-Identity-SHA256",
            "X-NICO-Package-Version",
            "X-NICO-Package-File-Count",
        ]
    )
    return Response(
        content=result.get("package_bytes") or b"",
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-NICO-Package-SHA256": str(result.get("package_sha256") or ""),
            "X-NICO-Manifest-SHA256": str(result.get("manifest_sha256") or ""),
            "X-NICO-Package-Identity-SHA256": str(result.get("package_identity_sha256") or ""),
            "X-NICO-Package-Version": str(result.get("package_version") or ""),
            "X-NICO-Package-File-Count": str(result.get("file_count") or 0),
            "Access-Control-Expose-Headers": exposed,
        },
    )


def _approved_delivery_readiness_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, object]:
    result = approved_delivery_operational_readiness(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
    )
    if result.get("admin_write"):
        raise HTTPException(
            status_code=403,
            detail={"status": "blocked", "message": "Admin authentication is required to inspect delivery readiness."},
        )
    return result


def _approved_delivery_reconcile_response(
    run_id: str,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    actor: str = "delivery_operator",
    grace_seconds: int | None = None,
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, object]:
    before = approved_delivery_operational_readiness(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
    )
    if before.get("admin_write"):
        raise HTTPException(
            status_code=403,
            detail={"status": "blocked", "message": "Admin authentication is required to reconcile delivery state."},
        )
    non_repairable = [
        item
        for item in before.get("checks") or []
        if not item.get("passed") and item.get("id") != "download_receipt_reconciliation"
    ]
    if non_repairable or before.get("critical_over_receipting"):
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "message": "Automatic reconciliation is unsafe because non-repairable delivery checks failed.",
                "failed_checks": non_repairable,
            },
        )
    result = reconcile_orphaned_delivery_consumptions(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        admin_token=x_nico_admin_token,
        actor=actor,
        grace_seconds=grace_seconds,
    )
    if result.get("status") == "blocked" and result.get("error"):
        raise HTTPException(
            status_code=409,
            detail={"status": "blocked", "message": str(result.get("error"))},
        )
    return result


def _install_public_delivery_boundary(target: FastAPI) -> None:
    if bool(getattr(target.state, "nico_public_delivery_boundary", False)):
        return
    # Append so an existing CORS middleware remains outermost and can decorate
    # boundary-generated 413/429 responses for approved frontend origins.
    target.user_middleware.append(Middleware(PublicDeliveryBoundaryMiddleware))
    target.middleware_stack = None
    target.state.nico_public_delivery_boundary = True


def register_hosted_extension_routes(target: FastAPI) -> FastAPI:
    """Register the complete hosted Full Assessment surface and delivery policy once."""

    existing = _route_pairs(target)
    present = existing & REQUIRED_FULL_ASSESSMENT_ROUTES
    changed = False
    if present != REQUIRED_FULL_ASSESSMENT_ROUTES:
        if present:
            missing = sorted(REQUIRED_FULL_ASSESSMENT_ROUTES - present)
            raise RuntimeError(f"Partial Full Assessment route registration detected; missing={missing}")
        register_full_assessment_routes(target)
        changed = True

    registered = _route_pairs(target)
    missing = REQUIRED_FULL_ASSESSMENT_ROUTES - registered
    if missing:
        raise RuntimeError(f"Full Assessment route registration incomplete; missing={sorted(missing)}")

    extension_routes = [
        ("/delivery/storage-readiness", _delivery_storage_readiness_response, ["GET"]),
        ("/delivery/boundary-status", _public_delivery_boundary_status_response, ["GET"]),
        ("/assessment/full-run/{run_id}/approved-delivery/package", _approved_delivery_package_response, ["GET"]),
        ("/assessment/full-run/{run_id}/approved-delivery/readiness", _approved_delivery_readiness_response, ["GET"]),
        ("/assessment/full-run/{run_id}/approved-delivery/reconcile", _approved_delivery_reconcile_response, ["POST"]),
    ]
    registered = _route_pairs(target)
    for path, endpoint, methods in extension_routes:
        pair = (methods[0], path)
        if pair not in registered:
            target.add_api_route(path, endpoint, methods=methods, tags=["approved-delivery"])
            changed = True
            registered.add(pair)

    if not bool(getattr(target.state, "nico_durable_delivery_middleware", False)):
        target.middleware("http")(_enforce_durable_delivery_storage)
        target.state.nico_durable_delivery_middleware = True
    _install_public_delivery_boundary(target)

    registered = _route_pairs(target)
    policy_missing = HOSTED_POLICY_ROUTES - registered
    if policy_missing:
        raise RuntimeError(f"Hosted delivery policy route registration incomplete; missing={sorted(policy_missing)}")
    if changed:
        target.openapi_schema = None
    return target


register_hosted_extension_routes(app)

__all__ = [
    "app",
    "register_hosted_extension_routes",
    "REQUIRED_FULL_ASSESSMENT_ROUTES",
    "HOSTED_POLICY_ROUTES",
]
