"""Worker resource classes. Bounded proofs stay at 256 MiB.

The full-project class is sized above Bitcoin Core's documented 1.5 GiB
compile requirement; that comparison is not measured capacity qualification.
Compile, sanitizer and fuzz memory stay unmeasured until a real run produces
them. Production selection requires
a controlled-project qualification receipt and does not claim Bitcoin execution.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

BOUNDED_CLASS = "bounded-owned-v1"
FULL_PROJECT_CLASS = "full-project-v1"
FULL_PROJECT_PROFILE = "cpp-full-project-v1"

# Existing owned compile/test/sanitizer proofs were taken inside this envelope.
BOUNDED_RESOURCES = {
    "resource_class": BOUNDED_CLASS,
    "cpus": "0.5",
    "memory": "256m",
    "memory_bytes": 268_435_456,
    "memory_swap": "256m",
    "pids": "32",
    "tmpfs_bytes": 33_554_432,
    "sufficient_for_bitcoin_compile": False,
}

# 2 GiB is above the pinned Bitcoin doc minimum of 1,610,612,736 bytes.
FULL_PROJECT_RESOURCES = {
    "resource_class": FULL_PROJECT_CLASS,
    "cpus": "2",
    "memory": "2g",
    "memory_bytes": 2_147_483_648,
    "memory_swap": "2g",
    "pids": "256",
    "tmpfs_bytes": 2_147_483_648,
    "sufficient_for_bitcoin_compile": None,
    "compile_memory_bytes": None,
    "compile_budget_status": "not_measured",
    "documented_compile_memory_bytes": 1_610_612_736,
    "sanitizer_memory_bytes": None,
    "sanitizer_budget_status": "not_measured",
    "fuzz_memory_bytes": None,
    "fuzz_budget_status": "not_measured",
}

FULL_PROJECT_STAGES = (
    "cmake_configure",
    "baseline_build",
    "dependencies",
    "unit_tests",
    "integration_tests",
    "sanitizer_checks",
    "bounded_fuzz",
)

BOUNDED_PROFILES = {
    "cppcheck-standalone-v1",
    "cpp-configured-v1",
    "cpp-sanitized-v1",
    "cpp-runtime-cases-v1",
}


def resources_for(profile: str) -> dict[str, Any]:
    if profile == FULL_PROJECT_PROFILE:
        return deepcopy(FULL_PROJECT_RESOURCES)
    if profile in BOUNDED_PROFILES:
        return deepcopy(BOUNDED_RESOURCES)
    raise ValueError("worker_resource_profile_unknown")


def docker_resource_args(profile: str, *, executable: bool | None = None) -> list[str]:
    """Flags for one docker create. Bounded profiles keep the proven 256 MiB line.

    executable None omits exec/noexec (standalone cppcheck). False is noexec
    (compiler workspace). True is exec (native-test workspace only).
    """
    resources = resources_for(profile)
    mount = "nosuid,nodev,"
    if executable is True:
        mount += "exec,"
    elif executable is False:
        mount += "noexec,"
    return [
        "--cpus=" + resources["cpus"],
        "--memory=" + resources["memory"],
        "--memory-swap=" + resources["memory_swap"],
        "--pids-limit=" + resources["pids"],
        "--tmpfs=/work:rw," + mount + "size=" + str(resources["tmpfs_bytes"]) + ",mode=1777",
    ]


def full_project_plan() -> dict[str, Any]:
    """Declare the Bitcoin-scale stages. None of them have executed."""
    resources = resources_for(FULL_PROJECT_PROFILE)
    if resources["memory_bytes"] <= resources["documented_compile_memory_bytes"]:
        raise ValueError("full_project_memory_below_documented_compile")
    if resources["sanitizer_budget_status"] != "not_measured" or resources["fuzz_budget_status"] != "not_measured":
        raise ValueError("unmeasured_budgets_must_stay_unmeasured")
    return {
        "profile": FULL_PROJECT_PROFILE,
        "resource_class": FULL_PROJECT_CLASS,
        "stages": list(FULL_PROJECT_STAGES),
        "executed_stages": [],
        "bitcoin_executed": False,
        "production_selected": False,
        "resources": resources,
    }


def select_production_profile(qualification: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Select the full-project profile only after a controlled C++ proof.

    A missing or Bitcoin-only claim does not select anything. Report accuracy
    for Bitcoin stays a later receipt.
    """
    if not isinstance(qualification, Mapping):
        return None
    required = {
        "profile", "resource_class", "controlled_project_passed",
        "bitcoin_executed", "report_verified",
    }
    if set(qualification) != required:
        return None
    if (qualification["profile"] != FULL_PROJECT_PROFILE
            or qualification["resource_class"] != FULL_PROJECT_CLASS
            or qualification["controlled_project_passed"] is not True):
        return None
    # This gate is exclusively for controlled-project qualification, never a
    # Bitcoin execution claim. Reject strings, integers and missing evidence
    # rather than silently projecting them into a false execution/report state.
    if qualification["bitcoin_executed"] is not False:
        return None
    if not isinstance(qualification["report_verified"], bool):
        return None
    return {
        "profile": FULL_PROJECT_PROFILE,
        "resource_class": FULL_PROJECT_CLASS,
        "automatic": True,
        "bitcoin_executed": False,
        "report_verified": False,
    }
