from __future__ import annotations

from nico.repository_quality_signals import (
    analyze_branch_hygiene,
    analyze_documentation_alignment,
    analyze_frontend_routes,
    analyze_runtime_patch_surface,
    analyze_security_configuration,
    build_repository_quality_signals,
)


def test_route_reexports_are_not_classified_as_placeholders() -> None:
    paths = [
        "apps/web/app/dashboard/page.tsx",
        "apps/web/app/findings/page.tsx",
        "apps/web/app/settings/page.tsx",
    ]
    files = {
        path: "export {default} from '../page';\n"
        for path in paths
    }

    result = analyze_frontend_routes(paths, files)

    assert result["route_aliases"] == paths
    assert result["explicit_placeholders"] == []
    assert result["findings"] == []
    assert any("intentional re-exports" in item for item in result["evidence"])


def test_explicit_coming_soon_route_is_flagged() -> None:
    path = "apps/web/app/billing/page.tsx"
    result = analyze_frontend_routes(
        [path],
        {path: "export default function Page(){return <main>Coming soon</main>}"},
    )

    assert result["explicit_placeholders"] == [path]
    assert result["findings"][0]["category"] == "frontend_completeness"
    assert result["findings"][0]["automatic_change_allowed"] is False


def test_large_branch_inventory_is_reported_without_claiming_staleness() -> None:
    branches = [{"name": f"branch-{index}"} for index in range(561)]

    result = analyze_branch_hygiene(branches)

    assert result["branch_count"] == 561
    assert result["findings"][0]["code"] == "branch_inventory_large"
    rendered = " ".join(result["findings"][0]["evidence"]).lower()
    assert "stale" not in rendered
    assert "delete" not in rendered


def test_runtime_patch_surface_is_detected() -> None:
    paths = [f"nico/capability_{index}_patch.py" for index in range(25)]
    init_text = "\n".join(f"install_capability_{index}()" for index in range(15))

    result = analyze_runtime_patch_surface(paths, {"nico/__init__.py": init_text})

    assert result["patch_compat_fallback_count"] == 25
    assert result["package_installer_call_count"] == 15
    assert result["findings"][0]["code"] == "runtime_patch_surface"


def test_latest_deployed_sha_drift_is_detected() -> None:
    old_sha = "1" * 40
    current_sha = "2" * 40
    path = "docs/PROJECT_STATUS.md"
    text = f"The latest verified deployed main commit is `{old_sha}`."

    result = analyze_documentation_alignment(
        [path],
        {path: text},
        current_default_branch_sha=current_sha,
    )

    assert result["stale_release_claim_count"] == 1
    assert result["findings"][0]["code"] == "documentation_deployment_sha_drift"
    assert old_sha in result["findings"][0]["evidence"][0]
    assert current_sha in result["findings"][0]["evidence"][0]


def test_security_configuration_requires_provider_evidence() -> None:
    result = analyze_security_configuration(
        {
            "code_scanning": {"status": "available", "open_alert_count": 0},
            "secret_scanning": {"status": "unavailable", "message": "permission denied"},
            "dependabot": {"status": "disabled", "message": "Dependabot alerts are disabled"},
        }
    )

    assert any("open_alert_count=0" in item for item in result["evidence"])
    assert any(item["code"] == "dependabot_disabled" for item in result["findings"])
    assert any("permission denied" in item for item in result["unavailable"])


def test_combined_quality_signals_are_advisory_only() -> None:
    result = build_repository_quality_signals(
        tree_paths=["apps/web/app/dashboard/page.tsx", "docs/PROJECT_STATUS.md"],
        files={
            "apps/web/app/dashboard/page.tsx": "export {default} from '../page';",
            "docs/PROJECT_STATUS.md": "Current status.",
        },
        branches=[{"name": "main"}],
        current_default_branch_sha="a" * 40,
        security_posture={},
    )

    assert result["status"] == "complete"
    assert result["scoring_effect"] == "advisory_only_until_calibrated"
    assert "Route aliases are not classified as placeholders" in result["truth_rule"]
