"""Execute the internal configure-first C/C++ contract through qualified stages.

Large native artifacts are retained through the authenticated worker transport.
The final receipt contains only bounded population hashes/counts and immutable
artifact references. Canonical finding reconstruction is a separate backend
step and is never implied by this module.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import re

from nico.assessment_worker_receipts import canonical_bytes

PROFILE = "cpp-configure-first-v2"


def execution_timeout_limit(contract):
    schema=((contract or {}).get("configuration") or {}).get("schema")
    wall=((contract or {}).get("limits") or {}).get("wall_seconds")
    if type(wall) is not int or wall < 1:
        raise ValueError("worker_configure_first_execution_contract_invalid")
    cap=8980 if schema == "nico.cpp-configure-first-contract.v3" else 2400
    return min(cap, max(1, wall-20))


_REQUIRED_ARTIFACTS = {
    "project-compilation-database", "project-generated-context", "project-compiler-evidence",
    "project-static-environment", "project-static-evidence",
}
_OPTIONAL_ARTIFACTS = {"project-static-clang-fallback","project-runtime-evidence"}
_SHA = re.compile(r"[0-9a-f]{64}")


def _population(values):
    if not isinstance(values, list):
        raise ValueError("worker_configure_first_projection_invalid")
    return len(values), hashlib.sha256(canonical_bytes(values)).hexdigest()


def _artifact_reference(value, key):
    required={"artifact_id","key","sha256","gzip_sha256","retained_bytes","gzip_bytes","storage_backend"}
    if (not isinstance(value,dict) or set(value)!=required or value.get("key")!=key
            or value.get("storage_backend")!="postgres"
            or not isinstance(value.get("artifact_id"),str) or not value["artifact_id"].startswith("scanartifact_")
            or any(not isinstance(value.get(name),str) or _SHA.fullmatch(value[name]) is None
                   for name in ("sha256","gzip_sha256"))
            or any(type(value.get(name)) is not int or value[name] < 1
                   for name in ("retained_bytes","gzip_bytes"))):
        raise ValueError("worker_configure_first_artifact_reference_invalid")
    return deepcopy(value)


def summarize_probe(result, targets, artifacts):
    if (not isinstance(result,dict) or not isinstance(targets,dict) or not targets
            or not isinstance(artifacts,dict)
            or any(not isinstance(k,str) or not isinstance(v,str) or _SHA.fullmatch(v) is None for k,v in targets.items())):
        raise ValueError("worker_configure_first_projection_invalid")
    generated=result.get("generated_context") or {}
    compiler=result.get("project_compiler") or {}
    static=result.get("project_static") or {}
    stage=result.get("project_static_stage") or {}
    tests=result.get("tests_discovered") or []
    executed=((result.get("tests_result") or {}).get("executed") or [])
    passed=((result.get("tests_result") or {}).get("passed") or [])
    skipped=((result.get("tests_result") or {}).get("skipped") or [])
    compiler_required=compiler.get("required_contexts") or []
    compiler_checked=compiler.get("checked_contexts") or []
    static_required=static.get("required_contexts") or []
    static_analyzed=static.get("analyzed_contexts") or []
    findings=static.get("findings") or []
    limitations=static.get("limitations") or []
    modeled=static.get("modeled_inputs") or []
    fallback=static.get("clang_fallback") or {}
    refs={key:_artifact_reference(value,key) for key,value in sorted(artifacts.items())}
    for key in refs:
        if key not in _REQUIRED_ARTIFACTS|_OPTIONAL_ARTIFACTS:
            raise ValueError("worker_configure_first_artifact_reference_invalid")
    tests_count,tests_sha=_population(tests)
    executed_count,executed_sha=_population(executed)
    passed_count,passed_sha=_population(passed)
    skipped_count,skipped_sha=_population(skipped)
    cr_count,cr_sha=_population(compiler_required); cc_count,cc_sha=_population(compiler_checked)
    sr_count,sr_sha=_population(static_required); sa_count,sa_sha=_population(static_analyzed)
    finding_count,finding_sha=_population(findings); limitation_count,limitation_sha=_population(limitations)
    modeled_count,modeled_sha=_population(modeled)
    fr_count,fr_sha=_population(fallback.get("required_contexts") or [])
    fa_count,fa_sha=_population(fallback.get("analyzed_contexts") or [])
    complete=bool(
        result.get("status")=="BASELINE_EXECUTED" and result.get("error") is None
        and result.get("compiled") is True and result.get("tests_executed") is True
        and result.get("tests_passed") is True and result.get("generated_context_verified") is True
        and compiler.get("complete") is True and static.get("complete") is True
        and stage.get("complete") is True and result.get("boundary_verified") is True
        and result.get("cleanup_verified") is True and _REQUIRED_ARTIFACTS <= set(refs)
        and cr_count==cc_count and sr_count==sa_count
    )
    return {
        "schema":"nico.cpp-configure-first-native.v1","status":result.get("status"),
        "complete_execution":complete,"error":result.get("error"),
        "source_population_sha256":hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        "source_count":len(targets),"compilation_database_sha256":result.get("compilation_database_sha256"),
        "configured_invocations":result.get("configured_invocations"),"baseline_execution_frozen":result.get("baseline_execution_frozen"),
        "compiled":result.get("compiled") is True,"tests_executed":result.get("tests_executed") is True,
        "tests_passed":result.get("tests_passed") is True,
        "tests_discovered_count":tests_count,"tests_discovered_sha256":tests_sha,
        "tests_executed_count":executed_count,"tests_executed_sha256":executed_sha,
        "tests_passed_count":passed_count,"tests_passed_sha256":passed_sha,
        "tests_skipped_count":skipped_count,"tests_skipped_sha256":skipped_sha,
        "generated_context_verified":result.get("generated_context_verified") is True,
        "project_compiler_complete":compiler.get("complete") is True,
        "project_compiler_required_count":cr_count,"project_compiler_required_sha256":cr_sha,
        "project_compiler_checked_count":cc_count,"project_compiler_checked_sha256":cc_sha,
        "project_static_complete":static.get("complete") is True,
        "project_static_required_count":sr_count,"project_static_required_sha256":sr_sha,
        "project_static_analyzed_count":sa_count,"project_static_analyzed_sha256":sa_sha,
        "project_static_findings_count":finding_count,"project_static_findings_sha256":finding_sha,
        "project_static_limitations_count":limitation_count,"project_static_limitations_sha256":limitation_sha,
        "project_static_modeled_inputs_count":modeled_count,"project_static_modeled_inputs_sha256":modeled_sha,
        "clang_fallback_complete":(fallback.get("complete") is True if fallback else None),
        "clang_fallback_required_count":fr_count,"clang_fallback_required_sha256":fr_sha,
        "clang_fallback_analyzed_count":fa_count,"clang_fallback_analyzed_sha256":fa_sha,
        "boundary_verified":result.get("boundary_verified") is True,
        "cleanup_verified":result.get("cleanup_verified") is True,
        "scratch_capacity_verified":result.get("scratch_capacity_verified") is True,
        "memory_peak_bytes":result.get("memory_peak_bytes"),
        "static_memory_peak_bytes":stage.get("memory_peak_bytes"),
        "duration_ms":result.get("duration_ms"),"aggregate_duration_ms":result.get("aggregate_duration_ms"),
        "artifacts":refs,"canonical_findings_projected":False,
    }


def run_configure_first(contract, source, acquisition, *, checkpoint, timeout_seconds, retain_artifact):
    from nico.assessment_worker_receipts import validate_contract
    from nico.assessment_cpp_configuration_probe import probe_project_configuration
    contract=validate_contract(contract)
    if (contract.get("profile")!=PROFILE or not isinstance(acquisition,dict)
            or acquisition.get("schema")!="nico.github_https_tree_materialization.v2"
            or acquisition.get("tree_sha")!=contract["configuration"]["expected_tree_sha"]
            or not isinstance(acquisition.get("inputs"),dict) or not acquisition["inputs"]
            or acquisition.get("population_sha256")!=hashlib.sha256(canonical_bytes(acquisition["inputs"])).hexdigest()
            or type(timeout_seconds) is not int or not 1<=timeout_seconds<=execution_timeout_limit(contract)
            or not callable(checkpoint) or not callable(retain_artifact)):
        raise ValueError("worker_configure_first_execution_contract_invalid")
    targets=deepcopy(acquisition["inputs"])
    retained={}
    def sink(key, raw):
        reference=_artifact_reference(retain_artifact(key,raw),key)
        if reference["sha256"]!=hashlib.sha256(raw).hexdigest() or reference["retained_bytes"]!=len(raw):
            raise ValueError("worker_configure_first_artifact_reference_invalid")
        retained[key]=reference
        return {"path":"artifacts/"+key+"-"+reference["sha256"]+".json",
                "sha256":reference["sha256"],"bytes":reference["retained_bytes"]}
    cfg=contract["configuration"]; caps=cfg["capabilities"]
    runtime_plan=None; runtime_interfaces=None; unit_test_data=None
    if cfg["schema"] in {"nico.cpp-configure-first-contract.v2", "nico.cpp-configure-first-contract.v3"}:
        from nico.assessment_cpp_cmake_policy import derive_project_options
        project_options = derive_project_options(source, targets, cfg["project_option_policy"])
        project_option_policy = cfg["project_option_policy"]
    else:
        project_options = cfg["project_options"]
        project_option_policy = "explicit-v1"
    if cfg["schema"]=="nico.cpp-configure-first-contract.v3":
        from nico.assessment_cpp_runtime_scope import (capture_runtime_interfaces,
            derive_runtime_plan_from_interfaces, acquire_unit_test_data)
        runtime_interfaces=capture_runtime_interfaces(source,targets)
        runtime_plan=derive_runtime_plan_from_interfaces(runtime_interfaces,targets,project_options,cfg["runtime_scope"])
        unit_test_data=acquire_unit_test_data(runtime_plan,checkpoint)
    result=probe_project_configuration(source,targets,contract["image_digest"],
        project_options=project_options,retain=lambda _:checkpoint(),
        baseline_execution=cfg["baseline_execution"],unit_test_data=unit_test_data,runtime_plan=runtime_plan,
        capture_generated_context=caps["capture_generated_context"],
        retain_artifact=sink,project_compiler_evidence=caps["project_compiler_evidence"],
        project_static_analysis=caps["project_static_analysis"],
        extended_compiler_budget=caps["extended_compiler_budget"],
        compiler_environment=caps["compiler_environment"])
    import base64
    database=base64.b64decode(result.get("compilation_database") or "",validate=True)
    if not database or hashlib.sha256(database).hexdigest()!=result.get("compilation_database_sha256"):
        raise ValueError("worker_configure_first_database_missing")
    sink("project-compilation-database",database)
    if runtime_plan is not None:
        from nico.assessment_cpp_runtime_scope import retained_runtime_bytes
        runtime_raw=retained_runtime_bytes(runtime_interfaces,runtime_plan,result.get("runtime_evidence"))
        sink("project-runtime-evidence",runtime_raw)
    native=summarize_probe(result,targets,retained)
    if runtime_plan is not None:
        runtime_summary=result.get("runtime_summary") or {}
        native["schema"]="nico.cpp-configure-first-native.v2"
        native["runtime_complete"]=(runtime_summary.get("complete") is True and "project-runtime-evidence" in retained)
        native["runtime_plan_sha256"]=hashlib.sha256(canonical_bytes(runtime_plan)).hexdigest()
        native["runtime_summary_sha256"]=hashlib.sha256(canonical_bytes(runtime_summary)).hexdigest()
        duration=(result.get("runtime_evidence") or {}).get("duration_ms")
        native["runtime_duration_ms"]=duration if type(duration) is int and duration>=0 else 0
        native["complete_execution"]=native["complete_execution"] and native["runtime_complete"]
    native["project_option_policy"]=project_option_policy
    native["project_options"]=dict(sorted(project_options.items()))
    native["project_options_sha256"]=hashlib.sha256(canonical_bytes(native["project_options"])).hexdigest()
    return {"native":native,"derived_targets":targets,
            "tool_version":contract["tool_version"]}
