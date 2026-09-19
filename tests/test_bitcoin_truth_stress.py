"""Synthetic truth contracts; never live authorization or production acceptance."""
from types import SimpleNamespace
import json
from pathlib import Path

import pytest

from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

SHA = "a" * 40
FROZEN_OBSERVATIONS = json.loads((Path(__file__).parent / "fixtures" / "bitcoin_truth_stress_observations.json").read_text())


@pytest.mark.parametrize("execution", ["unavailable", "failed", "partial"])
def test_missing_inventory_does_not_turn_execution_into_inapplicability(execution):
    result = normalize_scanner_applicability_canonical({
        "identity": {"commit_sha": SHA},
        "scanner_execution_records": [{"scanner_name": "npm-audit", "commit_sha": SHA,
            "status": execution, "state": execution, "completed": False,
            "failure_reason": "No package-lock.json with an adjacent package.json was found."}],
    })
    record = result["requested_scanner_records"][0]
    assert record["applicability_state"] == "applicability_unproven"
    assert record["execution_state"] == execution
    assert record["applicability_reason"]
    assert result["not_applicable_scanner_records"] == []
    assert result["assessment"]["scanner_applicability_summary"]["applicability_unproven_scanners"] == 1


def test_size_limited_checkout_keeps_identity_without_scanner_completion(monkeypatch):
    from nico import scanner_worker as base, snapshot_scanner_worker as worker
    from nico.scanner_determinism_v1 import clone_repository_at_snapshot
    from nico.storage import MemoryAdapter

    def fake_git(command, **kwargs):
        return SimpleNamespace(returncode=0, stderr="", stdout=SHA if command[:3] == ["git", "rev-parse", "HEAD"] else "")

    monkeypatch.setattr(worker, "_git", fake_git)
    monkeypatch.setattr(worker, "clone_repository_at_snapshot", clone_repository_at_snapshot)
    monkeypatch.setattr(base, "directory_size", lambda path: 291563274)
    monkeypatch.setattr(worker, "STORE", MemoryAdapter())
    monkeypatch.setattr(base, "SCAN_JOBS", {"synthetic_size_limit": {}})
    monkeypatch.setattr(worker.tool_runners, "run_scanner_tool", lambda *args: pytest.fail("oversized checkout must not execute scanners"))
    worker._run_snapshot_scan("synthetic_size_limit", {
        "repository": "example/authorized-fixture", "snapshot_commit_sha": SHA,
        "snapshot_id": "synthetic_snapshot", "run_id": "synthetic_run", "tools": ["bandit", "npm-audit"],
    })
    result = base.SCAN_JOBS["synthetic_size_limit"]
    assert result["snapshot_match"] is True
    assert result["actual_commit_sha"] == SHA
    assert result["status"] in {"unavailable", "partial", "failed"}
    assert result["execution_limit"]["reason"] == "repository_size_limit_exceeded"
    assert result["execution_limit"]["observed_bytes"] == 291563274
    assert result["execution_limit"]["limit_bytes"] == base.MAX_REPO_BYTES
    assert result["evidence_summary"]["repo_size_bytes"] == 291563274
    assert result["tools_run"] == []
    assert set(result["unavailable_tools"]) == {"bandit", "npm-audit"}
    assert all(row["execution_state"] == "unavailable" for row in result["scanner_results"])
    assert all(row["applicability_state"] == "applicability_unproven" for row in result["scanner_results"])


def test_requester_attestation_is_not_independent_permission_verification():
    from nico.comprehensive_production_capabilities import _authorization_provider
    result = _authorization_provider({"service_id": "comprehensive", "run_id": "synthetic_run",
        "repository": "example/authorized-fixture", "commit_sha": SHA,
        "evidence_ledger_id": "synthetic_ledger", "authorization_confirmed": True})
    assert result["authorization_confirmed"] is True  # existing gate meaning preserved
    assert result["evidence"]["requester_authorization_attestation"] == "confirmed"
    assert result["evidence"]["independent_authorization_verification"] == "not_established"
    assert "Ownership or explicit authorization" not in result["summary"]
    assert result["client_delivery_allowed"] is False


