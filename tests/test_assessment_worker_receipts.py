from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

import pytest

from nico.assessment_worker_jobs import _digest
from nico.assessment_worker_receipts import validate_contract, validate_receipt
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from scripts.worker_protocol_fixture import contract, identity, receipt


def validate(value, plan=None):
    plan = plan or contract()
    return validate_receipt(identity(plan), plan, "e" * 32, "github:123456:12345678:1", value)


def test_native_findings_are_reparsed_with_source_configuration_and_receipt_identity():
    value = receipt()
    raw, record, binding = validate(value)
    assert json.loads(raw) == value
    assert record["completed"] and len(record["findings"]) == 1
    assert binding["commit_sha"] == "a" * 40
    finding = record["findings"][0]
    assert finding["classification"] == "review_required_candidate"
    assert finding["specialist_review_completed"] is False
    assert finding["path"] == "src/control.cpp" and finding["line"] == 1
    assert finding["observation_id"].startswith("cppcheck_")
    assert record["worker_provenance"]["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["cppcheck_source_coverage"]["configuration_aware"] is False
    assert record["cppcheck_source_coverage"]["header_context_verified"] is False
    assert record["client_delivery_allowed"] is False


@pytest.mark.parametrize("field", list(asdict(identity())))
def test_every_tenant_run_source_contract_release_binding_rejects_substitution(field):
    value = receipt()
    value["identity"][field] = "wrong"
    with pytest.raises(ValueError, match="binding_mismatch"):
        validate(value)


@pytest.mark.parametrize("field,value", [("lease_id", "f" * 32), ("worker_id", "other-owner"),
    ("image_digest", "sha256:" + "f" * 64), ("tool_version", "1.0"),
    ("configuration_sha256", "f" * 64), ("target_hashes", {}), ("native_sha256", "f" * 64)])
def test_execution_binding_and_native_digest_reject_substitution(field, value):
    data = receipt()
    data[field] = value
    with pytest.raises(ValueError):
        validate(data)


@pytest.mark.parametrize("change,expected", [
    ({"xml": "<broken"}, "failed"), ({"progress": ""}, "partial"),
    ({"exit_code": 1}, "failed"), ({"timed_out": True, "exit_code": 124}, "timed_out"),
    ({"output_truncated": True}, "partial"),
    ({"xml": '<!DOCTYPE x [<!ENTITY x "y">]><results/>'}, "failed"),
    ({"xml": '<results version="2"><cppcheck version="2.17.1"/><errors><error id="syntaxError" severity="error"/></errors></results>'}, "partial"),
])
def test_missing_failed_partial_and_timed_out_native_results_never_become_complete(change, expected):
    data = receipt()
    data["native"].update(change)
    data["native_sha256"] = _digest(data["native"])
    raw, record, _ = validate(data)
    assert record["status"] == expected and record["completed"] is False
    assert record["verified_complete"] is False
    assert raw  # useful native failure bytes remain retainable
    assert record["cppcheck_source_coverage"]["requested_targets"] == ["src/control.cpp"]


@pytest.mark.parametrize("path", ["../escape.cpp", "/etc/escape.cpp", "src/../escape.cpp", "src\\escape.cpp",
    "src/./escape.cpp", "src//escape.cpp", "src/new\nline.cpp", "C:escape.cpp"])
def test_special_or_traversing_targets_rejected_explicitly(path):
    plan = contract()
    plan["targets"] = {path: "a" * 64}
    with pytest.raises(ValueError):
        validate_contract(plan)


def test_oversized_and_worker_supplied_canonical_success_rejected():
    value = receipt()
    value["completed"] = True
    with pytest.raises(ValueError):
        validate(value)
    value = receipt()
    value["native"]["progress"] = "x" * 65536
    value["native_sha256"] = _digest(value["native"])
    with pytest.raises(ValueError, match="size_invalid"):
        validate(value)


def test_unexpected_native_target_is_visible_and_blocks_complete_coverage():
    data = receipt()
    data["native"]["progress"] += "Checking outside/scope.cpp ...\n"
    data["native_sha256"] = _digest(data["native"])
    _, record, _ = validate(data)
    assert record["completed"] is False
    assert record["cppcheck_source_coverage"]["requested_targets"] == ["src/control.cpp"]
    assert any(row["rule_id"] == "unexpected_target" for row in record["cppcheck_source_coverage"]["limitations"])


def test_native_output_must_obey_existing_secret_redaction_before_retention():
    data = receipt()
    data["native"]["xml"] = data["native"]["xml"].replace("Synthetic protocol fixture", "gh" + "p_" + "x" * 36)
    data["native_sha256"] = _digest(data["native"])
    with pytest.raises(ValueError, match="redaction_required"):
        validate(data)


@pytest.mark.parametrize("location", ["message", "unused_attribute", "element_text", "element_tail", "limitation"])
def test_decoded_xml_secret_shapes_are_rejected_before_retention_or_projection(location):
    data = receipt()
    synthetic = "gh&#112;_" + "x" * 36
    xml = data["native"]["xml"]
    if location == "message":
        xml = xml.replace("Synthetic protocol fixture", synthetic)
    elif location == "unused_attribute":
        xml = xml.replace('<error id=', '<error extra="' + synthetic + '" id=')
    elif location == "element_text":
        xml = xml.replace("</error>", synthetic + "</error>")
    elif location == "element_tail":
        xml = xml.replace("</error>", "</error>" + synthetic)
    else:
        xml = xml.replace('severity="warning"', 'severity="information"').replace("Synthetic protocol fixture", synthetic)
    data["native"]["xml"] = xml
    data["native_sha256"] = _digest(data["native"])
    with pytest.raises(ValueError, match="redaction_required"):
        validate(data)


def test_compact_projection_preserves_worker_identity_scope_and_native_count():
    _, record, _ = validate(receipt())
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256="f" * 64)
    scan = {"scan_id": identity().scan_id, "scanner_results": [record]}
    result = compact_scanner_records(scan, commit_sha=identity().revision)
    assert len(result) == 1 and result[0]["scanner_name"] == "cppcheck"
    assert result[0]["worker_provenance"] == record["worker_provenance"]
    assert result[0]["cppcheck_source_coverage"] == record["cppcheck_source_coverage"]
    assert result[0]["finding_count"] == 1 and result[0]["findings"] == []


def test_worker_limits_and_summary_have_spanish_projection():
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    for text, expected in (
        ("The dedicated worker retained native scanner evidence. Individual tool records state completion and limitations.", "evidencia nativa"),
        ("The selected worker profile does not execute this requested tool.", "no ejecuta"),
        ("Native target execution or parsing is incomplete; retained observations require review.", "requieren revisión"),
    ):
        result = _translate_presentation(text)
        assert expected in result and result != text
