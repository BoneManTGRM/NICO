from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.comprehensive_localized_export_v1 import localized_evidence_package
from nico.comprehensive_same_run_locale_report_v1 import (
    EVIDENCE_PACKAGE_ROUTE, canonical_sha256, install_same_run_locale_report,
)


@pytest.fixture(scope="module")
def source_status():
    from tests.test_v2_premium_report_renderer import _package
    from nico.comprehensive_report_review_integrity_v1 import install_comprehensive_report_review_integrity_v1
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    install_comprehensive_report_review_integrity_v1()
    package = _package("en")
    package["json"]["identity"]["assessment_depth"] = "strategic"
    reports = rebuild_client_artifacts(package)
    canonical = reports["json"]
    reports["report_id"] = "comprehensive_report_localized_export_test"
    reports["canonical_truth_sha256"] = canonical_sha256(canonical)
    return {
        **{key: canonical["identity"][key] for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")},
        "report_language": "en", "terminal": True, "reports": reports,
    }


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_download_contains_every_actual_format_and_manifest(source_status, language):
    before = deepcopy(source_status)
    response = localized_evidence_package(source_status, language)
    assert source_status == before
    assert response.headers["x-nico-artifact-sha256"] == hashlib.sha256(response.body).hexdigest()
    assert response.headers["x-nico-client-delivery-allowed"] == "false"
    assert response.headers["x-nico-approval-status"] == "pending_human_approval"
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        manifest = json.loads(archive.read("evidence-manifest.json"))
        assert manifest["identity"]["run_id"] == source_status["run_id"]
        assert manifest["identity"]["commit_sha"] == source_status["commit_sha"]
        assert manifest["identity"]["report_language"] == language
        assert {entry["artifact_type"] for entry in manifest["artifacts"]} == {
            "canonical_json", "html_report", "markdown_report", "comprehensive_pdf",
            "findings_csv", "evidence_csv", "candidate_register_json", "remediation_backlog_json",
        }
        for entry in manifest["artifacts"]:
            body = archive.read(entry["filename"])
            assert hashlib.sha256(body).hexdigest() == entry["sha256"]
            assert len(body) == entry["size_bytes"]
            if entry["artifact_type"] == "canonical_json":
                canonical = json.loads(body)
                assert canonical["identity"]["report_language"] == language
                assert canonical["identity"]["commit_sha"] == source_status["commit_sha"]
            if language == "en":
                from nico.comprehensive_exact_artifact_hash_binding_v1 import _artifact_bytes
                assert body == _artifact_bytes(source_status["reports"], entry["artifact_type"])
    assert response.headers["x-nico-localized-artifact-requires-new-approval"] == str(language != "en").lower()


@pytest.mark.parametrize("mutation", ["nonterminal", "changed_truth", "changed_html"])
def test_refuses_incomplete_or_corrupt_source(source_status, mutation):
    status = deepcopy(source_status)
    if mutation == "nonterminal":
        status["terminal"] = False
    elif mutation == "changed_truth":
        status["reports"]["canonical_truth_sha256"] = "0" * 64
    else:
        status["reports"]["html"] += "tampered"
    with pytest.raises(ValueError):
        localized_evidence_package(status, "es-MX")


def test_route_is_read_only_and_rejects_invalid_locale(source_status):
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(status_read_only=lambda run_id: source_status)
    install_same_run_locale_report(app)
    assert sum(r.path == EVIDENCE_PACKAGE_ROUTE for r in app.routes) == 1
    install_same_run_locale_report(app)
    assert sum(r.path == EVIDENCE_PACKAGE_ROUTE for r in app.routes) == 1
    client = TestClient(app)
    path = EVIDENCE_PACKAGE_ROUTE.format(run_id=source_status["run_id"], report_language="fr")
    assert client.post(path).status_code == 405
    assert client.get(path).status_code == 422


def test_new_download_requires_auth_and_proof_cannot_post(source_status, monkeypatch):
    from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session, PRODUCTION_PROOF_SCOPE
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "test-only-localized-export-signing-key-over-32-bytes")
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(status_read_only=lambda run_id: source_status)
    install_same_run_locale_report(app)
    install_specialist_access(app)
    client = TestClient(app)
    path = EVIDENCE_PACKAGE_ROUTE.format(run_id=source_status["run_id"], report_language="en")
    assert client.get(path).status_code == 401
    token, _ = issue_specialist_session({"authority": "test"}, scope=PRODUCTION_PROOF_SCOPE, retained_claims={
        "repository": "BoneManTGRM/NICO", "ref": "refs/heads/main", "sha": "a" * 40,
        "workflow_ref": "BoneManTGRM/NICO/.github/workflows/mobile-restart-production-proof.yml@refs/heads/main",
        "run_id": "12345", "run_attempt": "1", "proof_role": "consumer",
    })
    headers = {"x-nico-operator-session": token}
    assert client.post(path, headers=headers).status_code == 403
    assert client.get(path, headers=headers).status_code == 200


@pytest.mark.parametrize("language", ["en", "es-MX"])
@pytest.mark.parametrize("state", ["approved", "rejected"])
def test_exact_source_decision_does_not_approve_regenerated_files(source_status, language, state):
    import base64
    from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition
    status = deepcopy(source_status)
    report = status["reports"]
    canonical = report["json"]
    if state == "approved":
        accepted = build_accepted_report_edition(
            repository=status["repository"], commit_sha=status["commit_sha"], tree_sha="test-tree",
            run_id=status["run_id"], scanner_run_id="test-scanner", evidence_bundle_hash="test-evidence",
            report_language="en", assessment_depth=canonical["identity"]["assessment_depth"],
            artifacts={"markdown": report["markdown"], "html": report["html"],
                       "pdf": base64.b64decode(report["pdf_base64"]), "json": canonical,
                       "evidence_manifest": report["evidence_manifest_json"]},
            reviewer="TEST Reviewer", reviewer_role="Security reviewer", decision="approved",
            decision_reason="TEST ONLY exact artifact acceptance fixture", decided_at="2026-09-09T00:00:00Z",
        )
        status.update(status="approved", human_review_completed=True, client_delivery_allowed=False,
                      delivery_status="pending_authorization", accepted_edition=accepted)
    else:
        status.update(status="rejected", human_review_completed=True, client_delivery_allowed=False,
                      approval_status="rejected", delivery_status="blocked",
                      response_projection={"rejection_review_integrity_valid": True})
    before = deepcopy(status)
    response = localized_evidence_package(status, language)
    assert status == before
    assert response.headers["x-nico-client-delivery-allowed"] == "false"
    if language == "es-MX":
        assert response.headers["x-nico-approval-status"] == "pending_human_approval"
        assert response.headers["x-nico-localized-artifact-requires-new-approval"] == "true"
    else:
        assert response.headers["x-nico-approval-status"] == ("approved_final" if state == "approved" else "rejected")
        with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
            manifest = json.loads(archive.read("evidence-manifest.json"))
            pdf = next(e for e in manifest["artifacts"] if e["artifact_type"] == "comprehensive_pdf")
            assert archive.read(pdf["filename"]) == base64.b64decode(report["pdf_base64"])