def test_coverage_projection_keeps_both_existing_denominators():
    from nico.repository_profile_coverage_v1 import profile_coverage
    from nico.comprehensive_report_package import _source_tables
    frozen = FROZEN_OBSERVATIONS["coverage"]
    eligible = [f"src/module_{i}.py" for i in range(frozen["eligible_source_files"])]
    excluded = [f"tests/test_module_{i}.py" for i in range(frozen["observed_source_files"] - len(eligible))]
    coverage = profile_coverage({"tree_paths": eligible + excluded,
        "files": {p: "pass\n" for p in eligible[:frozen["analyzed_source_files"]]},
        "tree_collection_succeeded": True, "tree_truncated": False}, {"files_analyzed": frozen["analyzed_source_files"]})
    assert coverage["eligible_source_coverage_percent"] == 3.65
    assert coverage["whole_repository_coverage_percent"] == 1.03
    rows = dict(_source_tables({"profile_coverage": coverage})[0]["rows"])
    assert rows["Eligible-source analysis coverage (%)"] == 3.65
    assert rows["Whole supported-source coverage (%)"] == 1.03
    assert rows["Eligible-source coverage fraction"] == "5 / 137"
    assert rows["Observed supported-source coverage fraction"] == "5 / 484"
    metrics = coverage["coverage_metrics"]
    assert metrics["eligible_source_analysis"]["numerator"] == 5
    assert metrics["eligible_source_analysis"]["denominator"] == 137
    assert metrics["observed_supported_source_analysis"]["denominator"] == 484
    assert metrics["eligible_source_analysis"]["denominator_population"] != metrics["observed_supported_source_analysis"]["denominator_population"]


def test_empty_scanner_ledger_cannot_establish_verified_assurance():
    from nico.express_score_assurance_ledger_v45 import _normalize_scanner_section
    section = {}
    _normalize_scanner_section({}, section)
    assert section["scanner_execution_denominator"] == 0
    assert section["assurance_status"] == "unverified"


def _limited_scan():
    return {"scan_id": "synthetic_scan", "status": "unavailable", "snapshot_match": True,
        "actual_commit_sha": SHA, "tools_requested": ["bandit"], "tools_run": [],
        "unavailable_tools": ["bandit"], "execution_limit": {
            "reason": "repository_size_limit_exceeded", "commit_sha": SHA,
            "observed_bytes": 291563274, "limit_bytes": 100000000,
            "scanner_execution_permitted": False},
        "scanner_results": [{"tool": "bandit", "status": "unavailable", "commit_sha": SHA,
            "execution_state": "unavailable", "execution_reason": "repository_size_limit_exceeded",
            "applicability_state": "applicability_unproven", "completed": False}]}


def test_verified_size_limit_continues_as_limited_evidence_without_execution_credit(monkeypatch):
    from nico import comprehensive_native_providers as native
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records, retained_scanner_payload
    context = {"run_id": "synthetic_run", "repository": "example/authorized-fixture", "commit_sha": SHA,
        "evidence_ledger_id": "synthetic_ledger", "customer_id": "synthetic_customer", "project_id": "synthetic_project",
        "prior_stage_results": {"immutable_repository_snapshot": {"snapshot": {"status": "attached", "commit_sha": SHA}}}}
    scan = _limited_scan()
    monkeypatch.setattr(native, "start_snapshot_scan", lambda payload: scan)
    monkeypatch.setattr(native, "get_scan", lambda scan_id: scan)
    stage = native.scanner_suite_provider(context)
    assert stage["status"] == "complete"  # evidence collection stage, not scanner execution
    assert stage["scanner"]["status"] == "unavailable"
    assert stage["scanner"]["tools_run"] == []
    assert stage["scanner"]["execution_limit"] == scan["execution_limit"]
    stage["scanner_execution_records"] = compact_scanner_records(scan, commit_sha=SHA)
    context["prior_stage_results"]["dependency_security_static_analysis"] = stage
    retained = retained_scanner_payload(context)
    assert retained["execution_limit"] == scan["execution_limit"]
    assert retained["scanner_execution_records"][0]["execution_state"] == "unavailable"
    assert retained["scanner_execution_records"][0]["applicability_state"] == "applicability_unproven"
    for invalid in ({"commit_sha": "b" * 40}, {"observed_bytes": 1}, {"scanner_execution_permitted": True}):
        scan["execution_limit"] = {**_limited_scan()["execution_limit"], **invalid}
        assert native.scanner_suite_provider(context)["status"] == "blocked"


