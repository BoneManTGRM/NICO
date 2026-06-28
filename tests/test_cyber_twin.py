from nico.cyber_twin import build_demo_cyber_twin


def test_cyber_twin_demo_has_required_local_model_nodes():
    result = build_demo_cyber_twin()
    node_types = {node["node_type"] for node in result["nodes"]}
    assert {"asset", "file", "route", "dependency", "finding", "repair", "verification", "drift", "agent", "audit"} <= node_types
    assert result["mode"] == "local_demo_only_no_external_discovery"
    assert result["tenant_id"] == "local"
    assert result["links"]
