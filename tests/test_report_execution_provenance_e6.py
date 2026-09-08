from __future__ import annotations

import base64
from copy import deepcopy
import gzip
import hashlib
import io
import json
from types import SimpleNamespace

from pypdf import PdfReader
import pytest


def digest(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    from nico.api import final_report_worker_bootstrap  # noqa: F401
    from nico import comprehensive_scanner_inventory_v1 as inventory
    from nico.scanner_execution_receipt_v1 import invocation_receipt

    monkeypatch.setattr(inventory, "DEFAULT_RAW_ROOT", str(tmp_path))
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("NICO_FRONTEND_BUILD_COMMIT_SHA", "b" * 40)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "synthetic-e6-deployment")
    # This fixture tests scanner/report provenance, not an external deployment.
    monkeypatch.delenv("NICO_FRONTEND_DEPLOYMENT_ID", raising=False)
    identity = dict(run_id="comprun_e6_synthetic", repository="example/authorized",
        commit_sha="c" * 40, customer_id="synthetic_customer",
        project_id="synthetic_project", evidence_ledger_id="ledger_e6_synthetic")
    raw = b'{"diagnostics":[{"message":"SYNTHETIC-PRIVATE-DIAGNOSTIC"}]}'
    compressed = gzip.compress(raw, mtime=0)
    blob = tmp_path / "typescript.gz"
    blob.write_bytes(compressed)
    receipt = invocation_receipt(["tsc", "--noEmit"], cwd=None,
        before=[], after=[], returncode=2, timed_out=False)
    scanner = dict(tool="typescript", status="completed_with_findings",
        commit_sha=identity["commit_sha"], snapshot_commit_sha=identity["commit_sha"],
        scanner_tool_version="Version 5.9.3", command_intent="tsc --noEmit",
        scanner_execution_receipt=receipt, generated_config_sha256="d" * 64,
        artifact_hash="e" * 64, returncode=2, returncode_valid=True,
        source_checkout_verified=True, output_capture_complete=True,
        execution_observed_for_this_report=True, raw_artifact_retention_complete=True,
        raw_artifact_sha256=digest(raw), raw_artifact={"storage_key": "typescript.gz",
            "sha256": digest(raw), "gzip_sha256": digest(compressed),
            "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True})
    scan = dict(scan_id="scan_snapshot_e6", **{k: identity[k] for k in
        ("run_id", "repository", "customer_id", "project_id")},
        snapshot_commit_sha=identity["commit_sha"], actual_commit_sha=identity["commit_sha"],
        snapshot_match=True, status="complete", tools_requested=["typescript"],
        scanner_results=[scanner])
    calls = []
    def get_scan(scan_id):
        calls.append(scan_id)
        return deepcopy(scan)
    monkeypatch.setattr(inventory, "get_scan", get_scan)
    context = dict(**identity, generated_at="2026-09-08T00:00:00Z", report_language="en",
        prior_stage_results={"authorization_and_scope": {"status": "complete", "evidence": {"authorized": True}},
            "dependency_security_static_analysis": {"status": "complete", "scan_id": scan["scan_id"]},
            "evidence_reconciliation_and_scoring": {"status": "complete", "assessment": {
                "technical_score": 80, "sections": [], "human_review_required": True,
                "client_delivery_allowed": False}, "evidence": {}}})
    return SimpleNamespace(context=context, scan=scan, scanner=scanner, blob=blob,
        raw=raw, receipt=receipt, calls=calls)


def build(evidence, language="en"):
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    context = deepcopy(evidence.context)
    context["report_language"] = language
    result = build_canonical_report_source(context)
    assert result["status"] == "complete", result
    return result


def provenance(result):
    return result["report_package"]["json"]["assessment"]["nico_release_provenance"]


def test_actual_final_source_uses_retained_version_not_configured_default(evidence):
    result = build(evidence)
    release = provenance(result)
    execution = release["scanner_execution_evidence"]
    row = execution["scanner_records"][0]
    assert row["scanner_version"] == "5.9.3"
    assert release["scanner_versions"]["typescript"] == "6.0.3"
    assert row["execution_status"] == "completed_with_findings"
    assert row["execution_evidence_verified"] is True
    assert row["raw_artifact"]["sha256"] == digest(evidence.raw)
    assert row["execution_provenance"]["execution_receipt"]["receipt_sha256"] == evidence.receipt["receipt_sha256"]
    assert row["configuration"]["full_configuration_verified"] is False
    assert execution["run_id"] == evidence.context["run_id"]
    assert execution["commit_sha"] == "c" * 40
    assert release["backend_build_commit"] == "a" * 40
    assert execution["coverage_status"] == "not_evaluated_by_inventory"
    assert "SYNTHETIC-PRIVATE" not in json.dumps(result)
    assert evidence.calls == ["scan_snapshot_e6"]


@pytest.mark.parametrize("change", ["missing", "corrupt", "wrong_run", "wrong_source", "missing_receipt", "corrupt_receipt"])
def test_actual_final_source_keeps_failed_evidence_unverified(evidence, change):
    if change == "missing": evidence.blob.unlink()
    if change == "corrupt": evidence.blob.write_bytes(b"isolated corruption")
    if change == "wrong_run": evidence.scan["run_id"] = "comprun_other"
    if change == "wrong_source": evidence.scan["actual_commit_sha"] = "f" * 40
    if change == "missing_receipt": evidence.scanner.pop("scanner_execution_receipt")
    if change == "corrupt_receipt": evidence.scanner["scanner_execution_receipt"]["exit_code"] = 0
    before = deepcopy(evidence.context)
    result = build(evidence)
    execution = provenance(result)["scanner_execution_evidence"]
    assert execution["verification_status"] != "verified"
    assert not any(row.get("execution_evidence_verified") for row in execution["scanner_records"])
    assert result["client_delivery_allowed"] is False
    assert evidence.context == before


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_production_composition_exports_same_frozen_execution_evidence(evidence, language, monkeypatch):
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    result = build(evidence, language)
    original = deepcopy(provenance(result))
    # Rendering after a deployment/scanner change must preserve the captured report.
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "f" * 40)
    evidence.scanner["scanner_tool_version"] = "Version 6.0.3"
    package = rebuild_client_artifacts(result["report_package"])
    assert package["json"]["assessment"]["nico_release_provenance"] == original
    pdf = PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"])))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    for rendered in (package["markdown"], package["html"], text):
        assert "5.9.3" in rendered
        assert digest(evidence.raw) in rendered
        assert evidence.receipt["receipt_sha256"] in rendered
        assert "a" * 40 in rendered and "c" * 40 in rendered
        assert "f" * 40 not in rendered
    assert package["pdf_page_count"] == len(pdf.pages)
    assert len(evidence.calls) == 1


def test_reordering_and_changed_evidence_have_truthful_report_identity(evidence):
    first = build(evidence)
    evidence.context["prior_stage_results"] = dict(reversed(list(evidence.context["prior_stage_results"].items())))
    reordered = build(evidence)
    assert provenance(first) == provenance(reordered)
    evidence.scanner["scanner_tool_version"] = "Version 5.9.4"
    changed = build(evidence)
    assert changed["report_id"] != reordered["report_id"]
    assert changed["report_package"]["canonical_truth_sha256"] != reordered["report_package"]["canonical_truth_sha256"]