@pytest.mark.parametrize("analyzed,expected", [(5, "limited"), (137, "supported_scope")])
def test_assurance_preserves_score_and_distinguishes_supported_control(analyzed, expected):
    from nico.comprehensive_score_assurance_ledger_v45 import bind_source_security_assurance
    coverage = {"version": "nico.repository_profile_coverage.v1", "inventory_complete": True,
        "observed_source_files": 484, "eligible_source_files": 137, "analyzed_source_files": analyzed,
        "unsampled_eligible_source_files": 137-analyzed, "eligible_source_coverage_percent": round(100*analyzed/137, 2),
        "whole_repository_coverage_percent": round(100*analyzed/484, 2)}
    original = {"assessment": {"maturity_signal": {"score": 74, "evidence_readiness_score": 62}},
        "stage_summaries": [{"profile_coverage": coverage}],
        "requested_scanner_records": [{"applicable": True, "applicability_state": "applicable",
            "completed": True, "verified_complete": True, "execution_state": "complete"}]}
    result = bind_source_security_assurance(original)
    assert result["assessment"]["maturity_signal"] == original["assessment"]["maturity_signal"]
    assurance = result["source_security_assurance"]
    assert assurance["status"] == expected
    assert assurance["repository_wide_security_rating"] is False
    assert assurance["coverage_metrics"]["observed_supported_source_analysis"]["denominator"] == 484
    assert original.get("source_security_assurance") is None
    assert bind_source_security_assurance({})["source_security_assurance"]["status"] == "unverified"


def test_reconciliation_keeps_unproven_applicability_out_of_applicable_counts():
    from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth
    result = reconcile_authoritative_scanner_truth({"identity": {"commit_sha": SHA},
        "scanner_execution_records": [{"scanner_name": "bandit", "status": "unavailable", "commit_sha": SHA}]})
    summary = result["assessment"]["scanner_applicability_summary"]
    assert summary["applicable_scanners"] == summary["incomplete_applicable_scanners"] == 0
    assert summary["applicability_unproven_scanners"] == 1
    assert result["client_readiness_contract"]["applicable_exact_run_scanners"] == []
    assert result["client_readiness_contract"]["applicability_unproven_scanners"] == ["bandit"]
    assert result["delivery_gate"]["analyzer_evidence_ready"] is False


def test_completed_execution_cannot_resolve_unproven_applicability_in_prerender():
    from nico.comprehensive_pre_render_scanner_truth_v65 import derive_authoritative_scanner_truth
    record = {"scanner_name": "bandit", "status": "completed", "completed": True, "verified": True,
        "artifact_hash": "c" * 64, "exact_commit_match": True,
        "applicable": None, "applicability_state": "applicability_unproven"}
    truth = derive_authoritative_scanner_truth({"dependency_security_static_analysis": {"scanner_execution_records": [record]}})
    assert truth["completed"] == ["bandit"]
    assert truth["applicability_unproven"] == ["bandit"]
    assert truth["applicable"] == []


def test_applicability_normalization_is_idempotent_and_javascript_does_not_prove_typescript():
    original = {"repository_evidence": {"file_evidence": {"sampled_paths": ["app.js", "package.json"]}},
        "scanner_execution_records": [{"scanner_name": "typescript", "status": "failed", "failure_reason": "Process failed."}]}
    first = normalize_scanner_applicability_canonical(original)
    second = normalize_scanner_applicability_canonical(first)
    assert first["requested_scanner_records"] == second["requested_scanner_records"]
    assert first["requested_scanner_records"][0]["applicability_state"] == "applicability_unproven"


