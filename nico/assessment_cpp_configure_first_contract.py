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
MAX_SOURCE_BYTES = 64 * 1024 * 1024

def validate_configuration(value):
    fields = {"schema", "platform", "expected_tree_sha", "project_options",
              "source_byte_limit", "baseline_execution", "capabilities"}
    if (not isinstance(value, dict) or set(value) != fields or value.get("schema") != SCHEMA
            or value.get("platform") != "linux/amd64"
            or not isinstance(value.get("expected_tree_sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", value["expected_tree_sha"]) is None
            or type(value.get("source_byte_limit")) is not int
            or not 1 <= value["source_byte_limit"] <= MAX_SOURCE_BYTES):
        raise ValueError("worker_configure_first_configuration_invalid")
    options=value["project_options"]
    if (not isinstance(options, dict) or len(options)>64
            or any(not isinstance(k,str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}",k) is None
                or k.startswith("CMAKE_") or not isinstance(v,str)
                or re.fullmatch(r"[A-Za-z0-9_./+-]{1,120}",v) is None for k,v in options.items())):
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
    capabilities=value["capabilities"]
    expected_caps={"capture_generated_context":True,"project_compiler_evidence":True,
                   "project_static_analysis":True,"extended_compiler_budget":True,
                   "compiler_environment":True}
    if capabilities != expected_caps:
        raise ValueError("worker_configure_first_capabilities_invalid")
    return deepcopy(value)
