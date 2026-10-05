"""Retained, source-bound baseline CTest evidence for ordinary worker results."""
from __future__ import annotations

import base64
import hashlib
from xml.etree.ElementTree import ParseError

from nico.assessment_worker_receipts import canonical_bytes
from nico.assessment_cpp_collection import validate_baseline_collection, _operations
from nico.assessment_cpp_collection_transport import validate_transport
from nico.assessment_cpp_full_project_execution import boundary_valid
from nico.assessment_worker_jobs import MAX_CPP_ARTIFACT_RAW_BYTES
from nico.assessment_cpp_full_project import _json
from nico.assessment_cpp_configure_first_contract import runtime_required, membership_required

MAX_BASELINE_BYTES = MAX_CPP_ARTIFACT_RAW_BYTES
_ORDER = (
    "image", "create", "start", "analyst-setup", "boundary-before", "scratch-capacity",
    "source-transfer", "boundary-after", "cmake-version", "gcc-version", "g++-version",
    "configure", "configuration-cache", "compilation-database", "unit-test-data",
    "baseline-build", "post-build-database", "baseline-test-discovery", "baseline-tests",
    "baseline-test-log", "baseline-junit",
)
_OPERATIONS = frozenset(_ORDER)
_FIELDS = (
    "baseline_execution", "baseline_execution_frozen", "compilation_database",
    "compilation_database_sha256", "native_test_discovery", "tests_discovered",
    "tests_result", "unit_test_data", "boundary", "image_config_digest",
    "project_options", "configuration_cache", "configuration_cache_sha256", "effective_project_options",
)
_ORDER_V2 = tuple(k for key in _ORDER for k in (
    ('fileapi-query',key) if key=='configure' else
    (key,'project-enabled-targets') if key=='compilation-database' else (key,)))
_FIELDS_V2 = _FIELDS + ('fileapi_client','enabled_target_capture')


def _require(condition):
    if not condition:
        raise ValueError("worker_baseline_evidence_invalid")


def retained_baseline_bytes(probe, targets, configuration, image, *, runtime_plan=None):
    """Keep native bytes; incomplete probes without captured JUnit remain incomplete."""
    rows = probe.get("operations") or []
    membership=membership_required(configuration)
    order=_ORDER_V2 if membership else _ORDER
    fields=_FIELDS_V2 if membership else _FIELDS
    population=frozenset(order)
    selected = [row for row in rows if row.get("id") in population]
    expected = population if probe.get("unit_test_data") is not None else population - {"unit-test-data"}
    if (set(row["id"] for row in selected) != expected
            or not isinstance((probe.get("tests_result") or {}).get("junit"), str)):
        return None
    value = {
        "schema": "nico.cpp-baseline-evidence.v2" if membership else "nico.cpp-baseline-evidence.v1",
        "source_population_sha256": hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        "configuration_sha256": hashlib.sha256(canonical_bytes(configuration)).hexdigest(),
        "image_config_digest": image,
        "runtime_plan": runtime_plan,
        "probe": {**{key: probe.get(key) for key in fields}, "operations": selected},
    }
    raw = canonical_bytes(value)
    _require(0 < len(raw) <= MAX_BASELINE_BYTES)
    return raw