@pytest.mark.parametrize("source,kind,expected", [(SHA, "VERCEL_GIT_COMMIT_SHA", "aligned"),
    ("b" * 40, "VERCEL_GIT_COMMIT_SHA", "mismatch"), (SHA, "NICO_RELEASE_SHA", "unverified"),
    ("dpl_synthetic", "VERCEL_GIT_COMMIT_SHA", "unverified")])
def test_serving_source_alignment_is_separate_from_configured_deployment_pin(monkeypatch, source, kind, expected):
    import base64, hashlib, json
    from nico import report_execution_provenance_e6 as provenance
    raw = json.dumps({"status": "ok", "release_sha": source, "release_sha_source": kind,
        "deployment_id": "dpl_synthetic", "deployment_id_source": "VERCEL_DEPLOYMENT_ID"}).encode()
    observation = {"frontend_observation_schema": "nico.frontend-runtime-observation.v2",
        "status": "mismatch", "source_url": provenance.FRONTEND_URL, "deployment_identity_verified": False,
        "release_sha": source, "release_sha_source": kind,
        "deployment_id": "dpl_synthetic", "deployment_id_source": "VERCEL_DEPLOYMENT_ID",
        "observation_bytes_base64": base64.b64encode(raw).decode(), "observation_size_bytes": len(raw),
        "observation_sha256": hashlib.sha256(raw).hexdigest()}
    monkeypatch.setattr(provenance, "capture_frontend_release", lambda *args: observation)
    monkeypatch.setattr(provenance, "scanner_execution_evidence", lambda *args: {})
    original = {"identity": {"commit_sha": "c" * 40, "run_id": "synthetic_run"}, "assessment": {
        "nico_release_provenance": {"backend_build_commit": SHA, "backend_identity_source": "RAILWAY_GIT_COMMIT_SHA",
            "deployment_identity_established": True, "frontend_build_commit": "d" * 40,
            "frontend_deployment_id": "dpl_configured_previous"}}}
    result = provenance.bind_report_execution_provenance(original, raw_stages={})["assessment"]["nico_release_provenance"]
    assert result["frontend_backend_source_alignment"] == expected
    assert result["frontend_build_commit"] == "d" * 40  # never bypass the existing configured pin
    assert result["frontend_deployment_identity_verified"] is False
    assert result["exact_release_readiness"] == "unverified" if expected != "mismatch" else result["exact_release_readiness"] == "blocked"
    observation["observation_sha256"] = "0" * 64
    corrupt = provenance.bind_report_execution_provenance(original, raw_stages={})["assessment"]["nico_release_provenance"]
    assert corrupt["frontend_backend_source_alignment"] == "unverified"


@pytest.mark.parametrize("mode,credential", [("anonymous_public", False), ("authenticated_read_only", True), (None, None)])
def test_canonical_authorization_keeps_attestation_access_and_independent_evidence_separate(mode, credential):
    from nico.comprehensive_canonical_report_source_v1 import _authorization_evidence
    stages = {"authorization_and_scope": {"status": "complete", "authorization_confirmed": True},
        "immutable_repository_snapshot": {"status": "complete", "snapshot": {"status": "attached", "commit_sha": SHA,
            "provider_access_observed": True, "access_mode": mode, "credential_used": credential}}}
    result = _authorization_evidence(stages, SHA)
    assert result["requester_authorization_attestation"] == "confirmed"
    assert result["repository_access_mode"] == (mode or "unknown")
    assert result["provider_credential_used"] is credential
    assert result["independent_authorization_verification"] == "not_established"
    stages["immutable_repository_snapshot"]["snapshot"]["commit_sha"] = "b" * 40
    assert _authorization_evidence(stages, SHA)["repository_access_mode"] == "unknown"


