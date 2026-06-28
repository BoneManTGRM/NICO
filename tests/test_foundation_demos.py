from nico.foundations import (
    agent_security_scan_demo,
    approvals_pending_demo,
    bench_demo,
    connector_policy_demo,
    cyber_twin_demo,
    sandbox_scanner_demo,
    swarm_policy_demo,
    tenant_demo,
    vault_demo,
)


def test_foundation_demo_commands_are_local_only():
    demos = [
        swarm_policy_demo(),
        agent_security_scan_demo(),
        vault_demo(),
        connector_policy_demo(),
        sandbox_scanner_demo(),
        approvals_pending_demo(),
        tenant_demo(),
        cyber_twin_demo(),
        bench_demo(),
    ]
    assert all(demo["mode"] == "local_only_demo_no_external_calls" for demo in demos)


def test_agent_security_demo_finds_risky_agent():
    report = agent_security_scan_demo()
    categories = {finding["category"] for finding in report["findings"]}
    assert "over_broad_tool_permissions" in categories
    assert "unsafe_memory_access" in categories


def test_vault_demo_uses_masked_references_only():
    demo = vault_demo()
    assert demo["denied_without_approval"]["allowed"] is False
    assert "DEMO_PLACEHOLDER_VALUE" not in str(demo)


def test_connector_guard_disabled_by_default():
    demo = connector_policy_demo()
    assert demo["policy"]["enabled"] is False
    assert demo["sample_request_decision"]["allowed"] is False


def test_sandbox_demo_blocks_destructive_command():
    demo = sandbox_scanner_demo()
    assert demo["blocked_plan"]["allowed"] is False


def test_tenant_demo_blocks_cross_tenant_access():
    demo = tenant_demo()
    assert demo["same_tenant_allowed"] is True
    assert demo["cross_tenant_allowed"] is False


def test_cyber_twin_and_bench_demo_shapes():
    assert cyber_twin_demo()["nodes"]
    assert bench_demo()["benchmark_claim"] == "no_production_benchmark_claimed"
