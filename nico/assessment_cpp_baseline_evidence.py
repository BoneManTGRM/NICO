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
from nico.assessment_cpp_configure_first_contract import runtime_required, membership_required, native_commands_required, generation_required

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
_ORDER_V3 = tuple(k for key in _ORDER_V2 for k in (
    (key,'project-native-commands') if key=='project-enabled-targets' else
    (key,'project-enabled-targets-post-build','project-native-commands-post-build') if key=='post-build-database' else (key,)))
_FIELDS_V3 = _FIELDS_V2 + ('native_command_capture','native_command_freeze','analysis_compilation_database_sha256','analysis_invocations')


def _generation_order(probe):
    generation = probe.get('generated_input_materialization') or {}
    selected = (generation.get('plan') or {}).get('selected_targets')
    _require(isinstance(selected,list) and len(selected)<=128)
    additions = ('generation-inputs-before', *('generation-target-'+str(i).zfill(3) for i in range(len(selected))),
                 'generation-inputs-after')
    return tuple(k for key in _ORDER_V3 for k in ((key,*additions) if key=='baseline-build' else (key,)))


def _require(condition):
    if not condition:
        raise ValueError("worker_baseline_evidence_invalid")


def retained_baseline_bytes(probe, targets, configuration, image, *, runtime_plan=None):
    """Keep native bytes; incomplete probes without captured JUnit remain incomplete."""
    rows = probe.get("operations") or []
    membership=membership_required(configuration)
    native_commands=native_commands_required(configuration)
    generation=generation_required(configuration)
    if generation and probe.get('generated_input_materialization') is None:
        return None
    order=_generation_order(probe) if generation else _ORDER_V3 if native_commands else _ORDER_V2 if membership else _ORDER
    fields=_FIELDS_V3+('generated_input_materialization',) if generation else _FIELDS_V3 if native_commands else _FIELDS_V2 if membership else _FIELDS
    population=frozenset(order)
    selected = [row for row in rows if row.get("id") in population]
    expected = population if probe.get("unit_test_data") is not None else population - {"unit-test-data"}
    if (set(row["id"] for row in selected) != expected
            or not isinstance((probe.get("tests_result") or {}).get("junit"), str)):
        return None
    value = {
        "schema": "nico.cpp-baseline-evidence.v4" if generation else "nico.cpp-baseline-evidence.v3" if native_commands else "nico.cpp-baseline-evidence.v2" if membership else "nico.cpp-baseline-evidence.v1",
        "source_population_sha256": hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        "configuration_sha256": hashlib.sha256(canonical_bytes(configuration)).hexdigest(),
        "image_config_digest": image,
        "runtime_plan": runtime_plan,
        "probe": {**{key: probe.get(key) for key in fields}, "operations": selected},
    }
    raw = canonical_bytes(value)
    _require(0 < len(raw) <= MAX_BASELINE_BYTES)
    return raw


def validate_retained_baseline(raw, targets, configuration, image, native, *, membership_raw=None, native_raw=None, native_post_raw=None, generation_raw=None):
    """Reconstruct populations from native discovery/JUnit before accepting summaries."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BASELINE_BYTES)
    try:
        membership=membership_required(configuration)
        native_commands=native_commands_required(configuration)
        generation=generation_required(configuration)
        fields=_FIELDS_V3+('generated_input_materialization',) if generation else _FIELDS_V3 if native_commands else _FIELDS_V2 if membership else _FIELDS
        value = _json(raw)
        order=_generation_order(value.get('probe') or {}) if generation else _ORDER_V3 if native_commands else _ORDER_V2 if membership else _ORDER
        _require(isinstance(value, dict) and set(value) == {
            "schema", "source_population_sha256", "configuration_sha256",
            "image_config_digest", "runtime_plan", "probe",
        })
        _require(value["schema"] == ("nico.cpp-baseline-evidence.v4" if generation else "nico.cpp-baseline-evidence.v3" if native_commands else "nico.cpp-baseline-evidence.v2" if membership else "nico.cpp-baseline-evidence.v1")
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
        if generation:
            materialization=probe['generated_input_materialization']
            reference=materialization['artifact']
            _require(isinstance(generation_raw,bytes)
                and generation_raw==canonical_bytes({k:v for k,v in materialization.items() if k!='artifact'})
                and reference=={'path':'artifacts/project-generation-evidence-'+hashlib.sha256(generation_raw).hexdigest()+'.json',
                    'sha256':hashlib.sha256(generation_raw).hexdigest(),'bytes':len(generation_raw)}
                and native['generated_input_materialization_complete'] is True
                and native['generation_evidence_sha256']==reference['sha256']
                and native['generation_selected_targets_count']==len(materialization['plan']['selected_targets']))
        def no_external_output(reference):
            if membership:
                key=reference['path'].removeprefix('artifacts/').rsplit('-',1)[0]
                if native_commands and key in {'project-native-commands','project-native-commands-post-build'}:
                    supplied=native_raw if key=='project-native-commands' else native_post_raw
                    expected_sha=native['native_command_capture_sha256'] if key=='project-native-commands' else native['native_command_post_capture_sha256']
                    expected_reference=(probe['native_command_capture'] if key=='project-native-commands'
                        else next(row['output_artifact'] for row in rows if row['id']==key))
                else:
                    _require(key=='project-enabled-targets' or native_commands and key=='project-enabled-targets-post-build')
                    supplied=membership_raw
                    expected_sha=native['enabled_target_capture_sha256']
                    expected_reference=(probe['enabled_target_capture'] if key=='project-enabled-targets'
                        else next(row['output_artifact'] for row in rows if row['id']==key))
                _require(reference==expected_reference and isinstance(supplied,bytes)
                    and reference['sha256']==hashlib.sha256(supplied).hexdigest()==expected_sha
                    and reference['bytes']==len(supplied)
                    and reference['path']=='artifacts/'+key+'-'+reference['sha256']+'.json')
                return supplied
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