@pytest.mark.parametrize("spanish", [False, True])
def test_limited_coverage_is_visible_on_score_cover_and_matches_csv(spanish):
    import csv, io, json
    from pypdf import PdfReader
    from nico.comprehensive_score_assurance_ledger_v45 import bind_source_security_assurance
    from nico.v2_dark_branded_cover import _cover
    from nico.comprehensive_report_package import _source_markdown
    from nico.comprehensive_decision_grade_csv_v6 import _evidence_csv
    stage = {"stage_id": "repository_and_delivery_evidence", "title": "Source evidence", "status": "complete",
        "profile_coverage": {"version": "nico.repository_profile_coverage.v1", "inventory_complete": True,
            "observed_source_files": 484, "eligible_source_files": 137, "analyzed_source_files": 5,
            "unsampled_eligible_source_files": 132, "eligible_source_coverage_percent": 3.65,
            "whole_repository_coverage_percent": 1.03}}
    canonical = bind_source_security_assurance({"identity": {"repository": "example/control", "commit_sha": SHA},
        "stage_summaries": [stage], "assessment": {"technical_score": 74, "evidence_adjusted_score": 62}})
    page = PdfReader(io.BytesIO(_cover(canonical, spanish=spanish))).pages[0].extract_text()
    for fact in ("5 / 137", "5 / 484", "3.65%", "1.03%", "132"):
        assert fact in page
    assert ("limitada" if spanish else "limited") in page
    assert ("no es una calificación de seguridad" if spanish else "not a repository-wide security rating") in page
    markdown = "\n".join(_source_markdown(stage, spanish=spanish))
    assert "5 / 137" in markdown and "5 / 484" in markdown
    rows = [json.loads(r["record"]) for r in csv.DictReader(io.StringIO(_evidence_csv([stage]))) if r["record_type"] == "source_coverage_metric"]
    assert {r["denominator"] for r in rows} == {137, 484}
    assert {r["numerator"] for r in rows} == {5}


def test_pinned_frontend_with_different_backend_cannot_claim_exact_release_readiness():
    import base64, hashlib, json
    from nico.comprehensive_client_delivery_contract_v1 import version_truth
    from nico.report_execution_provenance_e6 import FRONTEND_URL
    value = {"status": "ok", "release_sha": "b" * 40, "release_sha_source": "VERCEL_GIT_COMMIT_SHA",
        "deployment_id": "dpl_synthetic", "deployment_id_source": "VERCEL_DEPLOYMENT_ID"}
    raw = json.dumps(value).encode()
    observation = {**value, "status": "verified", "deployment_identity_verified": True, "source_url": FRONTEND_URL,
        "frontend_observation_schema": "nico.frontend-runtime-observation.v2",
        "observation_bytes_base64": base64.b64encode(raw).decode(), "observation_size_bytes": len(raw),
        "observation_sha256": hashlib.sha256(raw).hexdigest()}
    provenance = {"backend_build_commit": SHA, "backend_identity_source": "RAILWAY_GIT_COMMIT_SHA",
        "deployment_identity_conflict": False, "railway_deployment_id": "synthetic_backend_deployment",
        "frontend_build_commit": "b" * 40, "frontend_deployment_id": "dpl_synthetic",
        "assessment_run_id": "synthetic_run", "assessed_repository_commit": "c" * 40,
        "frontend_runtime_observation": observation}
    record = {"identity": {"run_id": "synthetic_run", "commit_sha": "c" * 40},
        "reports": {"json": {"assessment": {"nico_release_provenance": provenance}}}}
    assert version_truth(record)["deployment_identity_established"] is False
    provenance["backend_build_commit"] = "b" * 40
    assert version_truth(record)["deployment_identity_established"] is True


