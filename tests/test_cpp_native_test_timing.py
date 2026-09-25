"""Owned synthetic receipt tests: nested work must fit the retained stage clock."""
import base64
import json

import pytest

from nico.assessment_cpp_full_project import validate_native
from nico.assessment_worker_receipts import validate_receipt
from scripts.worker_protocol_fixture import identity
from tests.test_assessment_cpp_full_project import encoded, wrap
from tests.test_cpp_native_test_binding import v3_fixture


def receipt_case(group="address"):
    contract, native = v3_fixture()
    stage = next(row for row in native["steps"] if row["id"] == group + "-native-test-evidence")
    evidence = json.loads(base64.b64decode(stage["output"]))
    operations = [evidence["snapshot_operation"]]
    operations.extend(item[key] for item in evidence["inspections"] for key in ("nm", "dynamic"))
    operations.extend(item[key] for item in evidence["tests"] for key in ("before", "probe", "execution", "after"))
    # These are explicitly synthetic clocks, not measured native execution.
    for operation in operations:
        operation["duration_ms"] = 0
    return contract, native, stage, evidence, operations


def publish_evidence(stage, evidence):
    stage["output"] = encoded(json.dumps(evidence).encode())


@pytest.mark.parametrize("group", ["address", "undefined"])
@pytest.mark.parametrize("operation", range(11))
def test_each_nested_operation_must_fit_its_enclosing_native_stage(group, operation):
    contract, native, stage, evidence, operations = receipt_case(group)
    operations[operation]["duration_ms"] = 20000
    publish_evidence(stage, evidence)
    # Enclosing row records ten milliseconds; every operation is individually
    # within its own 32-second ceiling, so only aggregate binding can reject it.
    with pytest.raises(ValueError, match="worker_native_test_duration_contradiction"):
        receipt = wrap(native, contract)
        validate_receipt(identity(contract), contract, receipt["lease_id"], receipt["worker_id"], receipt)


@pytest.mark.parametrize("group", ["address", "undefined"])
def test_nested_runtime_is_summed_instead_of_only_checking_each_operation(group):
    contract, native, stage, evidence, operations = receipt_case(group)
    for operation in operations:
        operation["duration_ms"] = 2
    publish_evidence(stage, evidence)
    with pytest.raises(ValueError, match="worker_native_test_duration_contradiction"):
        validate_native(native, contract)


@pytest.mark.parametrize("group", ["address", "undefined"])
@pytest.mark.parametrize("duration", [0, 10, 12])
def test_consistent_nested_runtime_preserves_existing_canonical_evidence(group, duration):
    contract, native, stage, evidence, operations = receipt_case(group)
    baseline = validate_native(native, contract)
    # Snapshot timing is not a new canonical/report field; existing projection
    # and immutable native receipt schemas must remain unchanged.
    operations[0]["duration_ms"] = duration
    publish_evidence(stage, evidence)
    assert validate_native(native, contract) == baseline


def test_failed_nested_operation_does_not_excuse_impossible_timing():
    contract, native, stage, evidence, operations = receipt_case()
    operations[0]["duration_ms"] = 20000
    stage["exit_code"] = 1
    publish_evidence(stage, evidence)
    with pytest.raises(ValueError, match="worker_native_test_duration_contradiction"):
        validate_native(native, contract)
