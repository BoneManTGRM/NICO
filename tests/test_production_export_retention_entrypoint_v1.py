"""Isolated HTTP controls through the actual Spanish release acceptance function.

Synthetic package construction is fixture setup only. The collector must retrieve
the resulting bytes over its production-route HTTP transport, never regenerate them.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import io
import zipfile
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import httpx
import pytest

from nico.comprehensive_exact_artifact_hash_binding_v1 import _artifact_bytes
from tests.test_v2_premium_report_renderer import _package

ROOT = Path(__file__).resolve().parents[1]
RUN = "comprun_export_retention"
SHA = "a" * 40
REPORT = "NICO-REPORT-SYNTHETIC-EXPORT-RETENTION"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def acceptance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    try:
        import playwright.sync_api  # noqa: F401
    except ModuleNotFoundError:
        browser_stub = ModuleType("playwright")
        sync_stub = ModuleType("playwright.sync_api")
        sync_stub.Browser = object
        sync_stub.Page = object
        sync_stub.sync_playwright = lambda: pytest.fail("isolated export test cannot launch browser")
        browser_stub.sync_api = sync_stub
        monkeypatch.setitem(sys.modules, "playwright", browser_stub)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_stub)
    proof = importlib.import_module("spanish_comprehensive_live_acceptance_v3")
    retention = importlib.import_module("comprehensive_production_export_retention_v1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(proof.ENGAGEMENT_PROOF_FIXTURE_ENV, "supplied")
    package = _package("es-MX")
    package["report_id"] = REPORT
    package["json"]["identity"].update(
        run_id=RUN, commit_sha=SHA, report_language="es-MX",
        customer_name=proof.PROOF_CLIENT_NAME, project_name=proof.PROOF_PROJECT_NAME,
    )
    metadata = {**proof._expected_engagement_metadata(),
                "repository_inference_prohibited": True, "directly_scored": False}
    package["json"]["engagement_metadata"] = deepcopy(metadata)
    from nico.comprehensive_report_review_integrity_v1 import install_comprehensive_report_review_integrity_v1
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    install_comprehensive_report_review_integrity_v1()
    package = rebuild_client_artifacts(package)
    package["report_id"] = REPORT
    canonical = package["json"]
    from nico.comprehensive_same_run_locale_report_v1 import _render_target
    english = _render_target(canonical, "en")
    localized_packages = {"es-MX": package, "en": english}
    # The API's canonical truth digest uses stable object serialization; the
    # detached manifest separately binds the stored canonical_json byte stream.
    from comprehensive_production_run_handoff_v1 import canonical_json_sha256
    package["canonical_truth_sha256"] = canonical_json_sha256(canonical)
    digest = package["canonical_truth_sha256"]
    lifecycle = {
        "human_review_required": True, "human_review_completed": False,
        "client_delivery_allowed": False, "approval_status": "pending_human_approval",
        "delivery_status": "blocked",
    }
    full = {
        "run_id": RUN, "commit_sha": SHA, "status": "review_required",
        "terminal": True, "revision": 7, "integrity_sha256": "b" * 64,
        "current_stage": "report", "engagement_metadata": deepcopy(metadata),
        **lifecycle,
        "record": {**lifecycle, "revision": 7, "integrity_sha256": "b" * 64,
                   "current_stage": "report", "engagement_metadata": deepcopy(metadata)},
        "reports": package,
    }
    projected = deepcopy(full)
    projected["reports"] = {
        "report_id": REPORT, "canonical_truth_sha256": digest,
        "response_bounded": True, "artifact_delivery": "on_demand_exact_run",
        "pdf_available": True, "markdown_available": True,
    }
    route_root = f"/api/nico/assessment/comprehensive-run/{RUN}"
    requests: list[str] = []
    control = {"kind": None}
    headers = {
        "x-nico-run-id": RUN, "x-nico-commit-sha": SHA,
        "x-nico-report-id": REPORT, "x-nico-report-language": "es-MX",
        "x-nico-canonical-truth-sha256": digest,
        "x-nico-assessment-rerun": "false", "x-nico-human-review-required": "true",
        "x-nico-human-review-completed": "false", "x-nico-client-delivery-allowed": "false",
        "x-nico-approval-status": "pending_human_approval",
        "x-nico-delivery-status": "blocked_pending_human_approval",
        "set-cookie": "synthetic-secret-must-not-be-retained",
    }
    locale_lifecycle = {
        **lifecycle, "delivery_status": "blocked_pending_human_approval",
        "human_review_status": "pending", "client_delivery_status": "blocked",
    }

    def response(path: str) -> httpx.Response:
        requests.append(path)
        current_headers = dict(headers)
        suffix = path.removeprefix(route_root)
        if suffix == "":
            value = deepcopy(full)
            if control["kind"] == "wrong_run_family":
                value["run_id"] = "comprun_wrong"
            elif control["kind"] == "wrong_revision":
                value["revision"] = 8
            elif control["kind"] == "missing_manifest":
                del value["reports"]["evidence_manifest_json"]
            elif control["kind"] == "corrupt_manifest":
                value["reports"]["evidence_manifest_json"] += " "
            elif control["kind"] == "corrupt_retained_html":
                value["reports"]["html"] += "forged"
            return httpx.Response(200, json=value, headers=current_headers)
        if suffix == "/report/json":
            # The API's transport serialization legitimately differs from the
            # stable canonical digest and exact stored canonical_json string.
            body = json.dumps(canonical, ensure_ascii=False, indent=1).encode()
            return httpx.Response(200, content=body, headers=current_headers)
        if suffix in ("/report/markdown", "/report/html", "/report/pdf"):
            format_type = {"markdown": "markdown_report", "html": "html_report", "pdf": "comprehensive_pdf"}
            format_name = suffix.rsplit("/", 1)[-1]
            body = _artifact_bytes(package, format_type[format_name])
            current_headers["x-nico-artifact-sha256"] = sha(body)
            if format_name == "html" and control["kind"] == "corrupt_download":
                body += b"changed"
            elif format_name == "html" and control["kind"] == "rehashed_wrong_download":
                body += b"changed"
                current_headers["x-nico-artifact-sha256"] = sha(body)
            elif format_name == "markdown" and control["kind"] == "wrong_run_header":
                current_headers["x-nico-run-id"] = "comprun_wrong"
            elif format_name == "pdf" and control["kind"] == "failed_applicable_export":
                return httpx.Response(503, content=b"unavailable", headers=current_headers)
            return httpx.Response(200, content=body, headers=current_headers)
        if suffix.startswith("/localized-report/"):
            locale = suffix.split("/")[2]
            current_headers["x-nico-report-language"] = locale
            if suffix.endswith("/evidence-package"):
                from nico.comprehensive_retained_report_export_v1 import retained_report_zip
                body = retained_report_zip(localized_packages[locale])
                if control["kind"] == "corrupt_zip_member":
                    source_zip = zipfile.ZipFile(io.BytesIO(body))
                    output = io.BytesIO()
                    with zipfile.ZipFile(output, "w") as target:
                        for name in source_zip.namelist():
                            data = source_zip.read(name)
                            if name.endswith(".html"):
                                data += b"tampered"
                            target.writestr(name, data)
                    body = output.getvalue()
                if control["kind"] == "invented_manifest_approval":
                    source_zip = zipfile.ZipFile(io.BytesIO(body))
                    members = {name: source_zip.read(name) for name in source_zip.namelist()}
                    forged = json.loads(members["evidence-manifest.json"])
                    forged["approval"]["decision"] = "approved"
                    members["evidence-manifest.json"] = json.dumps(forged).encode()
                    identity = json.loads(members["artifact-identity.json"])
                    identity["evidence_manifest_sha256"] = sha(members["evidence-manifest.json"])
                    members["artifact-identity.json"] = json.dumps(identity).encode()
                    output = io.BytesIO()
                    with zipfile.ZipFile(output, "w") as target:
                        for name, data in members.items():
                            target.writestr(name, data)
                    body = output.getvalue()
                current_headers["x-nico-artifact-sha256"] = sha(body)
                if control["kind"] == "wrong_locale_zip":
                    current_headers["x-nico-report-language"] = "fr"
                if control["kind"] == "invented_zip_approval":
                    current_headers["x-nico-client-delivery-allowed"] = "true"
                return httpx.Response(200, content=body, headers=current_headers)
            if suffix.endswith("/pdf"):
                body = _artifact_bytes(localized_packages[locale], "comprehensive_pdf")
                current_headers["x-nico-artifact-sha256"] = sha(body)
                if control["kind"] == "wrong_source_localized_pdf":
                    current_headers["x-nico-commit-sha"] = "c" * 40
                return httpx.Response(200, content=body, headers=current_headers)
            markdown = localized_packages[locale]["markdown"]
            value = {
                "run_id": RUN, "commit_sha": SHA, "repository": canonical["identity"]["repository"],
                "evidence_ledger_id": canonical["identity"]["evidence_ledger_id"],
                "source_report_id": REPORT, "source_report_language": "es-MX",
                "report_language": locale, "canonical_truth_sha256": digest,
                "source_integrity_sha256": full["integrity_sha256"],
                "same_canonical_run": True, "assessment_rerun": False,
                "canonical_truth_preserved": True, "approval_state_mutated": False,
                "delivery_state_mutated": False,
                "artifact_scope": "retained-canonical-artifact" if locale == "es-MX" else "client-facing-same-run-projection",
                **locale_lifecycle,
                "canonical_run_lifecycle": dict(locale_lifecycle),
                "localized_artifact_lifecycle": dict(locale_lifecycle),
                "report": {
                    "report_id": REPORT, "presentation_language": locale,
                    "canonical_truth_sha256": digest, "markdown": markdown,
                    "markdown_sha256": sha(markdown.encode()), **locale_lifecycle,
                },
            }
            if locale == "en" and control["kind"] == "localized_markdown_hash":
                value["report"]["markdown_sha256"] = "0" * 64
            elif locale == "en" and control["kind"] == "invented_approval":
                value["report"]["human_review_completed"] = True
            return httpx.Response(200, json=value, headers=current_headers)
        raise AssertionError(f"collector requested unsupported route: {suffix}")

    monkeypatch.setattr(proof.httpx, "HTTPTransport", lambda **_kwargs: httpx.MockTransport(lambda req: response(req.url.path)))
    # Existing presentation checks have their own real PDF tests. Only text
    # content is stubbed here; real PDF parsing, fetch, hash and identity checks run.
    text = " ".join([*proof._expected_engagement_metadata().values(), *proof.base.SPANISH_PDF_MARKERS])
    monkeypatch.setattr(proof.base, "_pdf_text", lambda _body: text)
    monkeypatch.setattr(proof, "client_evidence_summary_has_five_fields", lambda *_args, **_kwargs: True)

    class BrowserResponse:
        status = 200
        ok = True
        headers = {"content-type": "application/json"}
        def __init__(self, value): self.value = value
        def body(self): return json.dumps(self.value).encode()
        def json(self): return deepcopy(self.value)

    browser_reads = []
    def browser_get(url, **kwargs):
        browser_reads.append(url)
        assert kwargs["headers"][proof.base.recovery.BROWSER_PROJECTION_HEADER] == proof.base.recovery.BROWSER_PROJECTION_VALUE
        value = deepcopy(projected)
        if len(browser_reads) > 1 and control["kind"] == "post_read_mutation":
            value["revision"] += 1
        return BrowserResponse(value)

    def run():
        return proof._verify_localized_spanish_terminal_artifacts(
            SimpleNamespace(request=SimpleNamespace(get=browser_get)),
            frontend_origin="https://app.nicoaudit.com", run_id=RUN, expected_commit_sha=SHA,
        )
    return SimpleNamespace(run=run, control=control, requests=requests, package=package,
                           retention=retention, projected=projected, proof=proof,
                           root=tmp_path, route_root=route_root)


def test_actual_release_entrypoint_retains_and_verifies_complete_bilingual_downloads(acceptance):
    result = acceptance.run()
    path = Path(result["export_download_manifest_path"])
    receipt = json.loads(path.read_bytes())
    assert result["export_download_manifest_sha256"] == sha(path.read_bytes())
    assert result["supported_export_bytes_and_bindings_verified"] is True
    assert result["full_bilingual_export_acceptance"] is True
    assert receipt["gaps"] == []
    assert receipt["status"] == "VERIFIED_BILINGUAL_EXPORTS"
    assert receipt["bindings"]["terminal_snapshot"]["revision"] == 7
    assert receipt["bindings"]["source_report_id"] == REPORT
    for item in receipt["files"]:
        body = (path.parent / item["path"]).read_bytes()
        assert len(body) == item["size_bytes"] and sha(body) == item["sha256"]
        assert "set-cookie" not in item.get("response_headers", {})
    by_label = {item["label"]: item for item in receipt["files"]}
    assert by_label["canonical-json"]["sha256"] != acceptance.package["canonical_json_sha256"]
    assert by_label["localized-markdown-en"]["sha256"] != by_label["localized-markdown-es-MX"]["sha256"]
    assert by_label["source-html"]["sha256"] == acceptance.package["html_sha256"]
    assert acceptance.requests.count(acceptance.route_root + "/report/json") == 2
    assert sum(route.endswith("/evidence-package") for route in acceptance.requests) == 2
    assert all(not route.endswith(("/localized-report/en/html", "/localized-report/en/json")) for route in acceptance.requests)


@pytest.mark.parametrize("control", [
    "wrong_run_family", "wrong_revision", "missing_manifest", "corrupt_manifest",
    "corrupt_retained_html", "corrupt_download", "rehashed_wrong_download",
    "wrong_run_header", "failed_applicable_export", "localized_markdown_hash",
    "invented_approval", "wrong_source_localized_pdf", "post_read_mutation",
    "corrupt_zip_member", "wrong_locale_zip", "invented_zip_approval", "invented_manifest_approval",
])
def test_isolated_negative_controls_fail_actual_release_entrypoint(acceptance, control):
    acceptance.control["kind"] = control
    with pytest.raises((ValueError, AssertionError)):
        acceptance.run()
    manifests = list(Path("audit-results/export-retention").glob("*/*/download-manifest.json"))
    assert len(manifests) == 1
    receipt = json.loads(manifests[0].read_bytes())
    assert receipt["status"] == "FAILED"
    assert receipt["full_bilingual_export_acceptance"] is False
    assert receipt["files"]  # Original failed response bytes remain available.


def test_changed_local_download_is_rejected_before_entrypoint_reports_success(acceptance, monkeypatch):
    original = acceptance.retention.Capture.finish
    def damage_isolated_copy(capture):
        item = next(item for item in capture.receipt["files"] if item["label"] == "source-html")
        (capture.directory / item["path"]).write_bytes(b"isolated negative control")
        original(capture)
    monkeypatch.setattr(acceptance.retention.Capture, "finish", damage_isolated_copy)
    with pytest.raises(ValueError, match="retained production download changed"):
        acceptance.run()


def test_repeated_read_only_capture_preserves_previous_receipt_and_bytes(acceptance):
    first = acceptance.run()
    original_path = Path(first["export_download_manifest_path"])
    original_bytes = original_path.read_bytes()
    second = acceptance.run()
    assert first["export_download_manifest_path"] != second["export_download_manifest_path"]
    assert original_path.read_bytes() == original_bytes
    assert first["canonical_truth_sha256"] == second["canonical_truth_sha256"]


def test_receipt_upload_is_in_existing_always_upload_step():
    workflow = (ROOT / ".github/workflows/spanish-comprehensive-production-proof.yml").read_text()
    upload = workflow.split("- name: Upload immutable Spanish proof", 1)[1].split("# Legacy contract locator", 1)[0]
    assert "if: always()" in upload
    assert "audit-results/export-retention/**" in upload
