from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_review_decision_v1 import build_reviewed_edition


WORKSPACE = Path(
    "apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx"
)


class _StaleApprovalService:
    def __init__(self) -> None:
        self.review_kwargs: dict[str, Any] = {}

    def review(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        self.review_kwargs = {"run_id": run_id, **kwargs}
        raise ValueError("stale_review_artifact_identity")

    def authorize_delivery(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        self.review_kwargs = {"run_id": run_id, **kwargs}
        raise ValueError("stale_review_artifact_identity")


def test_review_api_forwards_exact_artifact_identity_and_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    expected_identity = {
        "artifact_schema": "nico.comprehensive_review_artifact_identity.v1",
        "run_id": "comprun-exact-review",
        "revision": 17,
        "report_artifact_digest": "a" * 64,
        "artifact_digests": {"pdf": {"sha256": "b" * 64, "size_bytes": 29}},
    }
    service = _StaleApprovalService()
    app = FastAPI()
    register_comprehensive_api_routes(
        app,
        controller=ComprehensiveApiController(service),  # type: ignore[arg-type]
    )

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun-exact-review/review",
        headers={"X-NICO-Admin-Token": "operator-secret"},
        json={
            "review_authorized": True,
            "authorization_confirmed": True,
            "reviewer": "Authorized Human",
            "reviewer_role": "Security reviewer",
            "decision": "approved",
            "decision_reason": "Reviewed the exact immutable artifacts.",
            "expected_artifact_identity": expected_identity,
        },
    )

    assert service.review_kwargs["expected_artifact_identity"] == expected_identity
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "stale_review_artifact_identity",
        "message": (
            "The report artifact set changed after it was loaded. "
            "Reload and review the current exact artifacts before approving "
            "or authorizing client delivery."
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_review_ui_requires_download_of_the_current_digest_before_approval() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "review_artifact_identity?: JsonRecord" in source
    assert "expected_artifact_identity: reviewArtifactIdentity" in source
    assert 'const [downloadedArtifactDigest, setDownloadedArtifactDigest] = useState("")' in source
    assert "downloadedArtifactDigest !== currentReviewPdfDigest" in source
    assert (
        "disabled={downloadedArtifactDigest !== currentReviewPdfDigest || "
        "!currentReviewPdfDigest}"
    ) in source
    assert 'window.crypto.subtle.digest("SHA-256", buffer)' in source
    assert "reviewArtifactIdentity.artifact_digests" in source

    download_boundary = source[
        source.index("async function downloadReviewPdf") :
        source.index("async function downloadApprovedPackage")
    ]
    assert download_boundary.index("await downloadApprovedPdf(result)") < (
        download_boundary.index("setDownloadedArtifactDigest(verifiedPdfDigest)")
    )


def test_review_ui_separates_approval_from_delivery_and_localizes_safe_errors() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert 'const approvalCompleted = rawStatus === "approved" || runStatus === "approved"' in source
    assert "approvalCompleted && !deliveryAllowed" in source
    assert "/authorize-delivery" in source
    assert "delivery_authorized: true" in source
    assert "authorization_confirmed: true" in source
    assert "expected_artifact_identity: reviewArtifactIdentity" in source
    assert "disabled={loading || approvalCompleted}" in source
    assert 'if (locale === "es-MX") return new Error(`${fallback} (${response.status}).`);' in source


def test_delivery_authorization_api_forwards_exact_identity_and_stale_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    expected_identity = {
        "artifact_schema": "nico.comprehensive_review_artifact_identity.v1",
        "run_id": "comprun-exact-review",
        "revision": 18,
        "report_artifact_digest": "a" * 64,
        "artifact_digests": {"pdf": {"sha256": "b" * 64, "size_bytes": 29}},
    }
    service = _StaleApprovalService()
    app = FastAPI()
    register_comprehensive_api_routes(
        app,
        controller=ComprehensiveApiController(service),  # type: ignore[arg-type]
    )

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun-exact-review/authorize-delivery",
        headers={"X-NICO-Admin-Token": "operator-secret"},
        json={
            "delivery_authorized": True,
            "authorization_confirmed": True,
            "authorizer": "Authorized Human",
            "authorizer_role": "Security reviewer",
            "authorization_reason": "Explicitly authorized exact accepted artifacts.",
            "expected_artifact_identity": expected_identity,
        },
    )

    assert service.review_kwargs["expected_artifact_identity"] == expected_identity
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_review_artifact_identity"


@pytest.mark.parametrize("include_manifest", [False, True])
def test_accepted_edition_preserves_exact_pdf_and_optionally_binds_manifest(
    include_manifest: bool,
) -> None:
    pdf = b"%PDF-1.7\nNICO exact reviewed bytes\n%%EOF\n"
    package: dict[str, Any] = {
        "markdown": "# Exact report",
        "html": "<h1>Exact report</h1>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "json": {"identity": {"run_id": "comprun-exact-review"}},
        "canonical_truth_sha256": "c" * 64,
    }
    manifest = '{"manifest_id":"NICO-MANIFEST-EXACT"}'
    if include_manifest:
        package["evidence_manifest_json"] = manifest
    record = {
        "identity": {
            "repository": "owner/repo",
            "commit_sha": "a" * 40,
            "run_id": "comprun-exact-review",
            "assessment_depth": "comprehensive",
            "report_language": "en",
        },
        "revision": 17,
        "stage_results": {
            "immutable_repository_snapshot": {"snapshot": {"tree_sha": "b" * 40}},
            "dependency_security_static_analysis": {"scan_id": "scan-exact-review"},
            "final_comprehensive_report_generation": {"report_package": package},
        },
    }
    original = deepcopy(record)

    accepted = build_reviewed_edition(
        record,
        reviewer="Authorized Human",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Reviewed the exact immutable artifacts.",
        decided_at="2026-08-28T00:00:00+00:00",
    )

    assert accepted["accepted_edition"] is True
    assert record == original
    assert base64.b64decode(package["pdf_base64"], validate=True) == pdf
    assert accepted["artifact_digests"]["pdf"] == {
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "size_bytes": len(pdf),
    }
    if include_manifest:
        assert accepted["artifact_digests"]["evidence_manifest"] == {
            "sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
            "size_bytes": len(manifest.encode("utf-8")),
        }
    else:
        assert "evidence_manifest" not in accepted["artifact_digests"]
