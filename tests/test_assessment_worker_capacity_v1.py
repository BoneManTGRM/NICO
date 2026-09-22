"""Full-project worker capacity stays separate from the 256 MiB proofs."""
from nico.assessment_worker_capacity_v1 import (
    BOUNDED_RESOURCES,
    FULL_PROJECT_PROFILE,
    FULL_PROJECT_RESOURCES,
    docker_resource_args,
    full_project_plan,
    select_production_profile,
)


def test_bounded_profiles_keep_proven_256_mib_flags():
    for profile in (
        "cppcheck-standalone-v1",
        "cpp-configured-v1",
        "cpp-sanitized-v1",
        "cpp-runtime-cases-v1",
    ):
        flags = docker_resource_args(profile)
        assert "--cpus=0.5" in flags
        assert "--memory=256m" in flags
        assert "--memory-swap=256m" in flags
        assert "--pids-limit=32" in flags
        assert BOUNDED_RESOURCES["sufficient_for_bitcoin_compile"] is False


def test_full_project_capacity_exceeds_documented_bitcoin_compile():
    resources = FULL_PROJECT_RESOURCES
    assert resources["memory_bytes"] == 2_147_483_648
    assert resources["memory_bytes"] > resources["documented_compile_memory_bytes"] == 1_610_612_736
    assert resources["sufficient_for_bitcoin_compile"] is True
    assert resources["sanitizer_memory_bytes"] is None
    assert resources["sanitizer_budget_status"] == "not_measured"
    assert resources["fuzz_memory_bytes"] is None
    assert resources["fuzz_budget_status"] == "not_measured"
    flags = docker_resource_args(FULL_PROJECT_PROFILE)
    assert "--cpus=2" in flags
    assert "--memory=2g" in flags
    assert "--memory-swap=2g" in flags
    assert "--pids-limit=256" in flags
    assert "--memory=256m" not in flags


def test_full_project_plan_declares_stages_without_executing_bitcoin():
    plan = full_project_plan()
    assert plan["profile"] == FULL_PROJECT_PROFILE
    assert plan["executed_stages"] == []
    assert plan["bitcoin_executed"] is False
    assert plan["production_selected"] is False
    assert set(plan["stages"]) == {
        "cmake_configure", "baseline_build", "dependencies", "unit_tests",
        "integration_tests", "sanitizer_checks", "bounded_fuzz",
    }


def test_production_selects_full_project_only_after_controlled_proof():
    qualified = {
        "profile": FULL_PROJECT_PROFILE,
        "resource_class": "full-project-v1",
        "controlled_project_passed": True,
        "bitcoin_executed": False,
        "report_verified": False,
    }
    selected = select_production_profile(qualified)
    assert selected["profile"] == FULL_PROJECT_PROFILE
    assert selected["automatic"] is True
    assert selected["bitcoin_executed"] is False
    assert select_production_profile(None) is None
    unqualified = dict(qualified)
    unqualified["controlled_project_passed"] = False
    assert select_production_profile(unqualified) is None
    bitcoin_without_report = dict(qualified)
    bitcoin_without_report["bitcoin_executed"] = True
    assert select_production_profile(bitcoin_without_report) is None


def test_compiler_workspace_stays_noexec_and_native_test_is_exec():
    build = " ".join(docker_resource_args("cpp-configured-v1", executable=False))
    native = " ".join(docker_resource_args("cpp-runtime-cases-v1", executable=True))
    assert "noexec,size=33554432" in build
    assert ",exec,size=33554432" in native
    assert "noexec" not in native
    try:
        docker_resource_args("cpp-unbounded-v9")
    except ValueError as exc:
        assert "worker_resource_profile_unknown" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")
