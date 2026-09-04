from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "nico" / "comprehensive_api_routes.py"
PROXY = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
WORKSPACE = (
    ROOT
    / "apps"
    / "web"
    / "app"
    / "operations"
    / "final-review"
    / "FinalReviewWorkspace.tsx"
)
SERVICE = ROOT / "nico" / "comprehensive_run_service.py"
DELIVERY = ROOT / "nico" / "comprehensive_approved_delivery_v1.py"


def test_strategic_review_and_delivery_routes_require_admin_authentication() -> None:
    source = ROUTES.read_text(encoding="utf-8")
    security = (ROOT / "nico" / "admin_security.py").read_text(encoding="utf-8")

    assert "from nico.admin_security import require_comprehensive_operator" in source
    assert "def require_comprehensive_operator(" in security
    assert "admin_allowed, admin_status = require_admin_write(provided_token)" in security
    assert "SARA's service password is deliberately not accepted by ``require_admin_write``" in security
    assert 'x_nico_admin_token: str = Header(default="")' in source
    assert "_authorize_review(x_nico_admin_token)" in source
    assert "strategic_review_admin_authentication_required" in source
    assert (
        '"GET", "/assessment/comprehensive-run/{run_id}/approved-delivery-package"'
        in source
    )
    assert "validate_approved_delivery_package(record, candidate)" in source
    assert 'media_type="application/zip"' in source
    assert '"Cache-Control": "no-store, private, max-age=0"' in source


def test_same_origin_proxy_allows_only_exact_review_routes_and_forwards_secret() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "COMPREHENSIVE_REVIEW" in source
    assert "COMPREHENSIVE_APPROVED_DELIVERY" in source
    assert "COMPREHENSIVE_AUTOMATED_DELIVERY" in source
    assert "protectedReviewRoute(request.method, apiPath)" in source
    assert 'request.headers.get("x-nico-admin-token")' in source
    assert 'headers.set("X-NICO-Admin-Token", adminToken)' in source
    assert "approved-delivery-package" in source
    assert "automated-delivery-package" in source
    assert 'method === "POST" && COMPREHENSIVE_AUTOMATED_DELIVERY.test(path)' in source
    assert '"content-disposition"' in source
    assert '"x-nico-delivery-package-sha256"' in source
    assert '"x-nico-certified-package-sha256"' in source
    assert '"x-nico-authorization-mode"' in source
    assert '"x-nico-human-reviewed"' in source


def test_final_review_requires_memory_only_token_and_downloads_certified_zip() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "runId.trim() && adminToken.trim() && reviewer.trim() && reviewerRole.trim()" in source
    assert '"X-NICO-Admin-Token": adminToken.trim()' in source
    assert "canonicalHeaders(true)" in source
    assert "approved-delivery-package" in source
    assert "Download approved delivery package" in source
    assert "Descargar paquete de entrega aprobado" in source
    assert "bytes[0] !== 0x50 || bytes[1] !== 0x4b" in source
    assert 'new Blob([bytes], {type: "application/zip"})' in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie" not in source


def test_delivery_package_requires_distinct_post_approval_authorization() -> None:
    service = SERVICE.read_text(encoding="utf-8")
    delivery = DELIVERY.read_text(encoding="utf-8")

    assert "apply_comprehensive_review_decision" in service
    assert "def authorize_delivery(" in service
    assert "delivery_authorization = authorize_accepted_edition(" in service
    assert "authorization_record[\"delivery_authorization\"]" in service
    assert "attach_approved_delivery_package(" in service
    approval_method = service.split("def review(", 1)[1].split(
        "def authorize_delivery(", 1
    )[0]
    assert "attach_approved_delivery_package" not in approval_method
    assert 'package_input["accepted_edition"] = deepcopy(dict(manifest))' in delivery
    assert "build_premium_delivery_package(package_input)" in delivery
    assert '"report_regenerated_during_delivery_packaging": False' in delivery
    assert "delivery_authorization_certificate_sha256" in delivery
    assert "approval_requires_new_evidence_bound_report_after_request_more_evidence" in delivery


def test_status_projection_never_embeds_delivery_zip_bytes() -> None:
    source = ROUTES.read_text(encoding="utf-8")
    projection = source.split("def _approved_delivery_projection", 1)[1].split(
        "def _review_projection", 1
    )[0]

    assert "zip_sha256" in projection
    assert "zip_size_bytes" in projection
    assert "certificate" in projection
    assert "zip_base64" not in projection
