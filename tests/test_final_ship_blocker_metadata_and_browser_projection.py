from __future__ import annotations

from pathlib import Path

from nico.comprehensive_api_controller import _project_report, _project_report_manifest
from nico.comprehensive_canonical_report_source_v1 import _attach_engagement_identity
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


def _engagement_metadata() -> dict:
    return build_comprehensive_engagement_metadata(
        client_name="NICO Acceptance Client",
        project_name="NICO Acceptance Project",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "access_method": ["GitHub HTTPS/API - read-only"],
                    "primary_technical_contact": ["NICO Acceptance Contact"],
                    "authorized_scope": [
                        "Full repository at exact assessed SHA - read-only"
                    ],
                }
            }
        },
    )


def test_canonical_identity_preserves_all_supplied_engagement_metadata() -> None:
    metadata = _engagement_metadata()
    identity: dict[str, str] = {}

    _attach_engagement_identity(identity, {"engagement_metadata": metadata})

    assert identity == {
        "customer_name": "NICO Acceptance Client",
        "project_name": "NICO Acceptance Project",
        "primary_technical_contact": "NICO Acceptance Contact",
        "access_method": "GitHub HTTPS/API - read-only",
        "authorized_scope": "Full repository at exact assessed SHA - read-only",
        "engagement_metadata_sha256": metadata["engagement_metadata_sha256"],
    }


def test_canonical_identity_rejects_tampered_engagement_metadata() -> None:
    metadata = _engagement_metadata()
    metadata["client_name"] = "Tampered Client"
    identity: dict[str, str] = {}

    _attach_engagement_identity(identity, {"engagement_metadata": metadata})

    assert identity == {}


def test_canonical_identity_does_not_infer_missing_engagement_metadata() -> None:
    identity: dict[str, str] = {}

    _attach_engagement_identity(
        identity,
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_scope_identifier",
            "project_id": "project_scope_identifier",
        },
    )

    assert identity == {}


def test_browser_terminal_manifest_omits_heavy_artifacts_without_changing_full_api() -> None:
    report = {
        "service_id": "comprehensive",
        "report_id": "report_test",
        "markdown": "# NICO Comprehensive\n",
        "html": "<html><body>NICO</body></html>",
        "pdf_base64": "JVBERi0xLjQK",
        "pdf_filename": "nico.pdf",
        "pdf_sha256": "a" * 64,
        "canonical_truth_sha256": "b" * 64,
        "json": {"identity": {"run_id": "comprun_test"}},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    full = _project_report(report)
    browser = _project_report_manifest(report)

    assert full["markdown"] == report["markdown"]
    assert full["html"] == report["html"]
    assert full["pdf_base64"] == report["pdf_base64"]
    assert full["json"] == report["json"]

    for heavy_field in ("markdown", "html", "pdf_base64", "json"):
        assert heavy_field not in browser
    assert browser["markdown_available"] is True
    assert browser["html_available"] is True
    assert browser["pdf_available"] is True
    assert browser["json_available"] is True
    assert browser["artifact_delivery"] == "on_demand_exact_run"
    assert browser["human_review_required"] is True
    assert browser["client_delivery_allowed"] is False


def test_browser_projection_header_is_wired_end_to_end() -> None:
    requests = (
        ROOT / "apps/web/app/assessment/assessmentRunRequests.ts"
    ).read_text(encoding="utf-8")
    proxy = (
        ROOT / "apps/web/app/api/nico/[...path]/route.ts"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "nico/comprehensive_api_routes.py").read_text(encoding="utf-8")

    assert 'const BROWSER_PROJECTION_HEADER = "X-NICO-Browser-Projection";' in requests
    assert 'const BROWSER_PROJECTION_VALUE = "terminal-manifest-v1";' in requests
    assert 'const BROWSER_PROJECTION_HEADER = "x-nico-browser-projection";' in proxy
    assert 'headers.set("X-NICO-Browser-Projection", BROWSER_PROJECTION_VALUE);' in proxy
    assert '_BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"' in routes
    assert 'request.headers.get("x-nico-browser-projection")' in routes
    assert routes.count("_browser_projection_requested(request)") >= 4
    assert "include_review_artifact_identity=not browser_projection" in routes


def test_exact_run_views_unmount_optional_evidence_editor() -> None:
    workspace = (
        ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"
    ).read_text(encoding="utf-8")
    evidence_form = (
        ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"
    ).read_text(encoding="utf-8")

    assert "disabled={running || hasExactRun}" in workspace
    assert "protectedRunId || result?.run_id" in workspace
    assert "if (disabled) return null;" in evidence_form


def test_compact_mobile_context_uses_three_single_line_controls() -> None:
    source = (
        ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"
    ).read_text(encoding="utf-8")
    mobile_block = source.split("if (!richEditorEnabled) {", 1)[1].split(
        "const activeDefinition =", 1
    )[0]

    assert 'const MOBILE_CLIENT_ENGAGEMENT_FIELDS = ["access_method", "primary_technical_contact", "authorized_scope"] as const;' in source
    assert '<input\n              type="text"' in mobile_block
    assert "<textarea" not in mobile_block
    assert 'data-mobile-client-engagement-context="true"' in mobile_block
