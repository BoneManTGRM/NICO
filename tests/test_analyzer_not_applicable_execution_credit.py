"""Regression for production N/A pass credit and stale health summaries."""
from copy import deepcopy
import hashlib
import pytest

from nico.phase14_analyzer_evidence_v1 import reconcile_analyzers
from nico.phase15_production_integration_v1 import integrate_production_truth
from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth

SHA = "a" * 40
DIGEST = "b" * 64

def na(sequence=1):
    return {"scanner": "pip-audit", "status": "not_applicable",
            "commit_sha": SHA, "run_sequence": sequence,
            "artifact_sha256": DIGEST, "scope_reason": "No Python dependency inputs."}

def executed(sequence):
    return {"scanner": "pip-audit", "status": "completed",
            "commit_sha": SHA, "run_sequence": sequence,
            "artifact_sha256": "c" * 64, "capture_complete": True}

@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("required", [False, True])
def test_disposition_acceptance_is_not_execution_credit(count, required):
    records = [na(i) for i in range(1, count + 1)]
    original = deepcopy(records)
    result = reconcile_analyzers(records, expected_sha=SHA,
                                 required_scanners=["pip-audit"] if required else [])
    row = result["analyzers"][0]
    assert row["acceptance_ready"] is (not required or count == 2)
    assert row["successful_passes"] == 0
    assert row["consecutive_successful_passes"] == 0
    assert row["artifact_sha256"] == []
    assert row["client_defect_allowed"] is False
    assert "execution completed" not in str(row["assurance_impact"]).lower()
    assert "analyzer pass" not in str(row["remediation"]).lower()
    assert records == original

@pytest.mark.parametrize("states,total,trailing", [
    (["na", "executed"], 1, 1),
    (["executed", "na"], 1, 0),
    (["executed", "na", "executed"], 2, 1),
    (["na", "executed", "executed"], 2, 2),
    (["executed", "executed"], 2, 2),
])
def test_execution_counts_and_artifacts_exclude_dispositions(states, total, trailing):
    records = [(na if state == "na" else executed)(i)
               for i, state in enumerate(states, 1)]
    row = reconcile_analyzers(records, expected_sha=SHA,
                             required_scanners=["pip-audit"])["analyzers"][0]
    assert row["successful_passes"] == total
    assert row["consecutive_successful_passes"] == trailing
    assert row["artifact_sha256"] == ["c" * 64] * trailing
    assert row["client_defect_allowed"] is (trailing >= 2)
    if states[-1] == "executed":
        assert row["acceptance_ready"] is (trailing >= 2)

@pytest.mark.parametrize("change", [{"commit_sha": "d" * 40}, {"scope_reason": ""}])
def test_wrong_identity_and_missing_disposition_reason_reject(change):
    result = reconcile_analyzers([{**na(), **change}], expected_sha=SHA,
                                 required_scanners=["pip-audit"])
    assert result["acceptance_ready"] is False
    assert result["rejected_records"]
    assert result["analyzers"][0]["successful_passes"] == 0

def canonical_na(tmp_path, sha=SHA):
    from nico.node_scanner_applicability_v1 import inspect_node_inputs, observation_bytes, SOURCE_REASONS
    (tmp_path / "package.json").write_text("{}")
    inventory = inspect_node_inputs(tmp_path, sha)
    record = {
        "scanner_name": "pip-audit", "status": "not_applicable",
        "state": "not_applicable", "completed": False, "verified": False,
        "verified_complete": False, "verified_for_this_report": False,
        "commit_sha": sha, "exact_commit_match": True,
        "applicability_evidence": inventory,
        "applicability_reason": SOURCE_REASONS["pip-audit"],
        "raw_artifact_retention_complete": True,
        "raw_artifact_sha256": hashlib.sha256(observation_bytes(inventory, "pip-audit")).hexdigest(),
    }
    return {
        "identity": {"commit_sha": sha},
        "assessment": {"technical_score": 74},
        "requested_scanner_records": [record],
        "scanner_execution_records": [record],
        "live_scanner_evidence": {"tools_requested": ["pip-audit"], "tools_run": []},
        "evidence_health_summary": {"scanner_records": [
            {"scanner": "pip-audit", "required": True, "status": "not_applicable",
             "successful_passes": 1, "acceptance_ready": False,
             "assurance_impact": "Analyzer execution completed"}
        ]},
    }