def test_score_projection_cannot_verify_absent_scanners_from_empty_limitations():
    from nico.v2_report_quality_repairs import repair_canonical_truth
    result = repair_canonical_truth({"json": {"assessment": {"sections": [
        {"id": "static_analysis", "score": 74, "status": "review_limited", "unavailable": []}]}}})
    section = result["json"]["assessment"]["sections"][0]
    assert section["score"] == 74
    assert section["assurance_status"] == "unverified"


def test_client_scanner_stage_names_required_and_unproven_populations():
    from nico.comprehensive_human_review_package_cleanup_v1 import build_scanner_execution_stage
    renderer = SimpleNamespace(_stage=lambda stage_id, title, summary, **kwargs: {"summary": summary, **kwargs})
    record = {"scanner_name": "bandit", "completed": False, "status": "unavailable", "applicable": None,
        "applicability_state": "applicability_unproven", "execution_state": "unavailable"}
    result = build_scanner_execution_stage({"scanner_execution_records": [record]}, renderer)
    assert "0 of 1 required scanner executions completed" in result["summary"]
    assert "applicability unproven: 1" in result["summary"]
    assert "0 of 1 applicable" not in result["summary"]


def test_conflicting_input_evidence_does_not_establish_inapplicability(tmp_path):
    from nico.node_scanner_applicability_v1 import inspect_node_inputs
    inventory = inspect_node_inputs(tmp_path, SHA)
    canonical = {"identity": {"commit_sha": SHA},
        "repository_evidence": {"file_evidence": {"sampled_paths": ["package.json"]}},
        "scanner_execution_records": [{"scanner_name": "npm-audit", "commit_sha": SHA,
            "status": "unavailable", "applicability_evidence": inventory}]}
    result = normalize_scanner_applicability_canonical(canonical)
    record = result["requested_scanner_records"][0]
    assert record["applicability_state"] == "applicability_unproven"
    assert record["applicable"] is None
    assert "conflict" in record["applicability_reason"].lower()