def validate_retained_baseline(raw, targets, configuration, image, native, *, membership_raw=None):
    """Reconstruct populations from native discovery/JUnit before accepting summaries."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BASELINE_BYTES)
    try:
        membership=membership_required(configuration)
        fields=_FIELDS_V2 if membership else _FIELDS
        order=_ORDER_V2 if membership else _ORDER
        value = _json(raw)
        _require(isinstance(value, dict) and set(value) == {
            "schema", "source_population_sha256", "configuration_sha256",
            "image_config_digest", "runtime_plan", "probe",
        })
        _require(value["schema"] == ("nico.cpp-baseline-evidence.v2" if membership else "nico.cpp-baseline-evidence.v1")
                 and value["source_population_sha256"] == hashlib.sha256(canonical_bytes(targets)).hexdigest()
                 and value["configuration_sha256"] == hashlib.sha256(canonical_bytes(configuration)).hexdigest()
                 and value["image_config_digest"] == image)
        probe = value["probe"]
        _require(isinstance(probe, dict) and set(probe) == set(fields) | {"operations"}
                 and probe["image_config_digest"] == image)
        database = base64.b64decode(probe["compilation_database"], validate=True)
        digest = hashlib.sha256(database).hexdigest()
        _require(0 < len(database) <= 4 * 1024 * 1024
                 and digest == probe["compilation_database_sha256"] == native["compilation_database_sha256"]
                 and probe["baseline_execution_frozen"] == native["baseline_execution_frozen"])
        rows = probe["operations"]
        expected_order = [key for key in order
                          if key != "unit-test-data" or probe["unit_test_data"] is not None]
        _require(isinstance(rows, list) and [row["id"] for row in rows] == expected_order
                 and probe["project_options"] == native["project_options"]
                 and boundary_valid(probe["boundary"], profile=configuration["baseline_execution"]["profile"]))
        runtime_plan = value["runtime_plan"]
        if runtime_required(configuration):
            _require(isinstance(runtime_plan, dict)
                     and runtime_plan.get("total_seconds") == configuration["runtime_scope"]["total_seconds"]
                     and hashlib.sha256(canonical_bytes(runtime_plan)).hexdigest() == native["runtime_plan_sha256"])
        else:
            _require(runtime_plan is None)
        def no_external_output(reference):
            if membership:
                _require(reference == probe['enabled_target_capture']
                    and isinstance(membership_raw,bytes)
                    and reference['sha256']==hashlib.sha256(membership_raw).hexdigest()
                    and reference['sha256']==native['enabled_target_capture_sha256']
                    and reference['bytes']==len(membership_raw)
                    and reference['path']=='artifacts/project-enabled-targets-'+reference['sha256']+'.json')
                return membership_raw
            raise ValueError("worker_baseline_evidence_invalid")
        validate_transport(probe, _operations(rows, no_external_output, allow_baseline_failure=True),
                           targets, runtime_plan=runtime_plan, baseline_only=True)
        baseline = configuration["baseline_execution"]
        if baseline["schema"] == "nico.cpp-baseline-execution.v1":
            _require(digest == baseline["compilation_database_sha256"])
        else:
            _require(probe["baseline_execution_frozen"] == {
                "schema": "nico.cpp-baseline-execution-freeze.v1",
                "source_population_sha256": value["source_population_sha256"],
                "project_options": native["project_options"],
                "compilation_database_sha256": digest,
                "configured_invocations": native["configured_invocations"],
                "freeze_point": "after_configuration_before_build",
            })
        result = validate_baseline_collection(
            probe, baseline, no_external_output, allow_target_failure=True)
        for field, names in (("discovered", result["required"]), ("executed", result["executed"]),
                             ("passed", result["passed"]), ("skipped", result["skipped"])):
            _require(native["tests_" + field + "_count"] == len(names)
                     and native["tests_" + field + "_sha256"] == hashlib.sha256(canonical_bytes(names)).hexdigest())
        passed = result["passed"] == result["required"]
        _require(native["compiled"] is True and native["tests_executed"] is True
                 and native["tests_passed"] is passed)
        operations = {row["id"]: row for row in probe["operations"]}
        junit = base64.b64decode(probe["tests_result"]["junit"], validate=True)
        log_payload = _json(base64.b64decode(operations["baseline-test-log"]["output"], validate=True))
        log = base64.b64decode(log_payload["data"], validate=True)
        return {
            **result, "failed": [name for name in result["required"] if name not in result["passed"]],
            "collection_complete": True, "tests_passed": passed,
            "junit_sha256": hashlib.sha256(junit).hexdigest(),
            "ctest_log_sha256": hashlib.sha256(log).hexdigest(),
            "native_exit_code": operations["baseline-tests"]["exit_code"],
            "native_evidence_sha256": hashlib.sha256(raw).hexdigest(),
        }
    except (KeyError, TypeError, IndexError, ParseError) as exc:
        raise ValueError("worker_baseline_evidence_invalid") from exc
