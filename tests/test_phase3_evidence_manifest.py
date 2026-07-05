def test_evidence_manifest_module_statuses_correct():
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_manifest_test")

    manifest_path = Path("/tmp/nico_manifest_test/evidence_manifest.json")

    with open(manifest_path) as f:
        manifest = json.load(f)

    module_statuses = manifest.get("module_statuses", {})

    assert "dependency_audit" in module_statuses
    assert module_statuses.get("dependency_audit") in ("completed", "completed_with_findings", "limited", "unavailable", "unknown")

    assert "cicd_audit" in module_statuses
    assert "github_activity" in module_statuses