def test_retained_complete_input_inventory_proves_applicability_without_report_path_samples(tmp_path):
    from nico.node_scanner_applicability_v1 import inspect_node_inputs
    (tmp_path / "package.json").write_text('{"devDependencies":{"typescript":"synthetic"}}')
    inventory = inspect_node_inputs(tmp_path, SHA)
    result = normalize_scanner_applicability_canonical({"identity": {"commit_sha": SHA},
        "scanner_execution_records": [{"scanner_name": "typescript", "commit_sha": SHA,
            "status": "failed", "applicability_evidence": inventory}]})
    assert result["requested_scanner_records"][0]["applicability_state"] == "applicable"
    assert result["requested_scanner_records"][0]["execution_state"] == "failed"


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_public_report_builder_retains_limited_truth_across_artifacts(monkeypatch, language):
    """Catch late canonical/localization/rendering loss of coverage and authorization evidence."""
    import base64, io
    from pypdf import PdfReader
    from nico import report_execution_provenance_e6 as provenance
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    from nico.comprehensive_production_capabilities import _authorization_provider
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.source_signal_analysis_v2 import analyze_source_signals
    from nico.comprehensive_decision_grade_csv_v6 import _evidence_csv
    # Platform and scanner-store observations are outside this synthetic report case.
    monkeypatch.setattr(provenance, "capture_frontend_release", lambda *args: {"status": "unavailable",
        "frontend_observation_schema": "nico.frontend-runtime-observation.v2"})
    monkeypatch.setattr(provenance, "scanner_execution_evidence", lambda *args: {"verification_status": "unverified"})
    context = {"service_id": "comprehensive", "repository": "example/authorized-fixture", "commit_sha": SHA,
        "run_id": "synthetic_truth_report", "evidence_ledger_id": "synthetic_ledger", "customer_id": "customer",
        "project_id": "project", "authorization_confirmed": True, "report_language": language,
        "generated_at": "2026-09-19T00:00:00Z"}
    coverage = {"version": "nico.repository_profile_coverage.v1", "inventory_complete": True,
        "observed_source_files": 484, "eligible_source_files": 137, "analyzed_source_files": 5,
        "unsampled_eligible_source_files": 132, "eligible_source_coverage_percent": 3.65,
        "whole_repository_coverage_percent": 1.03}
    context["prior_stage_results"] = {
        "authorization_and_scope": _authorization_provider(context),
        "immutable_repository_snapshot": {"status": "complete", "snapshot": {"status": "attached", "commit_sha": SHA,
            "provider_access_observed": True, "access_mode": "anonymous_public", "credential_used": False}},
        "repository_and_delivery_evidence": {"status": "complete", "evidence": {"profile_coverage": coverage},
            "repository_evidence": {"code_signal_evidence": {"snapshot_commit_sha": SHA,
                "risk_pattern_hits": 1, "risk_records": analyze_source_signals({"src/runner.py": "exec(command)\n"})["risk_records"]}}},
        "dependency_security_static_analysis": {"status": "complete", "evidence": {"execution_limit": _limited_scan()["execution_limit"]},
            "scanner_execution_records": _limited_scan()["scanner_results"]},
        "evidence_reconciliation_and_scoring": {"status": "complete", "assessment": {"technical_score": 74,
            "maturity_signal": {"score": 74, "presented_score": 74, "evidence_readiness_score": 62}, "sections": []}},
    }
    source = build_canonical_report_source(context)
    assert source["status"] == "complete"
    canonical = source["report_package"]["json"]
    assert canonical["source_security_assurance"]["status"] == "limited"
    assert canonical["authorization_evidence"]["independent_authorization_verification"] == "not_established"
    assert canonical["source_risk_observation_summary"]["reported_count"] == 1
    assert canonical["canonical_findings"] == []
    evidence_csv = _evidence_csv(canonical["stage_summaries"])
    assert "source_risk_observation" in evidence_csv
    assert "src/runner.py" in evidence_csv
    package = rebuild_client_artifacts(source["report_package"])
    pdf = PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"])))
    for rendered in (package["markdown"], package["html"], "\n".join(p.extract_text() for p in pdf.pages)):
        assert "5 / 137" in rendered and "5 / 484" in rendered
        assert "132" in rendered
        assert ("Observaciones de riesgo del código fuente" if language == "es-MX" else "Source-risk observations") in rendered
        assert "src/runner.py" in rendered
        for observation in canonical["source_risk_observations"]:
            assert observation["observation_id"] in "".join(rendered.split())
            assert observation["source_excerpt"] in rendered
            assert observation["repository_revision"] in "".join(rendered.split())
    assert package["json"]["source_security_assurance"]["status"] == "limited"


