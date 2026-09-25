"""Internal configure-first C/C++ production contract.

The contract freezes source revision/tree and bounded execution policy before
source bytes are materialized. SHA256 member identities are derived only after
the exact Git tree/archive is verified, before any CMake command executes.
"""
from __future__ import annotations
from copy import deepcopy
import re

PROFILE = "cpp-configure-first-v2"
SCHEMA = "nico.cpp-configure-first-contract.v1"
SCHEMA_V2 = "nico.cpp-configure-first-contract.v2"
SCHEMA_V3 = "nico.cpp-configure-first-contract.v3"
MAX_SOURCE_BYTES = 64 * 1024 * 1024

def validate_configuration(value):
    schema = value.get("schema") if isinstance(value, dict) else None
    fields = {"schema", "platform", "expected_tree_sha",
              "source_byte_limit", "baseline_execution", "capabilities"}
    fields |= ({"project_options"} if schema == SCHEMA else {"project_option_policy"})
    if schema == SCHEMA_V3:
        fields.add("runtime_scope")
    if (not isinstance(value, dict) or set(value) != fields or schema not in {SCHEMA, SCHEMA_V2, SCHEMA_V3}
            or value.get("platform") != "linux/amd64"
            or not isinstance(value.get("expected_tree_sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", value["expected_tree_sha"]) is None
            or type(value.get("source_byte_limit")) is not int
            or not 1 <= value["source_byte_limit"] <= MAX_SOURCE_BYTES):
        raise ValueError("worker_configure_first_configuration_invalid")
    if schema == SCHEMA:
        options=value["project_options"]
        if (not isinstance(options, dict) or len(options)>64
                or any(not isinstance(k,str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}",k) is None
                    or k.startswith("CMAKE_") or not isinstance(v,str)
                    or re.fullmatch(r"[A-Za-z0-9_./+-]{1,120}",v) is None for k,v in options.items())):
            raise ValueError("worker_configure_first_options_invalid")
    else:
        from nico.assessment_cpp_cmake_policy import POLICY
        if value.get("project_option_policy") != POLICY:
            raise ValueError("worker_configure_first_options_invalid")
    baseline=value["baseline_execution"]
    expected={"schema","profile","freeze_compilation_database","build_seconds","test_seconds","test_case_seconds","parallel"}
    if (not isinstance(baseline,dict) or set(baseline)!=expected
            or baseline.get("schema")!="nico.cpp-baseline-execution.v2"
            or baseline.get("profile")!="cpp-baseline-qualification-v1"
            or baseline.get("freeze_compilation_database")!="after_configuration_before_build"
            or any(type(baseline.get(k)) is not int or not 1 <= baseline[k] <= maximum
                   for k,maximum in (("build_seconds",1200),("test_seconds",900),("test_case_seconds",300),("parallel",4)))):
        raise ValueError("worker_configure_first_execution_invalid")
    if schema == SCHEMA_V3:
        runtime=value["runtime_scope"]
        runtime_fields={"schema","functional_policy","functional_seconds","sanitizers",
            "sanitizer_build_seconds","sanitizer_test_seconds","sanitizer_test_case_seconds",
            "fuzz_policy","fuzz_replay_runs","fuzz_campaign_runs","fuzz_campaign_seconds","parallel"}
        if (not isinstance(runtime,dict) or set(runtime)!=runtime_fields
                or runtime.get("schema")!="nico.cpp-runtime-scope.v1"
                or runtime.get("functional_policy")!="source-declared-functional-v1"
                or runtime.get("sanitizers")!=["address","undefined"]
                or runtime.get("fuzz_policy")!="source-declared-libfuzzer-v1"
                or type(runtime.get("functional_seconds")) is not int or not 1<=runtime["functional_seconds"]<=1800
                or type(runtime.get("sanitizer_build_seconds")) is not int or not 1<=runtime["sanitizer_build_seconds"]<=1200
                or type(runtime.get("sanitizer_test_seconds")) is not int or not 1<=runtime["sanitizer_test_seconds"]<=900
                or type(runtime.get("sanitizer_test_case_seconds")) is not int or not 1<=runtime["sanitizer_test_case_seconds"]<=300
                or type(runtime.get("fuzz_replay_runs")) is not int or runtime["fuzz_replay_runs"]!=1
                or type(runtime.get("fuzz_campaign_runs")) is not int or not 1<=runtime["fuzz_campaign_runs"]<=1024
                or type(runtime.get("fuzz_campaign_seconds")) is not int or not 1<=runtime["fuzz_campaign_seconds"]<=900
                or type(runtime.get("parallel")) is not int or not 1<=runtime["parallel"]<=4):
            raise ValueError("worker_configure_first_runtime_scope_invalid")
    capabilities=value["capabilities"]
    expected_caps={"capture_generated_context":True,"project_compiler_evidence":True,
                   "project_static_analysis":True,"extended_compiler_budget":True,
                   "compiler_environment":True}
    if capabilities != expected_caps:
        raise ValueError("worker_configure_first_capabilities_invalid")
    return deepcopy(value)
