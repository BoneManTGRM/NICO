from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_raw_mapping_string_recovery_v1 import (
    install_raw_mapping_string_recovery_v1,
    recover_literal_structure,
)


def _raw_roadmap_string() -> str:
    return str(
        {
            "window": "0-30 days",
            "objective": "Remove the highest-risk delivery constraints.",
            "work_packages": [
                {
                    "work_package_id": "WP-001",
                    "title": "Decompose page.tsx",
                    "owner_role": "Product Engineer",
                    "effort": "M",
                }
            ],
        }
    )


def test_recover_literal_structure_accepts_only_inert_container_literals() -> None:
    raw = _raw_roadmap_string()
    recovered = recover_literal_structure(raw)

    assert isinstance(recovered, dict)
    assert recovered["window"] == "0-30 days"
    assert recover_literal_structure("normal client text") == "normal client text"
    executable = "__import__('os').system('false')"
    assert recover_literal_structure(executable) == executable


def test_installed_recovery_humanizes_pre_stringified_roadmap_without_mutation() -> None:
    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface

    raw = _raw_roadmap_string()
    before = deepcopy(raw)
    status = install_raw_mapping_string_recovery_v1()
    rendered = surface.humanize_client_surface_value(raw, item_limit=100_000)
    lines = surface.client_surface_values([raw], limit=1, item_limit=100_000)

    assert status["status"] in {"installed", "already_installed"}
    assert "Window: 0-30 days" in rendered
    assert "Work Package Id: WP-001" in rendered
    assert "Owner Role: Product Engineer" in rendered
    assert "{" not in rendered
    assert "'window'" not in rendered
    assert lines == [rendered]
    assert raw == before
    assert status["canonical_structured_sources_unchanged"] is True