def test_authoritative_summary_mirrors_are_consistent_and_idempotent(tmp_path):
    canonical = canonical_na(tmp_path)
    original = deepcopy(canonical)
    output = reconcile_authoritative_scanner_truth(canonical)
    health = output["evidence_health_summary"]
    final = health["phase14_analyzer_evidence"]["analyzers"]
    assert health["scanner_records"] == final
    assert final[0]["required"] is False
    assert final[0]["status"] == "not_applicable"
    assert final[0]["successful_passes"] == final[0]["consecutive_successful_passes"] == 0
    assert final[0]["acceptance_ready"] is True
    assert final[0]["artifact_sha256"] == []
    assert output["analyzer_evidence_report"]["analyzers"] == final
    assert output["analyzer_evidence_ui"]["rows"][0]["passes"] == "0/2"
    assert output["client_readiness_contract"]["not_applicable_scanners_receive_completion_credit"] is False
    assert output["client_readiness_contract"]["coverage_numerator"] == 0
    assert output["client_readiness_contract"]["coverage_denominator"] == 0
    assert output["assessment"]["technical_score"] == 74
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False
    assert canonical == original
    repeated = reconcile_authoritative_scanner_truth(output)
    assert repeated["evidence_health_summary"]["scanner_records"] == final
    assert repeated["requested_scanner_records"] == output["requested_scanner_records"]
    assert output["requested_scanner_records"][0]["applicability_evidence"] == original["requested_scanner_records"][0]["applicability_evidence"]

@pytest.mark.parametrize("invalid", ["missing_inventory", "wrong_sha"])
def test_unproven_applicability_cannot_remove_required_execution(tmp_path, invalid):
    canonical = canonical_na(tmp_path)
    for key in ("requested_scanner_records", "scanner_execution_records"):
        record = canonical[key][0]
        if invalid == "missing_inventory":
            record.pop("applicability_evidence", None)
        else:
            record["commit_sha"] = "d" * 40
    output = reconcile_authoritative_scanner_truth(canonical)
    assert output["client_readiness_contract"]["coverage_denominator"] == 1
    assert output["client_readiness_contract"]["coverage_numerator"] == 0
    assert output["not_applicable_scanner_records"] == []
    assert output["delivery_gate"]["analyzer_evidence_ready"] is False

def test_old_marker_regenerates_na_projection_from_raw_only():
    payload = {
        "identity": {"commit_sha": SHA},
        "scanner_execution_records": [na()],
        "phase15_production_integration": {"version": "nico.phase15.production-integration.v3",
                                         "analyzer_contract_applied": True,
                                         "canonical_population_applied": False},
        "evidence_health_summary": {"phase14_analyzer_evidence": {
            "required_scanners": ["pip-audit"],
            "analyzers": [{"scanner": "pip-audit", "successful_passes": 99}]}},
    }
    original = deepcopy(payload)
    output = integrate_production_truth(payload)
    assert output["analyzer_evidence_report"]["analyzers"][0]["successful_passes"] == 0
    assert payload == original
    assert integrate_production_truth(output)["analyzer_evidence_report"] == output["analyzer_evidence_report"]

def test_optional_execution_policy_is_preserved():
    row = reconcile_analyzers([executed(1)], expected_sha=SHA,
                             required_scanners=[])["analyzers"][0]
    assert row["acceptance_ready"] is True
    assert row["client_defect_allowed"] is True
    assert row["successful_passes"] == row["consecutive_successful_passes"] == 1

@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_actual_exports_preserve_inapplicable_zero_execution_and_human_gates(tmp_path, language):
    import base64
    import io
    from pypdf import PdfReader
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    package = _package(language)
    canonical = canonical_na(tmp_path, package["json"]["identity"]["commit_sha"])
    for key in ("requested_scanner_records", "scanner_execution_records", "live_scanner_evidence"):
        package["json"][key] = deepcopy(canonical[key])
    before = deepcopy(package)
    output = rebuild_client_artifacts(package)
    health = output["json"]["evidence_health_summary"]
    row = next(r for r in health["phase14_analyzer_evidence"]["analyzers"] if r["scanner"] == "pip-audit")
    assert row["status"] == "not_applicable"
    assert row["required"] is False
    assert row["successful_passes"] == row["consecutive_successful_passes"] == 0
    assert row["artifact_sha256"] == []
    assert next(r for r in health["scanner_records"] if r["scanner"] == "pip-audit") == row
    assert output["json"]["client_delivery_allowed"] is False
    assert output["json"]["human_review_required"] is True
    assert output["report_finality"] == "automated_draft"
    pdf_text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(base64.b64decode(output["pdf_base64"]))).pages)
    for text in (output["markdown"], output["html"], pdf_text):
        assert "pip-audit" in text
        assert "not_applicable" not in text
    assert package == before
