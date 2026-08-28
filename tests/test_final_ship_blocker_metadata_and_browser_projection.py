from __future__ import annotations

from pathlib import Path

from nico.comprehensive_canonical_report_source_v1 import _attach_engagement_identity
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


def _engagement_metadata() -> dict:
    return build_comprehensive_engagement_metadata(
        client_name="NICO Acceptance Client",
        project_name="NICO Acceptance Project",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "access_method": ["GitHub HTTPS/API - read-only"],
                    "primary_technical_contact": ["NICO Acceptance Contact"],
                    "authorized_scope": [
                        "Full repository at exact assessed SHA - read-only"
                    ],
                }
            }
        },
    )


def test_canonical_identity_preserves_all_supplied_engagement_metadata() -> None:
    metadata = _engagement_metadata()
    identity: dict[str, str] = {}

    _attach_engagement_identity(identity, {"engagement_metadata": metadata})

    assert identity == {
        "customer_name": "NICO Acceptance Client",
        "project_name": "NICO Acceptance Project",
        "primary_technical_contact": "NICO Acceptance Contact",
        "access_method": "GitHub HTTPS/API - read-only",
        "authorized_scope": "Full repository at exact assessed SHA - read-only",
        "engagement_metadata_sha256": metadata["engagement_metadata_sha256"],
    }


def test_canonical_identity_does_not_infer_missing_engagement_metadata() -> None:
    identity: dict[str, str] = {}

    _attach_engagement_identity(
        identity,
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_scope_identifier",
            "project_id": "project_scope_identifier",
        },
    )

    assert identity == {}


def test_exact_run_views_unmount_optional_evidence_editor() -> None:
    workspace = (
        ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"
    ).read_text(encoding="utf-8")
    evidence_form = (
        ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"
    ).read_text(encoding="utf-8")

    assert 'disabled={running || Boolean(result?.run_id)}' in workspace
    assert "if (disabled) return null;" in evidence_form


def test_compact_mobile_context_uses_three_single_line_controls() -> None:
    source = (
        ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"
    ).read_text(encoding="utf-8")
    mobile_block = source.split("if (!richEditorEnabled) {", 1)[1].split(
        "const activeDefinition =", 1
    )[0]

    assert 'const CLIENT_ENGAGEMENT_FIELDS = ["access_method", "primary_technical_contact", "authorized_scope"] as const;' in source
    assert '<input\n              type="text"' in mobile_block
    assert "<textarea" not in mobile_block
    assert 'data-mobile-client-engagement-context="true"' in mobile_block
