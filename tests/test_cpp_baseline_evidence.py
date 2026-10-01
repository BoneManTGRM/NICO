from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

def legacy_complete_receipt():
    path = Path(__file__).with_name("test_cpp_configure_first_execution.py")
    spec = importlib.util.spec_from_file_location("baseline_receipt_fixture", path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    from nico.assessment_worker_jobs import _digest
    identity, contract, receipt = fixture.incomplete_receipt()
    keys = ("project-compilation-database", "project-generated-context",
            "project-compiler-evidence", "project-static-environment", "project-static-evidence")
    native = fixture.summarize_probe(fixture.proof(), receipt["target_hashes"],
                                    {key: fixture.ref(key) for key in keys})
    native.update(project_option_policy="explicit-v1", project_options={},
                  project_options_sha256=_digest({}))
    native["complete_execution"] = True  # Seed the invalid historical wire claim.
    receipt.update(native=native, native_sha256=_digest(native))
    return identity, contract, receipt

def test_completed_receipt_without_baseline_native_artifact_is_rejected():
    from nico.assessment_worker_receipts import validate_receipt
    identity, contract, receipt = legacy_complete_receipt()
    assert receipt["native"]["complete_execution"] is True
    with pytest.raises(ValueError, match="worker_configure_first_native_invalid"):
        validate_receipt(identity, contract, "e"*32, "github:1:2:3", receipt)

def test_summary_without_baseline_native_artifact_cannot_claim_complete():
    from nico.assessment_cpp_configure_first_execution import summarize_probe
    _, _, receipt = legacy_complete_receipt()
    from tests.test_cpp_configure_first_execution import proof
    out = summarize_probe(proof(), receipt["target_hashes"], receipt["native"]["artifacts"])
    assert out["complete_execution"] is False

import base64
import hashlib
import json

from nico.assessment_cpp_baseline_evidence import retained_baseline_bytes, validate_retained_baseline
from nico.assessment_worker_receipts import canonical_bytes

def baseline_case(tmp_path, failed=False, freeze=False):
    # The existing command harness returns an independently declared single CTest
    # named owned_suite. It executes no target code or Docker process.
    from tests.test_cpp_baseline_execution import execute, contract
    case_root = tmp_path / "case"
    case_root.mkdir()
    spec = contract()
    if freeze:
        spec.pop("compilation_database_sha256")
        spec.update(schema="nico.cpp-baseline-execution.v2", freeze_compilation_database="after_configuration_before_build")
    result, _, _ = execute(case_root, fault="target_failure" if failed else None, spec=spec)
    targets = {p.relative_to(case_root / "source").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (case_root / "source").rglob("*") if p.is_file()}
    config = {"schema": "nico.cpp-configure-first-contract.v1", "baseline_execution": spec}
    native = {"compilation_database_sha256": result["compilation_database_sha256"],
              "baseline_execution_frozen": result["baseline_execution_frozen"],
              "project_options": {"BUILD_TESTS": "ON"}, "configured_invocations": 1,
              "compiled": True, "tests_executed": True, "tests_passed": not failed}
    for field, values in [("discovered", ["owned_suite"]), ("executed", ["owned_suite"]),
                          ("passed", [] if failed else ["owned_suite"]), ("skipped", [])]:
        native["tests_"+field+"_count"] = len(values)
        native["tests_"+field+"_sha256"] = hashlib.sha256(canonical_bytes(values)).hexdigest()
    image = "sha256:" + "a"*64
    raw = retained_baseline_bytes(result, targets, config, image)
    assert raw is not None
    return raw, targets, config, image, native

@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("freeze", [False, True])
def test_retained_baseline_reconstructs_clean_and_completed_target_failure(tmp_path, failed, freeze):
    raw, targets, config, image, native = baseline_case(tmp_path, failed, freeze)
    out = validate_retained_baseline(raw, targets, config, image, native)
    assert out["required"] == out["executed"] == ["owned_suite"]
    assert out["passed"] == ([] if failed else ["owned_suite"])
    assert out["failed"] == (["owned_suite"] if failed else [])
    assert out["skipped"] == []
    assert out["tests_passed"] is (not failed)
    assert out["native_exit_code"] == (8 if failed else 0)
    assert out["collection_complete"] is True
    assert out["native_evidence_sha256"] == hashlib.sha256(raw).hexdigest()

def rewrite_output(operation, raw):
    operation["output"] = base64.b64encode(raw).decode()
    operation["output_sha256"] = hashlib.sha256(raw).hexdigest()

@pytest.mark.parametrize("fault", [
    "source", "image", "configuration", "false_failed_summary", "wrong_population_hash",
    "missing_operation", "duplicate_operation", "timeout", "truncated", "wrong_argv",
    "wrong_duration", "artifact_bytes", "malformed_junit", "dropped_case", "skipped_case",
    "wrong_discovery", "wrong_database", "wrong_exit",
])
def test_retained_baseline_rejects_controlled_faults(tmp_path, fault):
    raw, targets, config, image, native = baseline_case(tmp_path)
    value = json.loads(raw)
    probe = value["probe"]
    operations = {row["id"]: row for row in probe["operations"]}
    if fault == "source": value["source_population_sha256"] = "0"*64
    if fault == "image": value["image_config_digest"] = "sha256:"+"0"*64
    if fault == "configuration": value["configuration_sha256"] = "0"*64
    if fault == "false_failed_summary":
        native.update(tests_passed=False, tests_passed_count=0,
                      tests_passed_sha256=hashlib.sha256(canonical_bytes([])).hexdigest())
    if fault == "wrong_population_hash": native["tests_passed_sha256"] = "0"*64
    if fault == "missing_operation": probe["operations"].remove(operations["baseline-test-log"])
    if fault == "duplicate_operation": probe["operations"].append(deepcopy(operations["baseline-tests"]))
    if fault == "timeout": operations["baseline-tests"]["timed_out"] = True
    if fault == "truncated": operations["baseline-junit"]["output_truncated"] = True
    if fault == "wrong_argv": operations["baseline-tests"]["invocation"].append("--exclude-regex=owned_suite")
    if fault == "wrong_duration": operations["baseline-tests"]["duration_ms"] = 1000000
    if fault == "artifact_bytes": operations["baseline-junit"]["output"] = base64.b64encode(b"changed").decode()
    if fault in ("malformed_junit", "dropped_case", "skipped_case"):
        junit = {"malformed_junit": b"<testsuite>",
                 "dropped_case": b'<testsuite tests="0"></testsuite>',
                 "skipped_case": b'<testsuite tests="1"><testcase name="owned_suite"><skipped/></testcase></testsuite>'}[fault]
        probe["tests_result"]["junit"] = base64.b64encode(junit).decode()
        rewrite_output(operations["baseline-junit"], canonical_bytes({"data": probe["tests_result"]["junit"], "truncated": False}))
    if fault == "wrong_discovery":
        discovery = canonical_bytes({"kind":"ctestInfo","version":{"major":1,"minor":0},"tests":[{"name":"substituted"}]})
        rewrite_output(operations["baseline-test-discovery"], discovery)
        probe["native_test_discovery"] = base64.b64encode(discovery).decode()
        probe["tests_discovered"] = ["substituted"]
    if fault == "wrong_database": native["compilation_database_sha256"] = "0"*64
    if fault == "wrong_exit": operations["baseline-tests"]["exit_code"] = 8
    with pytest.raises(ValueError):
        validate_retained_baseline(canonical_bytes(value), targets, config, image, native)

def test_completed_failure_requires_the_real_junit_failure_marker(tmp_path):
    raw, targets, config, image, native = baseline_case(tmp_path, failed=True)
    value = json.loads(raw)
    probe = value["probe"]
    junit = b'<testsuite tests="1"><testcase name="owned_suite"><failure/></testcase></testsuite>'
    probe["tests_result"]["junit"] = base64.b64encode(junit).decode()
    row = next(row for row in probe["operations"] if row["id"] == "baseline-junit")
    rewrite_output(row, canonical_bytes({"data":probe["tests_result"]["junit"],"truncated":False}))
    with pytest.raises(ValueError):
        validate_retained_baseline(canonical_bytes(value), targets, config, image, native)

@pytest.mark.parametrize("fault", [
    "create_image", "privileged_create", "image_argv", "database_argv", "boundary_policy",
    "reversed_order", "source_transfer", "configure_options", "missing_source_transport",
])
def test_baseline_rejects_source_transport_and_isolation_faults(tmp_path, fault):
    raw, targets, config, image, native = baseline_case(tmp_path)
    value = json.loads(raw)
    probe = value["probe"]
    operations = {row["id"]: row for row in probe["operations"]}
    if fault == "create_image": operations["create"]["invocation"][-2] = "sha256:"+"0"*64
    if fault == "privileged_create": operations["create"]["invocation"].append("--privileged")
    if fault == "image_argv": operations["image"]["invocation"][-1] = "sha256:"+"0"*64
    if fault == "database_argv": operations["compilation-database"]["invocation"][-2] = "/work/other.json"
    if fault == "boundary_policy":
        probe["boundary"]["memory_max"] = "max"
        rewrite_output(operations["boundary-after"], canonical_bytes(probe["boundary"]))
    if fault == "reversed_order": probe["operations"].reverse()
    if fault == "source_transfer":
        changed = dict(targets)
        changed[next(iter(changed))] = "0"*64
        rewrite_output(operations["source-transfer"], canonical_bytes(changed))
    if fault == "configure_options": operations["configure"]["invocation"].append("-DBUILD_TESTS=OFF")
    if fault == "missing_source_transport": probe["operations"].remove(operations["source-transfer"])
    with pytest.raises(ValueError):
        validate_retained_baseline(canonical_bytes(value), targets, config, image, native)

def test_existing_four_mib_database_boundary_remains_supported(tmp_path):
    raw, targets, config, image, native = baseline_case(tmp_path)
    value = json.loads(raw)
    probe = value["probe"]
    database = base64.b64decode(probe["compilation_database"], validate=True)
    padded = database + b" " * (4*1024*1024-len(database))
    # Whitespace changes bytes/hash, never the independently fixed context population.
    assert json.loads(padded) == json.loads(database)
    digest = hashlib.sha256(padded).hexdigest()
    probe["compilation_database"] = base64.b64encode(padded).decode()
    probe["compilation_database_sha256"] = native["compilation_database_sha256"] = digest
    config["baseline_execution"]["compilation_database_sha256"] = digest
    probe["baseline_execution"] = deepcopy(config["baseline_execution"])
    operations = {row["id"]: row for row in probe["operations"]}
    for key in ("compilation-database", "post-build-database"):
        rewrite_output(operations[key], canonical_bytes({"data": probe["compilation_database"], "truncated": False}))
    captured = retained_baseline_bytes(probe, targets, config, image)
    assert len(captured) > 16*1024*1024
    out = validate_retained_baseline(captured, targets, config, image, native)
    assert out["required"] == out["passed"] == ["owned_suite"]
    assert out["collection_complete"] is True

def test_missing_verified_baseline_cannot_finish_canonical_projection():
    from nico.assessment_cpp_configure_first_projection import project_configure_first_record
    from tests.test_cpp_configure_first_projection import identity
    record = {"status": "partial", "completed": False, "verified_complete": False,
              "verified_for_this_report": False, "cppcheck_source_coverage": {},
              "worker_provenance": {}}
    receipt = {"configuration_sha256": "1"*64, "target_hashes": {"main.cpp": "2"*64},
               "native": {"complete_execution": True, "compilation_database_sha256": "3"*64,
                          "artifacts": {"project-static-evidence": {"artifact_id": "scanartifact_"+"4"*64}}}}
    reconstruction = {"analysis": {"complete": True, "required_contexts": ["5"*64],
                         "analyzed_contexts": ["5"*64], "findings": [], "limitations": [],
                         "native_evidence_sha256": "6"*64},
                      "compiler": {"native_evidence_sha256": "7"*64}}
    out = project_configure_first_record(record, identity(), {}, receipt, reconstruction)
    assert out["completed"] is False
    assert out["verified_complete"] is False