@pytest.mark.parametrize("alignment", ["aligned", "mismatch", "unknown", "legacy_unknown", "legacy_missing_native_identities"])
def test_new_report_operator_approval_requires_verified_aligned_release(alignment):
    """Synthetic approval boundary; never an owner's production decision."""
    import base64, hashlib, json
    from copy import deepcopy
    from tests.test_comprehensive_operator_approval_v1 import fixture_record, payload
    from nico.comprehensive_operator_approval_v1 import build_operator_edition
    from nico.comprehensive_review_decision_v1 import report_package_from_record
    from nico.comprehensive_run_record import _record_hash
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.report_execution_provenance_e6 import FRONTEND_URL
    record = deepcopy(fixture_record())
    package = report_package_from_record(record)
    provenance = package['json']['assessment']['nico_release_provenance']
    frontend = provenance['backend_build_commit'] if alignment == 'aligned' else 'f' * 40
    value = {'status': 'ok', 'release_sha': frontend, 'release_sha_source': 'VERCEL_GIT_COMMIT_SHA',
        'deployment_id': 'dpl_synthetic_truth', 'deployment_id_source': 'VERCEL_DEPLOYMENT_ID'}
    raw = json.dumps(value).encode()
    provenance.update(frontend_build_commit=frontend, frontend_deployment_id=value['deployment_id'],
        frontend_runtime_observation={**value, 'status': 'verified', 'deployment_identity_verified': True,
            'source_url': FRONTEND_URL, 'frontend_observation_schema': 'nico.frontend-runtime-observation.v2',
            'observation_bytes_base64': base64.b64encode(raw).decode(), 'observation_size_bytes': len(raw),
            'observation_sha256': hashlib.sha256(raw).hexdigest()})
    if alignment in {'unknown', 'legacy_unknown'}:
        provenance['frontend_runtime_observation'] = {'frontend_observation_schema': 'nico.frontend-runtime-observation.v2',
            'status': 'unavailable'}
        if alignment == 'legacy_unknown':
            provenance['frontend_runtime_observation'].pop('frontend_observation_schema')
    if alignment == 'legacy_missing_native_identities':
        from tests.test_phase4_approved_delivery_v4 import _record
        from nico.comprehensive_client_delivery_contract_v1 import version_truth
        from nico.report_execution_provenance_e6 import observed_native_frontend_source
        legacy = deepcopy(report_package_from_record(_record())['json']['assessment']['nico_release_provenance'])
        record['nico_build_commit'] = legacy.pop('backend_build_commit')
        legacy['assessment_run_id'] = record['identity']['run_id']
        legacy['assessed_repository_commit'] = record['identity']['commit_sha']
        provenance.clear()
        provenance.update(legacy)
        assert provenance.get('backend_build_commit') is None
        assert observed_native_frontend_source(provenance['frontend_runtime_observation']) is None
    record['stage_results']['final_comprehensive_report_generation']['report_package'] = rebuild_client_artifacts({'json': package['json']})
    if alignment == 'legacy_missing_native_identities':
        assert version_truth(record)['deployment_identity_established'] is True
    record['integrity_sha256'] = _record_hash(record)
    before = deepcopy(record)
    if alignment == 'aligned':
        assert build_operator_edition(record, payload(record))['review']['decision'] == 'approved'
    else:
        with pytest.raises(ValueError, match='report_release_provenance_unverified'):
            build_operator_edition(record, payload(record))
    assert record == before


@pytest.mark.parametrize('spanish', [False, True])
def test_assurance_headline_passes_unchanged_publication_placeholder_gate(spanish):
    from nico.comprehensive_score_assurance_ledger_v45 import assurance_headline
    from nico.phase9_production_report_gate_v1 import validate_production_report
    headline = assurance_headline({'source_security_assurance': {'status': 'limited'}}, spanish=spanish)
    assert validate_production_report({'executive_summary': headline})['valid'] is True
    assert validate_production_report({'executive_summary': headline + ' TODO'})['valid'] is False


def test_observation_presentation_preserves_literal_evidence_and_record_identity():
    from nico.comprehensive_report_package import _source_markdown, _source_pdf_tables
    from reportlab.platypus import SimpleDocTemplate
    from pypdf import PdfReader
    import io
    stage = {"source_risk_observation_summary": {"reported_count": 2},
        "source_risk_observations": [
            {"observation_id": "observation-one", "path": "unknown", "line": 7, "column": 1,
             "rule_id": "import", "source_excerpt": "import", "repository_revision": SHA,
             "revision_match": True, "semantic_class": "source_observation"},
            {"observation_id": "observation-two", "path": "unknown", "line": 7, "column": 12,
             "rule_id": "import", "source_excerpt": "import", "repository_revision": "b" * 40,
             "revision_match": False, "semantic_class": "source_observation"},
        ]}
    markdown = "\n".join(_source_markdown(stage, spanish=True))
    assert "| Fuente | unknown |" in markdown
    assert "| Fragmento del código fuente | import |" in markdown
    assert "| Columna | 1 |" in markdown and "| Columna | 12 |" in markdown
    assert "| La revisión de las observaciones coincide con la evaluación | No |" in markdown
    output = io.BytesIO()
    SimpleDocTemplate(output).build(_source_pdf_tables(stage, spanish=True, width=450))
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(output.getvalue())).pages)
    for value in ("observation-one", "observation-two", "unknown", "import", SHA, "b" * 40):
        assert value in "".join(text.split())
