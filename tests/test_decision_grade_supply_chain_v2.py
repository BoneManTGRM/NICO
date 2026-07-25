from __future__ import annotations

from nico.decision_grade_supply_chain_v2 import build_supply_chain_package


def test_builds_inventory_sbom_and_lockfile_completeness() -> None:
    package = build_supply_chain_package(
        {
            "package.json": '{"dependencies":{"react":"18.3.1"},"devDependencies":{"typescript":"5.6.3"}}',
            "package-lock.json": '{"lockfileVersion":3}',
            "requirements.txt": "fastapi==0.115.0\npytest>=8.0\n",
            "uv.lock": "version = 1\n",
        },
        repository="owner/repo",
        commit_sha="a" * 40,
    )

    assert package["lockfile_completeness"]["complete"] is True
    assert {item["name"] for item in package["dependency_inventory"]} == {
        "react",
        "typescript",
        "fastapi",
        "pytest",
    }
    assert package["cyclonedx_sbom"]["bomFormat"] == "CycloneDX"
    assert len(package["cyclonedx_sbom"]["components"]) == 4
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False


def test_missing_lockfile_is_explicit_and_not_silently_clean() -> None:
    package = build_supply_chain_package({"package.json": '{"dependencies":{"react":"18"}}'})

    assert package["lockfile_completeness"]["complete"] is False
    assert package["lockfile_completeness"]["missing_lockfile_ecosystems"] == ["npm"]


def test_output_is_deterministic_for_file_order() -> None:
    first = build_supply_chain_package(
        {"requirements.txt": "b==2\na==1\n", "uv.lock": "x"},
        repository="r",
        commit_sha="c",
    )
    second = build_supply_chain_package(
        {"uv.lock": "x", "requirements.txt": "b==2\na==1\n"},
        repository="r",
        commit_sha="c",
    )

    assert first == second


def test_empty_vulnerability_register_does_not_claim_clean() -> None:
    package = build_supply_chain_package({"requirements.txt": "fastapi==1\n", "uv.lock": "x"})

    assert package["vulnerability_register"] == []
    assert any("does not prove absence" in item for item in package["limitations"])
    assert all(item["status"] == "not_assessed" for item in package["license_register"])
