from __future__ import annotations

from copy import deepcopy

from nico.client_finding_remediation_register_v4 import (
    build_finding_remediation_register,
    synchronize_canonical_finding_surfaces,
)


def _canonical() -> dict:
    finding = {
        "finding_id": "ARCH-1",
        "category": "architecture",
        "priority": "P1",
        "status": "open",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "finding_family": "complexity-hotspot",
        "fact": "cyclomatic_complexity=52; loc=173; grade=F",
        "interpretation": "High-complexity code hotspot",
        "business_impact": "Concentrated branching increases regression risk.",
        "recommendation": "Split orchestration from presentation logic.",
        "acceptance_criteria": ["Operations route complexity is reduced."],
        "production_scope": True,
        "exact_commit_match": True,
    }
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "abc123",
            "run_id": "run-1",
        },
        "canonical_findings": [finding, deepcopy(finding)],
        "findings_register": [deepcopy(finding), deepcopy(finding)],
        "executive_findings": [
            {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
        ],
        "roadmap": [
            {
                "work_packages": [
                    {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
                ]
            }
        ],
        "backlog": [
            {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
        ],
        "assessment": {},
    }


def _apply(value: dict) -> dict:
    register = build_finding_remediation_register(value)
    return synchronize_canonical_finding_surfaces(value, register)


def test_finding_alias_and_mirrored_surfaces_are_idempotent() -> None:
    first = _apply(_canonical())
    second = _apply(first)

    assert first == second
    finding = first["canonical_findings"][0]
    assert finding["finding_id"].startswith("NICO-FINDING-")
    assert finding["finding_aliases"] == ["ARCH-1"]
    assert first["executive_findings"][0]["finding_id"] == finding["finding_id"]
    assert first["roadmap"][0]["work_packages"][0]["finding_id"] == finding["finding_id"]
    assert first["backlog"][0]["finding_id"] == finding["finding_id"]
    assert first["client_finding_remediation_register"]["summary"][
        "stable_alias_projection_idempotent"
    ] is True
